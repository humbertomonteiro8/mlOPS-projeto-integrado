"""Gera o único ZIP de entrega sem CSV real (PII), .env, mlruns ou .venv.

Inclui o modelo promovido (models/credit-score-v1), o CSV demo sintético,
o notebook de execução com logs e as ferramentas de preparação cross-platform.

Uso: python tools/package.py
"""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "QuantumFinance_MLOps_Entrega.zip"
FILES = [
    ".gitignore", ".env.example", "README.md", "requirements.txt",
    "requirements-notebook.txt",
    "docs/arquitetura.md", "docs/api.md", "docs/validacao_local.md", "docs/throttling_azure.md", "deploy/apim-policy.xml",
    "docs/evidencias/captura_respostas_http.png", "docs/evidencias/captura_swagger_local.png",
    "docs/evidencias/execucao_http.log", "docs/evidencias/consumo_api.json", "docs/evidencias/relatorio_http.html",
    "examples/cliente.json", "examples/azure_endpoint_input.json",
    "data/raw/README.md", "data/raw/demo_train.csv", "data/processed/README.md",
    "notebooks/README.md", "notebooks/execucao_api.ipynb", "models/README.md",
    "src/__init__.py", "src/features.py", "src/registry.py", "src/train.py",
    "src/predict.py", "src/api.py", "tests/test_project.py", "tools/package.py",
    "tools/setup_local.py", "tools/seed_registry.py", "tools/export_model.py",
    "tools/gerar_demo_csv.py", "tools/validate_local.py", "tools/gerar_evidencias.py",
    "tools/gerar_notebook.py",
]
# Logs de conexão gerados por notebooks/execucao_api.ipynb: entram se existirem.
OPTIONAL = {
    "docs/evidencias/execucao_api_principal.log",
    "docs/evidencias/execucao_api_sem_modelo.log",
}


def walk_dir(rel: str):
    """Lista arquivos de um diretório (inclusive o modelo embalado)."""
    base = ROOT / rel
    if not base.is_dir():
        return []
    return [p.relative_to(ROOT).as_posix() for p in sorted(base.rglob("*")) if p.is_file()]


with ZipFile(DEST, "w", ZIP_DEFLATED) as archive:
    for rel in FILES + walk_dir("models/credit-score-v1") + sorted(OPTIONAL):
        source = ROOT / rel
        if not source.is_file():
            if rel in OPTIONAL:
                continue
            raise SystemExit(f"Arquivo não encontrado: {rel}")
        archive.write(source, arcname=f"QuantumFinance_MLOps_Entrega/{rel}")
print(f"Criado: {DEST} ({DEST.stat().st_size} bytes)")