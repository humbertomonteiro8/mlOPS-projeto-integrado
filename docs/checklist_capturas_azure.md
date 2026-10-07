# Checklist — Capturas do Portal Azure (entrega 4: "nuvem com imagens")

**Estado: núcleo capturado ✅ e camada APIM aplicada e evidenciada** (07/10/2026). O endpoint `mlw-quantumfinance-credit-ocqjl` está com `quantumfinance-credit-score-v9` em **100% do tráfego ao vivo**. O **Azure API Management** foi criado e configurado via CLI (`apim-quantumfinance-credit`, plano Consumption, mesma região), com política `rate-limit` por assinatura e um **429 real** demonstrado. As evidências programáticas estão nos JSONs/logs `docs/evidencias/apim_*.json`, `apim_teste_http.log` e `apim_teste_throttle.log`. As **capturas do portal (telas 7–11) continuam opcionais**: os recursos existem, então podem ser fotografadas se o professor pedir imagens do portal, mas não são mais necessárias para provar a entrega.

## Regras de privacidade (obrigatórias)

- **Nunca** mostre a chave (primária/secundária) do endpoint, da assinatura APIM nem tokens. Em telas que exibem chave (ex.: **Consumir**), **recorte ou desfoque** o valor e deixe apenas o rótulo (`Chave primária`, `Chave secundária`) e o modo `Key`.
- Não capture telas com dados pessoais. O body de teste é `examples/azure_endpoint_input.json` (sem `SSN`/`Name`/`Customer_ID`).
- Nome dos arquivos: **somente ASCII**, extensão `.png`, dentro de `docs/evidencias/`.
- Se algum passo não existir na sua assinatura (ex.: APIM), **não invente**: registre "não aplicável" aqui e ajuste a documentação em vez de deixar evidência falsa.

## Como capturar

1. Entre no **Azure ML Studio** com a conta dona do workspace `mlw-quantumfinance-credit-ocqjl`.
2. Siga a tabela abaixo; salve cada tela com o nome indicado.
3. Depois de capturar, rode `tools/package.py` (o ZIP já inclui as novas PNGs) e faça um commit.

## Núcleo (capturado)

| # | Tela a capturar | Caminho no portal | O que deve aparecer | Arquivo em `docs/evidencias/` |
|---|---|---|---|---|
| 1 | Lista de endpoints | Azure ML Studio → **Pontos de extremidade** | O cartão do endpoint `mlw-quantumfinance-credit-ocqjl` com estado **Healthy** e tipo Managed online endpoint | `captura_pontos_de_extremidade.png` |
| 2 | Detalhes do endpoint | Endpoint → aba **Detalhes** | Estado do endpoint, URI de consumo, deployment destacado | coberto por `captura_pontos_de_extremidade.png` (item 1); tela separada opcional |
| 3 | Tráfego ao vivo: 100% para v9 | Endpoint → **Detalhes → Atualizar tráfego** | Barra/porcentagem: `quantumfinance-credit-score-v9 = 100%` (e demais em 0) | `captura_trafego_100_porcento.png` |
| 4 | Deployments | Endpoint → aba **Deployments** (ou **Em implantação**) | v9 com estado **Healthy**, instância/CPU/região | `captura_deployments.png` |
| 5 | Consumir (auth Key) | Endpoint → aba **Consumir** | Endpoint URI, modo de autenticação **`Key`**; chaves **mascaradas** | `captura_consumir.png` |
| 6 | Testar (resposta real) | Endpoint → aba **Testar**, `quantumfinance-credit-score-v9`, input `examples/azure_endpoint_input.json` | Resposta `{"predictions":["Good"],"model_version":"1"}` (ou equivalente) | `captura_testar.png` |

> A captura 3 prova o roteamento; a 5 prova a autenticação por chave; a 6 prova o consumo real. A captura 4 mostra qual deployment atende (v9).

## Governança: camada APIM (aplicada via CLI — capturas opcionais)

A instância `apim-quantumfinance-credit`, a API, o Named Value, a política `rate-limit` e a assinatura `parceiro-exemplo` **já existem** e foram testados (ver [`docs/throttling_azure.md`](throttling_azure.md)). A prova atual é programática (JSONs/logs em `docs/evidencias/`). Se o professor exigir imagens do portal, capture a partir do **Portal Azure → API Management → apim-quantumfinance-credit**; caso contrário, estas cinco telas não são obrigatórias. Regras: chaves de assinatura sempre **mascaradas**; corpo de teste `examples/azure_endpoint_input.json` (sem PII).

| # | Tela a capturar | Caminho no portal | O que deve aparecer | Arquivo em `docs/evidencias/` |
|---|---|---|---|---|
| 7 | Instância APIM | Portal → **API Management** → sua instância → **Visão geral** | Instância criada, nome/região/SKU | `apim_01_overview.png` |
| 8 | API criada | APIM → **APIs** | `QuantumFinance Score` com operação **POST /predict** | `apim_02_api_criada.png` |
| 9 | Política rate-limit | API → **All operations → Inbound processing → Code editor** | `<rate-limit calls="60" renewal-period="60" ...>` (conforme `deploy/apim-policy.xml`) | `apim_03_politica_rate_limit.png` |
| 10 | Assinatura por parceiro | APIM → **Subscriptions** | Uma assinatura com scope na API QuantumFinance (chave **mascarada**) | `apim_04_subscriptions.png` |
| 11 | Teste de 429 | Postman/`curl` → gateway APIM `.../credit-score/v1/predict` | Com `calls="3"` temporário: a 4ª chamada retorna **429** (retorne a política a 60 depois) | `apim_05_teste_429.png` |

## Depois de capturar

1. `.\\.venv\\Scripts\\python.exe tools\\package.py` — regenera `QuantumFinance_MLOps_Entrega.zip` com as novas PNGs.
2. Commit: `git add docs/evidencias/ && git commit -m "Evidências do portal Azure (tráfego 100% v9, auth Key, resposta real)"`.
3. (Opcional) Atualize o parágrafo "Segurança na nuvem" de [`docs/api.md`](api.md) somente se o APIM tiver sido aplicado e testado com 429 real.