"""Configuração do mesmo MLflow para treino e inferência."""
import os
from pathlib import Path

import mlflow
from mlflow.exceptions import MlflowException

MODEL_NAME = "quantumfinance-credit-score"
ROOT = Path(__file__).resolve().parents[1]


def configure_mlflow():
    # file:///... funciona no Windows e no Linux; ambos processos devem ver o mesmo store.
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI") or (ROOT / "mlruns").as_uri())


def production_version(client):
    try:
        versions = client.get_latest_versions(MODEL_NAME, stages=["Production"])
    except MlflowException as exc:
        if (getattr(exc, "error_code", None) == "RESOURCE_DOES_NOT_EXIST"
                or "not found" in str(exc).lower()
                or "does not exist" in str(exc).lower()):
            return None
        raise
    return str(versions[0].version) if versions else None
