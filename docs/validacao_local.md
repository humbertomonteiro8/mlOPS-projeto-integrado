# Evidências de validação da entrega local — 06/10/2026

## Treinamento completo com limiar padrão

Comando executado pelo autor no diretório deste repositório (em outra máquina, troque o caminho pelo CSV da disciplina):

```powershell
.\.venv\Scripts\python.exe -m src.train --data '<caminho-do-seu-train.csv>'
```

O CSV acadêmico original ficou **fora do repositório/ZIP** (contém dados pessoais). Após os filtros de consistência: **80.036 registros**, sendo **63.989 para treino** e **16.047 para validação**. O particionamento e a validação cruzada são agrupados por `Customer_ID` para impedir que meses do mesmo cliente sejam usados simultaneamente em treino/validação. Cada candidato foi rastreado numa run MLflow com parâmetros, métricas, SHA-256 do arquivo, contagens, relatório por classe, matriz de confusão e Pipeline serializado. O conteúdo do dataset não foi publicado nos artefatos.

| Candidato | F1-weighted treino | F1-weighted validação | Gap | Acurácia validação |
|---|---:|---:|---:|---:|
| Random Forest | 0,6346 | 0,6013 | 0,0333 | 0,6317 |
| XGBoost | 0,7396 | 0,7064 | 0,0332 | 0,7066 |
| LightGBM | 0,7477 | 0,7086 | 0,0391 | 0,7082 |

**Decisão efetivamente executada:** os dois melhores passaram no mínimo **F1 ≥ 0,70**. A diferença entre LightGBM e XGBoost (≈ 0,0022) é menor que **0,005**, portanto houve empate técnico; pelo critério documentado de **menor gap absoluto treino/validação**, venceu **XGBoost**. O MLflow registrou `quantumfinance-credit-score`, **versão 1**, estágio **Production**, no Registry **local** `./mlruns`. O número `1` desse Registry **não está vinculado** à implantação Azure `quantumfinance-credit-score-v9` e não prova qual versão está servida lá. Um novo treinamento registra nova versão somente se atingir o mínimo e superar a versão anterior no mesmo holdout em pelo menos 0,005.

O teste reduzido anterior (150 clientes com `--min-f1 0`) teve seus artefatos removidos; a v1 atual acima decorre **exclusivamente do treino completo com o limiar padrão**. Os artefatos binários e `mlruns/` não estão no ZIP; para reproduzir, execute o comando acima com o CSV original.

## Testes automatizados e HTTP real

`python -m pytest -q`: **5 testes passaram** (avisos de depreciação de dependências, sem falhas).

Após a promoção, foi executado `.\.venv\Scripts\python.exe tools/validate_local.py`. Esse script sobe temporariamente `uvicorn` em `127.0.0.1` com chave **aleatória, não salva**, e diminui **apenas na sessão de demonstração** o limite para 2 chamadas/minuto por chave; não altera o padrão de produção local (60/min e 10/s):

| Teste | HTTP observado |
|---|---:|
| `GET /credit-score/v1/health` | 200 |
| `POST /credit-score/v1/predict` sem `X-API-Key` | 401 |
| Primeira chamada válida com chave | 200 |
| Segunda chamada válida com chave | 200 |
| Terceira chamada válida com mesma chave | 429 (`Retry-After` informado) |

Resposta da primeira chamada válida, com o corpo de `examples/cliente.json`:

```json
{"credit_score_predicted":"Good","model_version":"1","request_id":"teste-local"}
```

O servidor do teste foi encerrado ao final. O resultado demonstra **o fluxo local**: treino → promoção → carregamento por versão Production → API com chave e throttling. O endpoint Azure ML bruto não recebe throttling deste fluxo; para limite por parceiro **na nuvem**, o **Azure API Management** foi aplicado e testado com **429 real** — veja [docs/throttling_azure.md](throttling_azure.md) e as evidências em `docs/evidencias/apim_teste_http.log` e `apim_teste_throttle.log`.

## Capturas e logs salvos (pasta `docs/evidencias/`)

Além do script acima, `tools/gerar_evidencias.py` repete as chamadas reais e grava as evidências em arquivos:

| Arquivo | O que é |
|---|---|
| `docs/evidencias/captura_respostas_http.png` | Captura (1440×1200) do relatório HTML com as cinco respostas HTTP reais |
| `docs/evidencias/captura_swagger_local.png` | Captura da documentação OpenAPI gerada pelo próprio servidor em `/docs` |
| `docs/evidencias/execucao_http.log` | Log textual da sessão (`> ` requisição, `< ` resposta), sem chaves |
| `docs/evidencias/consumo_api.json` | Registro estruturado das requisições: método, rota, status, headers e corpo |
| `docs/evidencias/relatorio_http.html` | Página de origem da captura de respostas |
| `docs/evidencias/execucao_api_principal.log` | Access log do uvicorn gerado pelo notebook de execução (casos 1–9) |
| `docs/evidencias/execucao_api_sem_modelo.log` | Access log do uvicorn do servidor sem modelo (caso 10, 503) |

O notebook `notebooks/execucao_api.ipynb` (já executado no pacote) é a demonstração completa: inicia o servidor, executa **10 chamadas reais** (200, 401, 401, 200, 400, 400, 200, 200, 429, 503), exibe respostas e **log de conexão** de cada caso, e copia os logs para `docs/evidencias/`. Ele é reexecutável com `requirements-notebook.txt`.

Comando que as gerou:

```powershell
.\.venv\Scripts\python.exe tools/gerar_evidencias.py
```

O log confirma os status **200 → 200 → 429** para as três chamadas com a mesma chave, com `Retry-After: 57` na resposta limitada, e **401** na chamada sem chave. A chave usada é aleatória por execução e **não é gravada** em nenhum arquivo (`<omitida>`). Essas são evidências do **servidor local**, não do endpoint Azure.

## Reprodução em outra máquina (fluxo portável do pacote)

O ZIP agora inclui o **mesmo** modelo promovido (`models/credit-score-v1/`) e um CSV demo sintético (`data/raw/demo_train.csv`). Em qualquer máquina com Python 3.11:

1. `python tools/setup_local.py` — cria `.venv`, instala `requirements.txt` e registra o modelo embalado como Production.
2. Iniciar a API e chamar `/credit-score/v1/predict` com `examples/cliente.json` — **sem dataset e sem treino**.

Teste executado com um `MLFLOW_TRACKING_URI` **limpo** (simulando outra máquina):

| Passo | Resultado |
|---|---|
| `production_version` antes do seed | `None` |
| `python tools/seed_registry.py` | registrada v1 (Production) |
| Segunda execução do `seed_registry.py` | **não duplica** (idempotente); mantém v1 |
| `predict(examples/cliente.json)` | `{"credit_score_predicted": "Good", "model_version": "1"}` |

Retreino demonstrativo com o CSV demo em Registry limpo e grade `--quick`: Random Forest 0,6931 · XGBoost 0,6957 · LightGBM 0,7287 → **promovido LightGBM v1** (o demo é pequeno/artificial e serve para exercitar o pipeline). Importante: se a máquina **já tiver** um Production, `seed_registry.py` **não sobrescreve** — ele só registra o modelo embalado quando não há versão em Production, preservando modelos treinados pelo próprio usuário.
