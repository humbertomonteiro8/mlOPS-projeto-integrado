"""Treino, tracking MLflow e promoção para Production (dataset da disciplina).

Uso: python -m src.train --data "C:\\...\\train.csv\\train.csv"
MLFLOW_TRACKING_URI opcional; sem ele, usa ./mlruns compartilhado com a API.
Não copia o CSV com SSN para artefatos: registra hash SHA-256 e contagens.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import lightgbm as lgb
import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
import xgboost as xgb
from mlflow.tracking import MlflowClient
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import GridSearchCV, GroupKFold, GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from src.features import CATEGORICAL, FEATURE_NUMERIC, REQUIRED, CreditFeatures
from src.registry import MODEL_NAME, configure_mlflow, production_version

CLASS_NAMES = ["Good", "Poor", "Standard"]  # mesma ordem em train e predict
MIN_F1 = 0.70
MIN_IMPROVEMENT = 0.005


def make_pipeline(estimator):
    return Pipeline([
        ("features", CreditFeatures()),
        ("columns", ColumnTransformer([
            ("numeric", SimpleImputer(strategy="median", keep_empty_features=True), FEATURE_NUMERIC),
            ("category", Pipeline([
                ("impute", SimpleImputer(strategy="most_frequent")),
                ("onehot", OneHotEncoder(handle_unknown="ignore")),
            ]), CATEGORICAL),
        ])),
        ("classifier", estimator),
    ])


def candidates(quick=False):
    trees = [30] if quick else [150, 200]
    return {
        "random_forest": (RandomForestClassifier(random_state=42, n_jobs=1),
                          {"classifier__n_estimators": trees, "classifier__max_depth": [10] if quick else [10, 16]}),
        "xgboost": (xgb.XGBClassifier(random_state=42, n_jobs=1, eval_metric="mlogloss", tree_method="hist"),
                    {"classifier__n_estimators": trees, "classifier__max_depth": [4] if quick else [4, 6]}),
        "lightgbm": (lgb.LGBMClassifier(random_state=42, n_jobs=1, verbosity=-1),
                     {"classifier__n_estimators": trees, "classifier__num_leaves": [15] if quick else [15, 31]}),
    }


def choose(results, incumbent_f1=None, minimum=MIN_F1):
    """Empate (<0,005): menor gap treino/validação; incumbente ganha empate."""
    eligible = [r for r in results if r["f1_val"] >= minimum]
    if not eligible:
        return None
    top = max(r["f1_val"] for r in eligible)
    tied = [r for r in eligible if top - r["f1_val"] < MIN_IMPROVEMENT]
    winner = min(tied, key=lambda r: (abs(r["f1_train"] - r["f1_val"]), -r["f1_val"]))
    if incumbent_f1 is not None and winner["f1_val"] < incumbent_f1 + MIN_IMPROVEMENT:
        return None
    return winner


def load_dataset(path, max_customers=None):
    df = pd.read_csv(path)
    required = set(REQUIRED + ["Credit_Score", "Customer_ID"])
    if not required <= set(df.columns):
        raise ValueError(f"Colunas ausentes no CSV: {sorted(required - set(df.columns))}")
    df = df[df["Credit_Score"].isin(CLASS_NAMES)].copy()
    # Filtrar ANTES do split. Não usamos SSN, nome, ID, Customer_ID ou Month como features.
    df = df[pd.to_numeric(df["Age"], errors="coerce") > 0]
    df = df[pd.to_numeric(df["Monthly_Inhand_Salary"], errors="coerce") > 0]
    if max_customers:
        customers = df["Customer_ID"].drop_duplicates().sample(
            n=min(max_customers, df["Customer_ID"].nunique()), random_state=42)
        df = df[df["Customer_ID"].isin(customers)].copy()
    if df["Customer_ID"].nunique() < 6 or df["Credit_Score"].nunique() != 3:
        raise ValueError("Necessários >= 6 clientes e as três classes para treino/CV.")
    return df


def train(path, quick=False, max_customers=None, minimum=MIN_F1):
    configure_mlflow()
    mlflow.set_experiment(MODEL_NAME)
    client = MlflowClient()
    df = load_dataset(path, max_customers)
    with open(path, "rb") as source:
        data_hash = hashlib.file_digest(source, "sha256").hexdigest()
    # GroupShuffleSplit/GroupKFold impedem que meses do mesmo cliente caiam
    # simultaneamente no treino e validação (vazamento no split do notebook).
    group = df["Customer_ID"]
    tr_idx, val_idx = next(GroupShuffleSplit(test_size=0.2, random_state=42).split(df, df["Credit_Score"], group))
    train_df, val_df = df.iloc[tr_idx], df.iloc[val_idx]
    X_train, X_val = train_df[REQUIRED], val_df[REQUIRED]
    y_train = train_df["Credit_Score"].map({v: i for i, v in enumerate(CLASS_NAMES)}).to_numpy()
    y_val = val_df["Credit_Score"].map({v: i for i, v in enumerate(CLASS_NAMES)}).to_numpy()
    if len(set(y_train)) != 3 or len(set(y_val)) != 3:
        raise ValueError("Split sem as três classes. Use mais clientes.")
    results = []
    for name, (estimator, grid) in candidates(quick).items():
        search = GridSearchCV(make_pipeline(estimator), grid, cv=GroupKFold(n_splits=3),
                              scoring="f1_weighted", n_jobs=1)
        search.fit(X_train, y_train, groups=train_df["Customer_ID"])
        model = search.best_estimator_
        pred = model.predict(X_val)
        f1_train = f1_score(y_train, model.predict(X_train), average="weighted")
        f1_val = f1_score(y_val, pred, average="weighted")
        with mlflow.start_run(run_name=name) as run:
            mlflow.log_params(search.best_params_)
            mlflow.log_param("cv", "GroupKFold(3)")
            mlflow.log_param("validation", "GroupShuffleSplit(0.2, seed=42)")
            mlflow.log_metric("f1_weighted_train", f1_train)
            mlflow.log_metric("f1_weighted_val", f1_val)
            mlflow.log_metric("accuracy_val", accuracy_score(y_val, pred))
            mlflow.log_metric("overfit_gap", f1_train - f1_val)
            mlflow.set_tags({"dataset_sha256": data_hash, "dataset_rows": str(len(df)),
                             "train_rows": str(len(train_df)), "val_rows": str(len(val_df)),
                             "model_family": name, "class_order": json.dumps(CLASS_NAMES)})
            mlflow.log_text(classification_report(y_val, pred, labels=[0, 1, 2],
                                                  target_names=CLASS_NAMES, zero_division=0), "classification_report.txt")
            mlflow.log_text(pd.DataFrame(confusion_matrix(y_val, pred, labels=[0, 1, 2]),
                                         index=CLASS_NAMES, columns=CLASS_NAMES).to_csv(), "confusion_matrix.csv")
            # Pipeline completo: o mesmo pré-processamento é executado em predict.py.
            mlflow.sklearn.log_model(model, artifact_path="model", serialization_format="cloudpickle")
            results.append({"name": name, "run_id": run.info.run_id,
                            "f1_train": f1_train, "f1_val": f1_val})
        print(f"{name}: F1 validação = {f1_val:.4f}")

    incumbent = production_version(client)
    incumbent_f1 = None
    if incumbent:
        try:
            old = mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}/{incumbent}")
            incumbent_f1 = f1_score(y_val, np.asarray(old.predict(X_val)).astype(int), average="weighted")
            print(f"Production v{incumbent}: F1 no mesmo holdout = {incumbent_f1:.4f}")
        except Exception as exc:
            raise RuntimeError("Não foi possível avaliar o modelo em produção; promoção cancelada") from exc
    winner = choose(results, incumbent_f1, minimum)
    if winner is None:
        print(f"Sem promoção: F1 mínimo {minimum:.3f} e melhoria >= {MIN_IMPROVEMENT:.3f} sobre Production.")
        return None
    version = mlflow.register_model(f"runs:/{winner['run_id']}/model", MODEL_NAME)
    # archive_existing_versions evita arquivar manualmente antes da nova promoção.
    client.transition_model_version_stage(MODEL_NAME, version.version, "Production", archive_existing_versions=True)
    print(f"Promovido: {winner['name']} v{version.version} (F1 {winner['f1_val']:.4f}).")
    return version.version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True, help="CSV train.csv da disciplina; NÃO versionar no Git")
    parser.add_argument("--quick", action="store_true", help="Grade reduzida, somente para smoke test")
    parser.add_argument("--max-customers", type=int, default=None, help="Amostra de clientes, somente para teste")
    parser.add_argument("--min-f1", type=float, default=MIN_F1, help="Limiar de promoção (padrão: 0.70)")
    args = parser.parse_args()
    if not 0 <= args.min_f1 <= 1 or (args.max_customers is not None and args.max_customers < 6):
        parser.error("--min-f1 deve estar entre 0 e 1 e --max-customers >= 6")
    train(args.data, args.quick, args.max_customers, args.min_f1)


if __name__ == "__main__":
    main()
