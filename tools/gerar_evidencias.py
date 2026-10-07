"""Captura HTTP real, logs sem segredos e screenshots via Edge headless.

Uso: python tools/gerar_evidencias.py
Pré-requisito: modelo aprovado no Registry local e Edge instalado para PNGs.
Os arquivos em docs/evidencias/ são derivados de chamadas reais ao uvicorn.
"""
from __future__ import annotations

import html
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "evidencias"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
# Perfil temporário do Edge: usa o diretório temporário padrão do SO.
TEMP = Path(tempfile.gettempdir()) / "opencode"


def capture(url: str, image: Path) -> None:
    if not EDGE.is_file():
        raise RuntimeError("Microsoft Edge não encontrado; não é possível capturar screenshot real")
    TEMP.mkdir(parents=True, exist_ok=True)
    profile = Path(tempfile.mkdtemp(prefix="qf-edge-", dir=TEMP))
    try:
        result = subprocess.run([
            str(EDGE), "--headless=new", "--disable-gpu", "--no-first-run",
            "--hide-scrollbars", "--window-size=1440,1200", "--force-device-scale-factor=1",
            "--virtual-time-budget=12000", f"--user-data-dir={profile}",
            f"--screenshot={image.resolve()}", url,
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        if result.returncode or not image.is_file() or image.stat().st_size < 1000:
            raise RuntimeError(f"Edge não gerou {image.name} (exit={result.returncode})")
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def as_entry(label: str, method: str, url: str, response: httpx.Response, header: str) -> dict:
    return {
        "teste": label,
        "metodo": method,
        "rota": url,
        "credencial_enviada": header,  # nunca registra o segredo real
        "status_http": response.status_code,
        "headers_resposta": {k: response.headers[k] for k in (
            "content-type", "x-request-id", "x-ratelimit-limit", "x-ratelimit-remaining", "retry-after"
        ) if k in response.headers},
        "corpo_resposta": response.json(),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
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
        with httpx.Client(timeout=60) as client:
            for _ in range(60):
                if server.poll() is not None:
                    raise RuntimeError("uvicorn encerrou antes de iniciar")
                try:
                    health = client.get(base + "/credit-score/v1/health")
                    break
                except httpx.ConnectError:
                    time.sleep(0.5)
            else:
                raise RuntimeError("uvicorn não iniciou em 30 segundos")
            payload = json.loads((ROOT / "examples" / "cliente.json").read_text(encoding="utf-8"))
            url = "/credit-score/v1/predict"
            authenticated = {"X-API-Key": key}
            unauthorized = client.post(base + url, json=payload, headers={"X-Request-Id": "evidencia-401"})
            ok = client.post(base + url, json=payload, headers={**authenticated, "X-Request-Id": "evidencia-200"})
            ok_again = client.post(base + url, json=payload, headers={**authenticated, "X-Request-Id": "evidencia-200b"})
            limited = client.post(base + url, json=payload, headers={**authenticated, "X-Request-Id": "evidencia-429"})
            statuses = [health.status_code, unauthorized.status_code, ok.status_code, ok_again.status_code, limited.status_code]
            if statuses != [200, 401, 200, 200, 429] or "retry-after" not in limited.headers:
                raise RuntimeError(f"Validação HTTP inesperada: {statuses}; nada será publicado")
            records = [
                as_entry("Health (liveness)", "GET", "/credit-score/v1/health", health, "nenhuma"),
                as_entry("Sem chave", "POST", url, unauthorized, "nenhuma"),
                as_entry("Com chave válida", "POST", url, ok, "<omitida>"),
                as_entry("Segunda chamada com chave", "POST", url, ok_again, "<omitida>"),
                as_entry("Terceira chamada com chave (limite 2/min)", "POST", url, limited, "<omitida>"),
            ]
            timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
            evidence = {"gerado_em_utc": timestamp, "origem": "HTTP real via httpx + uvicorn em 127.0.0.1",
                        "payload": "examples/cliente.json (sem PII)", "limite_apenas_no_teste": "2/min por chave; padrão da API 60/min + 10/s",
                        "requisicoes": records}
            (OUT / "consumo_api.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            lines = [f"QuantumFinance | evidência de consumo HTTP real | {timestamp}",
                     "Chaves omitidas; payload: examples/cliente.json; API local (NÃO Azure).", ""]
            for record in records:
                lines += [f"> {record['metodo']} {record['rota']} | X-API-Key: {record['credencial_enviada']}",
                          f"< HTTP {record['status_http']} | headers: {json.dumps(record['headers_resposta'], ensure_ascii=False)}",
                          f"< body: {json.dumps(record['corpo_resposta'], ensure_ascii=False)}", ""]
            transcript = "\n".join(lines)
            (OUT / "execucao_http.log").write_text(transcript + "\n", encoding="utf-8")
            cards = "\n".join(
                f"<section><h2>{html.escape(r['teste'])} · HTTP {r['status_http']}</h2>"
                f"<p>{r['metodo']} {html.escape(r['rota'])} — X-API-Key: {html.escape(r['credencial_enviada'])}</p>"
                f"<pre>{html.escape(json.dumps(r['corpo_resposta'], ensure_ascii=False, indent=2))}</pre>"
                f"<small>{html.escape(json.dumps(r['headers_resposta'], ensure_ascii=False))}</small></section>"
                for r in records
            )
            page = f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Evidências HTTP - QuantumFinance</title>
<style>body{{font:16px Segoe UI,Arial,sans-serif;background:#f5f7fb;color:#17263c;margin:30px auto;width:1250px}}
h1{{color:#075cb0}}section{{display:inline-block;vertical-align:top;background:white;border:1px solid #ccd9eb;
border-radius:8px;width:575px;min-height:140px;padding:14px;margin:6px}}section h2{{font-size:19px;margin:0 0 8px}}
pre{{white-space:pre-wrap;color:#003b75;background:#eff6ff;padding:9px;border-radius:5px}}small{{overflow-wrap:anywhere}}
footer{{margin-top:15px;color:#465c72}}</style>
<h1>QuantumFinance — consumo REAL da API local</h1>
<p>HTTP para uvicorn em 127.0.0.1, {html.escape(timestamp)} · sem chaves nem PII · body: examples/cliente.json</p>
{cards}<footer>Esta é uma captura de um relatório HTML gerado A PARTIR das respostas HTTP salvas em consumo_api.json.
Não é screenshot de Azure, Swagger ou console de desenvolvedor.</footer></html>"""
            report = OUT / "relatorio_http.html"
            report.write_text(page, encoding="utf-8")
            capture(report.resolve().as_uri(), OUT / "captura_respostas_http.png")
            capture(base + "/docs", OUT / "captura_swagger_local.png")
            print(transcript)
            print("Capturas salvas em docs/evidencias/captura_respostas_http.png e captura_swagger_local.png")
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)


if __name__ == "__main__":
    main()
