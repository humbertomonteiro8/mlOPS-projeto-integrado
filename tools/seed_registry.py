"""Registra o modelo embalado (models/credit-score-v1) como Production.

Permite usar predict.py e a API em qualquer máquina SEM dataset e SEM treino.
Idempotente: se a versão embalada já estiver registrada, não duplica.

Uso: python tools/seed_registry.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import mlflow
from mlflow.tracking import MlflowClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.registry import MODEL_NAME, configure_mlflow, production_version

BUNDLED = ROOT / "models" / "credit-score-v1"
TAG_KEY = "bundled_seed"
TAG_VALUE = "true"


def _bundled_version(client: MlflowClient):
    """Versão registrada que aponta para o modelo embalado, se existir."""
    for mv in client.search_model_versions(f"name='{MODEL_NAME}'"):
        tags = mv.tags or {}
        if tags.get(TAG_KEY) == TAG_VALUE:
            return str(mv.version)
    return None


def main() -> None:
    configure_mlflow()
    client = MlflowClient()
    if not (BUNDLED / "MLmodel").is_file():
        raise SystemExit(f"Modelo embalado não encontrado: {BUNDLED}. Rode tools/export_model.py antes.")
    existing = _bundled_version(client)
    if existing:
        print(f"Registry já contém a versão embalada v{existing} em Production; nada a fazer.")
        return
    # Preserva um modelo treinado pelo próprio usuário: se já há Production, não sobrescreve.
    current = production_version(client)
    if current:
        print(f"Registry já possui Production v{current} (treinado localmente); modelo embalado NÃO será registrado.")
        print("Dica: para repor pelo embalado, apague as versões deste Model Registry ou use outro MLFLOW_TRACKING_URI.")
        return
    # Registry vazio: simula uma promoção registrando o modelo embalado.
    mv = mlflow.register_model(model_uri=BUNDLED.as_uri(), name=MODEL_NAME)
    client.transition_model_version_stage(MODEL_NAME, mv.version, "Production",
                                          archive_existing_versions=True)
    client.set_model_version_tag(MODEL_NAME, mv.version, TAG_KEY, TAG_VALUE)
    print(f"Registrado modelo embalado -> {MODEL_NAME} v{mv.version} (Production).")
    print(f"predict.py e a API usarão {production_version(client)}")


if __name__ == "__main__":
    main()