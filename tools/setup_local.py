"""Preparação automática em qualquer SO (Windows/Linux/macOS) com Python 3.11.

Cria .venv, instala requirements e registra o modelo embalado como Production,
para usar predict.py e a API imediatamente (sem dataset e sem treinar).

Uso: python tools/setup_local.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"
BIN = VENV / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")


def run(args: list[str]) -> None:
    print(f"> {' '.join(map(str, args))}")
    subprocess.check_call([str(a) for a in args])


def main() -> None:
    if not (VENV / "pyvenv.cfg").exists():
        print("Criando ambiente virtual .venv ...")
        venv.EnvBuilder(with_pip=True).create(VENV)
    else:
        print(".venv já existe; reutilizando.")
    run([BIN, "-m", "pip", "install", "-q", "-r", ROOT / "requirements.txt"])
    run([BIN, ROOT / "tools" / "seed_registry.py"])
    print()
    print("Pronto! Para iniciar a API:")
    if os.name == "nt":
        print('  $env:QF_API_KEYS = "uma-chave-local-longa-e-aleatoria"')
        print("  .\\.venv\\Scripts\\python.exe -m uvicorn src.api:app --host 127.0.0.1 --port 8000")
    else:
        print('  export QF_API_KEYS="uma-chave-local-longa-e-aleatoria"')
        print("  ./.venv/bin/python -m uvicorn src.api:app --host 127.0.0.1 --port 8000")
    print("Documentação interativa: http://127.0.0.1:8000/docs")


if __name__ == "__main__":
    main()