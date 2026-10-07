"""Smoke test REAL da API local (HTTP) sem expor chaves ou dados pessoais.

Pré-requisito: executar primeiro `python -m src.train --data <csv>` e promover
um modelo pelo limiar padrão; então `python tools/validate_local.py`.
Sobe uvicorn em porta local temporária, valida health, 401, 200 e 429.
"""
from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    key = secrets.token_urlsafe(32)
    env = dict(os.environ, QF_API_KEYS=key, QF_RATE_PER_MINUTE="2", QF_RATE_PER_SECOND="10")
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.api:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        with httpx.Client(timeout=30) as client:
            for _ in range(60):
                if server.poll() is not None:
                    raise RuntimeError("Servidor encerrou antes de iniciar. Confira dependências e configuração.")
                try:
                    health = client.get(base + "/credit-score/v1/health")
                    break
                except httpx.ConnectError:
                    time.sleep(0.5)
            else:
                raise RuntimeError("Servidor não iniciou em 30 segundos")
            assert health.status_code == 200
            url = base + "/credit-score/v1/predict"
            payload = json.loads((ROOT / "examples/cliente.json").read_text(encoding="utf-8"))
            unauthorized = client.post(url, json=payload)
            assert unauthorized.status_code == 401, unauthorized.text
            headers = {"X-API-Key": key, "X-Request-Id": "teste-local"}
            first = client.post(url, json=payload, headers=headers)
            assert first.status_code == 200, first.text
            second = client.post(url, json=payload, headers=headers)
            assert second.status_code == 200, second.text
            throttled = client.post(url, json=payload, headers=headers)
            assert throttled.status_code == 429 and throttled.headers.get("Retry-After"), throttled.text
            print(json.dumps({
                "health": health.status_code,
                "sem_chave": unauthorized.status_code,
                "com_chave": first.status_code,
                "resposta": first.json(),
                "acima_do_limite": throttled.status_code,
                "retry_after_seconds": throttled.headers["Retry-After"],
                "limite_temporario_por_minuto": 2,
            }, ensure_ascii=False, indent=2))
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)


if __name__ == "__main__":
    main()
