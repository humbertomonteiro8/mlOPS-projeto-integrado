"""Demonstra o rate-limit (429) do gateway APIM QuantumFinance.

Procedimento seguro e reproduzivel:
  1) Envia a politica com calls=\"3\" (temporario) via API de management (PUT + If-Match *).
  2) Dispara N chamadas com a mesma assinatura de parceiro; a excedente deve dar HTTP 429.
  3) Restaura a politica para calls=\"60\" e valida o conteudo aplicado.

Variaveis de ambiente (segredos via ambiente, nunca no codigo):
  QF_AZ_TOKEN        token de management:  az account get-access-token --resource https://management.azure.com
  QF_SUBSCRIPTION    id da assinatura Azure
  QF_RESOURCE_GROUP  ex.: rg-quantumfinance-mlops
  QF_APIM_NAME       ex.: apim-quantumfinance-credit
  QF_API_ID          ex.: quantumfinance-credit
  QF_APIM_GATEWAY    ex.: https://apim-quantumfinance-credit.azure-api.net
  QF_APIM_SUB_KEY    chave de assinatura APIM do parceiro
  QF_POLICY_PATH     (opcional) deploy/apim-policy.xml
  QF_BODY_PATH       (opcional) examples/azure_endpoint_input.json

Uso:
  python tools/testar_throttle_apim.py
Se nenhum 429 for observado, o script sai com codigo 1.
"""
import os
import sys
import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

TOKEN = os.environ["QF_AZ_TOKEN"]
SUBSCRIPTION = os.environ["QF_SUBSCRIPTION"]
RG = os.environ["QF_RESOURCE_GROUP"]
APIM = os.environ["QF_APIM_NAME"]
API_ID = os.environ["QF_API_ID"]
GATEWAY = os.environ["QF_APIM_GATEWAY"].rstrip("/")
SUB_KEY = os.environ["QF_APIM_SUB_KEY"]
POLICY_PATH = os.environ.get("QF_POLICY_PATH", "deploy/apim-policy.xml")
BODY_PATH = os.environ.get("QF_BODY_PATH", "examples/azure_endpoint_input.json")
API_VERSION = "api-version=2022-08-01"
POLICY_URL = (
    "https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
    "/providers/Microsoft.ApiManagement/service/{svc}/apis/{api}/policies/policy?{ver}"
).format(sub=SUBSCRIPTION, rg=RG, svc=APIM, api=API_ID, ver=API_VERSION)


def _rest(method: str, url: str, body: bytes | None = None):
    req = urllib.request.Request(url, method=method, data=body)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Content-Type", "application/json")
    if method == "PUT":
        req.add_header("If-Match", "*")  # atualizacao de recurso existente exige ETag
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _policy_body(calls: int) -> bytes:
    xml = open(POLICY_PATH, encoding="utf-8-sig").read()
    xml = xml.replace('calls="60"', f'calls="{calls}"')
    return json.dumps({"properties": {"format": "rawxml", "value": xml}}).encode("utf-8")


def _gateway_call(index: int):
    payload = open(BODY_PATH, "rb").read()
    req = urllib.request.Request(GATEWAY + "/credit-score/v1/predict", data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Ocp-Apim-Subscription-Key", SUB_KEY)
    try:
        with urllib.request.urlopen(req, timeout=150) as resp:
            status, headers, raw = resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        status, headers, raw = e.code, dict(e.headers), e.read()
    body = raw.decode("utf-8", errors="replace")[:160]
    rl = " | ".join(
        f"{k}: {headers.get(k)}"
        for k in ("X-RateLimit-Limit", "X-RateLimit-Remaining", "Retry-After")
        if headers.get(k)
    )
    print(f"  chamada {index}: HTTP {status} || {rl} || {body}")
    return status


def main() -> int:
    print("=" * 70)
    print(f"Teste de throttling APIM - {datetime.now(timezone.utc).isoformat()} UTC")
    print(f"Gateway: {GATEWAY}")
    try:
        status, _ = _rest("PUT", POLICY_URL, _policy_body(3))
        print(f"[1] politica calls=3 aplicada (HTTP {status})")
        if status not in (200, 201):
            print("Falha ao aplicar politica calls=3; abortando (politica pode ter ficado inconsistente).")
            return 1
        time.sleep(5)  # deixa o gateway consolidar a mudanca (Consumption)
        print("[2] chamadas rapidas com a mesma assinatura:")
        statuses = [_gateway_call(i) for i in range(1, 6)]
        had_429 = 429 in statuses
        print(f"    429 observado: {had_429}")
        status, _ = _rest("PUT", POLICY_URL, _policy_body(60))
        print(f"[3] politica restaurada para calls=60 (HTTP {status})")
        st, raw = _rest("GET", POLICY_URL)
        if st == 200:
            value = json.loads(raw.decode("utf-8-sig"))["properties"]["value"]
            ok60 = 'calls="60"' in value
            print(f"    validacao: calls=\"60\" presente = {ok60}")
        else:
            print(f"    validacao: GET da politica falhou (HTTP {st})")
        print("=" * 70)
        return 0 if had_429 else 1
    except Exception as exc:  # noqa: BLE001 - garante tentativa de restauracao
        print(f"ERRO durante o teste: {exc}")
        try:
            status, _ = _rest("PUT", POLICY_URL, _policy_body(60))
            print(f"[fallback] politica restaurada para calls=60 (HTTP {status})")
        except Exception as e2:  # noqa: BLE001
            print(f"[fallback] falha ao restaurar politica: {e2}")
        return 1


if __name__ == "__main__":
    sys.exit(main())