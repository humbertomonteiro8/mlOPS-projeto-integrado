"""Inferência: resolve Production no MLflow em cada chamada, sem fixar versão.

CLI: python -m src.predict --input clientes.csv --output resultado.csv
CSV deve conter apenas os campos de REQUIRED (sem nome/SSN/ID).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import mlflow
import mlflow.pyfunc
import numpy as np
import pandas as pd
from mlflow.tracking import MlflowClient

from src.features import REQUIRED
from src.registry import MODEL_NAME, configure_mlflow, production_version

CLASS_NAMES = ["Good", "Poor", "Standard"]


class ModelNotAvailableError(RuntimeError):
    pass


class CreditScorePredictor:
    def __init__(self):
        configure_mlflow()
        self.client = MlflowClient()
        self._model = None
        self._version = None

    def predict_dataframe(self, data: pd.DataFrame):
        missing = set(REQUIRED) - set(data.columns)
        if missing:
            raise ValueError(f"Campos obrigatórios ausentes: {', '.join(sorted(missing))}")
        # Reconsulta a versão por request, carrega novamente SOMENTE se mudar.
        # URI numérica evita reportar uma versão diferente da realmente carregada.
        try:
            version = production_version(self.client)
            if not version:
                raise ModelNotAvailableError("Nenhuma versão do modelo está em Production")
            if version != self._version:
                model = mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}/{version}")
                self._model, self._version = model, version
        except ModelNotAvailableError:
            raise
        except Exception as exc:
            raise ModelNotAvailableError("Registry ou modelo Production indisponível") from exc
        indices = np.asarray(self._model.predict(data[REQUIRED])).astype(int)
        if np.any((indices < 0) | (indices >= len(CLASS_NAMES))):
            raise ValueError("Modelo retornou classe não reconhecida")
        return [CLASS_NAMES[i] for i in indices], self._version

    def predict(self, payload: dict):
        predictions, version = self.predict_dataframe(pd.DataFrame([payload]))
        return {"credit_score_predicted": predictions[0], "model_version": version}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    df = pd.read_csv(args.input)
    labels, version = CreditScorePredictor().predict_dataframe(df)
    # Não persiste colunas sensíveis do CSV de entrada na saída.
    pd.DataFrame({"credit_score_predicted": labels, "model_version": version}).to_csv(args.output, index=False)
    print(f"{len(labels)} predições pela versão {version} em {args.output}")


if __name__ == "__main__":
    main()
