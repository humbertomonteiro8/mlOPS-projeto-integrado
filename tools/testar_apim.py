"""Testa o gateway Azure API Management (APIM) do QuantumFinance.

Fluxo (sem modificar a politica):
  1) POST sem chave de assinatura          -> espera 401 (Subscription required)
  2) POST com chave de assinatura correta  -> espera 200 + predicao (prova politica/backend)
  3) POST com chave errada                 -> espera 401

Variaveis de ambiente (sem segredos no codigo):
  QF_APIM_GATEWAY   ex.: https://apim-quantumfinance-credit.azure-api.net
  QF_APIM_SUB_KEY   chave de assinatura APIM do parceiro (segredo, via ambiente)
  QF_APIM_BODY      (opcional) caminho do payload; padrao examples/azure_endpoint_input.json

Uso:
  $env:QF_APIM_GATEWAY='https://...azure-api.net'
  $env:QF_APIM_SUB_KEY='<chave>'
  python tools/testar_apim.py
Saida nao expoe a chave de assinatura nem a chave do backend.
"""
import os
import sys
import json
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone

GATEWAY = os.environ["QF_APIM_GATEWAY"].rstrip("/")
SUB_KEY = os.environ.get("QF_APIM_SUB_KEY", "")
BODY = os.environ.get("QF_APIM_BODY", "examples/azure_endpoint_input.json")
PATH = "/credit-score/v1/predict"
URL = GATEWAY + PATH


def call(sub_key: str | None, label: str, expected: int):
    payload = open(BODY, "rb").read()
    req = urllib.request.Request(URL, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    if sub_key:
        req.add_header("Ocp-Apim-Subscription-Key", sub_key)
    try:
        with urllib.request.urlopen(req, timeout=150) as resp:
            status = resp.status
            headers = dict(resp.headers)
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        status = e.code
        headers = dict(e.headers)
        body = e.read().decode("utf-8", errors="replace")
    ok = status == expected
    print(f"-- {label}: HTTP {status} (esperado {expected}) -> {'OK' if ok else 'FALHOU'}")
    interesting = {
        "X-RateLimit-Limit": headers.get("X-RateLimit-Limit"),
        "X-RateLimit-Remaining": headers.get("X-RateLimit-Remaining"),
        "Retry-After": headers.get("Retry-After"),
    }
    for k, v in interesting.items():
        if v:
            print(f"   {k}: {v}")
    print(f"   body: {body[:200]}")
    return ok


def main() -> int:
    print("=" * 70)
    print(f"Teste APIM QuantumFinance - {datetime.now(timezone.utc).isoformat()} UTC")
    print(f"Gateway: {URL}")
    if not SUB_KEY:
        print("ATENCAO: QF_APIM_SUB_KEY vazia; a assinatura correta nao sera testada.") 
    results = [
        call(None, "1) POST sem chave de assinatura", 401),
        call(SUB_KEY, "2) POST com chave correta", 200),
        call("chave-errada", "3) POST com chave errada", 401),
    ]
    ok = all(results)
    print("=" * 70)
    print(f"Resultado geral: {'OK - gateway APIM funcionando' if ok else 'FALHOU - conferir'} ")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())