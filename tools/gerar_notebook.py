"""Gera notebooks/execucao_api.ipynb (execução real da API com logs).

O código das células fica aqui como strings, para manutenção sem editar JSON.
Após gerar, rode:  python -m nbconvert --to notebook --execute --inplace notebooks/execucao_api.ipynb

Uso: python tools/gerar_notebook.py
"""
from __future__ import annotations

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "notebooks" / "execucao_api.ipynb"

MD_TITLE = r"""# QuantumFinance — Execução real da API com logs de conexão

Este notebook **inicia o servidor FastAPI** (`src/api.py`) em uma porta aleatória, faz
chamadas **HTTP reais** e mostra, para cada caso, a **resposta** e o **log de conexão**
(access log do uvicorn). Inclui casos de **sucesso** e de **falha**:

| # | Cenário | Esperado | O que comprova |
|---|---|---|---|
| 1 | `GET /health` | **200** | Liveness do processo |
| 2 | `POST /predict` sem `X-API-Key` | **401** | Autenticação exige chave |
| 3 | `POST /predict` com chave inválida | **401** | Chave inválida é rejeitada |
| 4 | `POST /predict` com chave válida (1ª) | **200** | Predição `Good`, versão `Production` |
| 5 | `POST /predict` com JSON inválido | **400** | Validação de payload |
| 6 | `POST /predict` faltando campo obrigatório | **400** | Esquema estrito |
| 7 | `POST /predict` chave válida (2ª) | **200** | `X-RateLimit-Remaining` decresce |
| 8 | `POST /predict` chave válida (3ª) | **200** | Limite de demonstração: 3/min |
| 9 | `POST /predict` 4ª chamada no minuto | **429** | Throttling + `Retry-After` |
| 10 | `POST /predict` (Registry sem Production) | **503** | `model_not_available` |
"""

MD_PREREQ = r"""## Pré-requisitos e segurança

- Dependências de `requirements.txt` (ex.: `python tools/setup_local.py`).
- Modelo em `Production` no MLflow local (o `tools/seed_registry.py` registra o modelo embalado) — **sem isso**, o caso 10 é o único esperado como `503` para `model_not_available`; os demais continuam válidos.
- Para reexecutar/editar este notebook, use `requirements-notebook.txt` (ferramentas Jupyter opcionais).

Segurança: a chave da API é **aleatória por execução** e **não é impressa**.
Os payloads usam `examples/cliente.json` (sem PII). O acesso log do uvicorn mostra apenas
método/rota/status — **nunca** header de chave.
"""

CODE_SETUP = r'''"""Célula de setup: importa, localiza a raiz e define os helpers usados nas próximas células."""
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

API_KEY = secrets.token_urlsafe(24)  # chave aleatória desta execução; não será impressa

def find_root():
    here = Path.cwd()
    for cand in (here, here.parent, here.parent.parent):
        if (cand / "src" / "api.py").is_file():
            return cand.resolve()
    raise SystemExit("Não encontrei src/api.py a partir do diretório atual.")

ROOT = find_root()
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]

def start_server(env_extra=None, log_suffix="principal"):
    """Sobe uvicorn em porta aleatória, com chave e limite de demonstração, gravando o log."""
    port = free_port()
    log_path = Path(tempfile.gettempdir()) / f"qf-api-{log_suffix}.log"
    log_file = open(log_path, "w", encoding="utf-8")
    env = dict(os.environ)
    env.update({
        "QF_API_KEYS": API_KEY,
        "QF_RATE_PER_MINUTE": "3",     # somente nesta demonstração (a API padrão usa 60/min)
        "QF_RATE_PER_SECOND": "10",
        "PYTHONUNBUFFERED": "1",       # garante o access log visível no arquivo
        "PYTHONWARNINGS": "ignore",    # logs de conexão limpos (só uvicorn)
    })
    if env_extra:
        env.update(env_extra)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.api:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "info"],
        cwd=str(ROOT), env=env, stdout=log_file, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    with httpx.Client(timeout=30) as client:
        for _ in range(60):
            if proc.poll() is not None:
                log_file.close()
                raise RuntimeError("uvicorn encerrou durante a inicialização")
            try:
                if client.get(base + "/credit-score/v1/health").status_code == 200:
                    break
            except httpx.ConnectError:
                time.sleep(0.5)
        else:
            log_file.close()
            raise RuntimeError("Servidor não respondeu em 30 segundos")
    return proc, base, log_path, log_file

def log_new(log_path, consumed):
    """Retorna novas linhas do log e o novo offset consumido."""
    time.sleep(0.25)  # dá tempo do access log ser gravado
    data = Path(log_path).read_text(encoding="utf-8", errors="replace")
    return data[consumed:], len(data)

def run_case(number, title, expected, resp):
    status = resp.status_code
    verdict = "OK" if status == expected else "DIVERGENTE"
    headers = {k: resp.headers[k] for k in
               ("content-type", "x-request-id", "x-ratelimit-limit", "x-ratelimit-remaining", "retry-after")
               if k in resp.headers}
    print(f"Caso {number:02d} — {title}")
    print(f"  esperado {expected} | recebido {status} [{verdict}]")
    print(f"  headers: {json.dumps(headers, ensure_ascii=False)}")
    print(f"  body   : {resp.text}")
'''

CODE_START = r'''"""Inicia o servidor principal e descarta as linhas de inicialização do log."""
proc, base, log_path, log_file = start_server(log_suffix="principal")
consumed = len(Path(log_path).read_text(encoding="utf-8", errors="replace"))
print(f"Servidor principal: {base}")
print("Log de conexão:     arquivo temporário do SO (exibido inline abaixo)")
print("Chave da API:       (aleatória, omitida)")
url = base + "/credit-score/v1/predict"
payload = json.loads((ROOT / "examples" / "cliente.json").read_text(encoding="utf-8"))
payload_sem_campo = {k: v for k, v in payload.items() if k != "Age"}
'''

CODE_CASES = r'''"""Executa os 9 cenários (sucesso e falha) mostrando resposta e log de conexão."""
with httpx.Client(timeout=30) as client:
    def caso(number, title, expected, resp):
        run_case(number, title, expected, resp)

    resp = client.get(base + "/credit-score/v1/health", headers={"X-Request-Id": "caso-01"})
    caso(1, "GET /health (liveness)", 200, resp)
    print(); print("  --- log de conexão ---")
    tail, consumed = log_new(log_path, consumed)
    for line in tail.splitlines():
        print("   ", line)

    resp = client.post(url, json=payload, headers={"X-Request-Id": "caso-02"})
    caso(2, "POST /predict sem X-API-Key", 401, resp)
    print(); print("  --- log de conexão ---")
    tail, consumed = log_new(log_path, consumed)
    for line in tail.splitlines():
        print("   ", line)

    resp = client.post(url, json=payload, headers={"X-API-Key": "chave-errada", "X-Request-Id": "caso-03"})
    caso(3, "POST /predict com chave inválida", 401, resp)
    print(); print("  --- log de conexão ---")
    tail, consumed = log_new(log_path, consumed)
    for line in tail.splitlines():
        print("   ", line)

    resp = client.post(url, json=payload, headers={"X-API-Key": API_KEY, "X-Request-Id": "caso-04"})
    caso(4, "POST /predict com chave válida (1ª chamada)", 200, resp)
    print(); print("  --- log de conexão ---")
    tail, consumed = log_new(log_path, consumed)
    for line in tail.splitlines():
        print("   ", line)

    resp = client.post(url, content=b'{isto nao eh um json valido',
                       headers={"X-API-Key": API_KEY, "X-Request-Id": "caso-05",
                                "Content-Type": "application/json"})
    caso(5, "POST /predict com JSON inválido", 400, resp)
    print(); print("  --- log de conexão ---")
    tail, consumed = log_new(log_path, consumed)
    for line in tail.splitlines():
        print("   ", line)

    resp = client.post(url, json=payload_sem_campo, headers={"X-API-Key": API_KEY, "X-Request-Id": "caso-06"})
    caso(6, "POST /predict faltando campo obrigatório (Age)", 400, resp)
    print(); print("  --- log de conexão ---")
    tail, consumed = log_new(log_path, consumed)
    for line in tail.splitlines():
        print("   ", line)

    resp = client.post(url, json=payload, headers={"X-API-Key": API_KEY, "X-Request-Id": "caso-07"})
    caso(7, "POST /predict chave válida (2ª chamada — limite 3/min)", 200, resp)
    print(); print("  --- log de conexão ---")
    tail, consumed = log_new(log_path, consumed)
    for line in tail.splitlines():
        print("   ", line)

    resp = client.post(url, json=payload, headers={"X-API-Key": API_KEY, "X-Request-Id": "caso-08"})
    caso(8, "POST /predict chave válida (3ª chamada — limite esgotado)", 200, resp)
    print(); print("  --- log de conexão ---")
    tail, consumed = log_new(log_path, consumed)
    for line in tail.splitlines():
        print("   ", line)

    resp = client.post(url, json=payload, headers={"X-API-Key": API_KEY, "X-Request-Id": "caso-09"})
    caso(9, "POST /predict 4ª chamada no minuto — throttling", 429, resp)
    print(); print("  --- log de conexão ---")
    tail, consumed = log_new(log_path, consumed)
    for line in tail.splitlines():
        print("   ", line)
'''

CODE_MODEL = r'''"""Caso 10: 503 model_not_available — servidor apontando para um Registry vazio."""
empty_store = Path(tempfile.mkdtemp(prefix="qf-empty-store-"))
(empty_store / "dummy").mkdir(parents=True, exist_ok=True)
proc2, base2, log2_path, log2_file = start_server(
    {"MLFLOW_TRACKING_URI": empty_store.as_uri(), "QF_RATE_PER_MINUTE": "60"},
    log_suffix="sem-modelo")
consumed2 = len(Path(log2_path).read_text(encoding="utf-8", errors="replace"))
with httpx.Client(timeout=30) as client:
    resp = client.post(base2 + "/credit-score/v1/predict", json=payload,
                       headers={"X-API-Key": API_KEY, "X-Request-Id": "caso-10"})
    run_case(10, "POST /predict sem versão Production no Registry", 503, resp)
print(); print("  --- log de conexão (servidor sem modelo) ---")
tail, _ = log_new(log2_path, consumed2)
for line in tail.splitlines():
    print("   ", line)
'''

CODE_STOP = r'''"""Encerra os servidores (chaves temporárias descartadas) e copia os logs para docs/evidencias/."""
import shutil

for proc_, log_file_ in ((proc, log_file), (proc2, log2_file)):
    proc_.terminate()
    try:
        proc_.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc_.kill()
        proc_.wait(timeout=5)
    log_file_.close()

evid = ROOT / "docs" / "evidencias"
evid.mkdir(parents=True, exist_ok=True)
for src, dst in ((log_path, evid / "execucao_api_principal.log"),
                 (log2_path, evid / "execucao_api_sem_modelo.log")):
    shutil.copyfile(src, dst)

print("Servidores encerrados. Chaves temporárias descartadas.")
print("Logs de conexão copiados para:")
print("  docs/evidencias/execucao_api_principal.log")
print("  docs/evidencias/execucao_api_sem_modelo.log")
'''

MD_END = r"""## Leitura dos resultados

- **Autenticação**: sem chave e com chave inválida → **401** `invalid_api_key`; com a chave certa → **200**.
- **Validação**: JSON quebrado e campo ausente → **400** `invalid_payload` (validado antes do rate limit).
- **Throttling**: com o limite **temporário de 3 chamadas/minuto** deste notebook, a 1ª e a 2ª retornam
  `X-RateLimit-Remaining` decrescente (`2`→`1`→`0`) e a 4ª chamada no minuto retorna **429**
  `rate_limit_exceeded` com `Retry-After` (a API padrão usa 60/min e 10/s por chave).
- **Disponibilidade do modelo**: sem versão `Production` no Registry → **503** `model_not_available`.
- Os **logs de conexão** acima vêm do próprio uvicorn (access log), gravados em arquivo e reproduzidos aqui.

Contrato completo: [`docs/api.md`](../docs/api.md).
"""


def build() -> None:
    cells = [
        new_markdown_cell(MD_TITLE),
        new_markdown_cell(MD_PREREQ),
        new_code_cell(CODE_SETUP),
        new_code_cell(CODE_START),
        new_code_cell(CODE_CASES),
        new_code_cell(CODE_MODEL),
        new_code_cell(CODE_STOP),
        new_markdown_cell(MD_END),
    ]
    nb = new_notebook(cells=cells, metadata={"kernelspec": {
        "display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.11"}})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(nb, OUT)
    print(f"Gerado: {OUT} ({len(cells)} células)")


if __name__ == "__main__":
    build()