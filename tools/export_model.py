"""Exporta a versão Production do Registry para models/credit-score-v1/.

Essa pasta é autocontida (sem `mlruns`) e vai dentro do ZIP para que qualquer
máquina consiga registrar a mesma versão promovida sem treinar novamente.

Uso: python tools/export_model.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import mlflow
from mlflow.artifacts import download_artifacts
from mlflow.tracking import MlflowClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.registry import MODEL_NAME, configure_mlflow, production_version

DEST = ROOT / "models" / "credit-score-v1"


def main() -> None:
    configure_mlflow()
    client = MlflowClient()
    version = production_version(client)
    if not version:
        raise SystemExit("Nenhuma versão em Production para exportar.")
    mv = client.get_model_version(MODEL_NAME, version)
    if not mv.run_id:
        raise SystemExit(f"Versão {version} não possui run_id (não é exportável por run).")
    with tempfile.TemporaryDirectory(dir=ROOT, prefix=".export-model-") as tmp:
        downloaded = Path(download_artifacts(run_id=mv.run_id, artifact_path="model",
                                             dst_path=tmp))
        # download_artifacts pode criar uma camada extra de pastas.
        source = downloaded if (downloaded / "MLmodel").is_file() else downloaded / "model"
        if not (source / "MLmodel").is_file():
            raise SystemExit(f"MLmodel não encontrado em {source}")
        shutil.rmtree(DEST, ignore_errors=True)
        shutil.copytree(source, DEST)
    model_uri = DEST.as_uri()
    probe = mlflow.pyfunc.load_model(model_uri)
    # Remove metadados do registro original para o seed controlar nome/versão
    # (download_artifacts pode recriá-lo após a cópia/primeiro load).
    (DEST / "registered_model_meta").unlink(missing_ok=True)
    print(f"Exportado: models/credit-score-v1 (Production v{version} -> {mv.run_id[:8]})")
    print(f"Flavor pyfunc OK: {type(probe).__name__}")
    print(f"Caminho no ZIP para registro: {model_uri}")


if __name__ == "__main__":
    main()