# QuantumFinance — entrega MLOps

Projeto de demonstração **local**, baseado no dataset acadêmico [Credit Score Classification (Kaggle)](https://www.kaggle.com/datasets/parisrohan/credit-score-classification) e no notebook `analise_score_credito.ipynb` fornecido pelo autor. O projeto **não** afirma que há integração com transações atuais. Existe um endpoint público Azure ML separado, que não executa esta API local nem seu throttling.

## O que este pacote permite em qualquer máquina

- **Usar a API imediatamente, sem dataset e sem treinar.** O modelo promovido (XGBoost v1, treinado no dataset da disciplina) vem embalado em `models/credit-score-v1/`; `tools/seed_registry.py` o registra como `Production` no MLflow local.
- **Retreinar** com o dataset da disciplina (fornecido pelo curso; contém PII e fica fora do pacote) ou com o CSV demo sintético `data/raw/demo_train.csv` (sem PII, incluído no pacote).
- **Ver a execução da API com logs de conexão**: o notebook `notebooks/execucao_api.ipynb` já vem **executado** com 10 chamadas reais (200/401/400/429/503) e os respectivos logs do uvicorn; reexecutável em qualquer máquina.

Requisitos: **Python 3.11** em Windows/Linux/macOS. Na primeira execução, `setup_local.py` baixa as dependências listadas em `requirements.txt`.

## Início rápido — API sem dataset

Windows (PowerShell):

```powershell
python tools/setup_local.py
$env:QF_API_KEYS = 'uma-chave-local-longa-e-aleatoria'
.\.venv\Scripts\python.exe -m uvicorn src.api:app --host 127.0.0.1 --port 8000
```

Linux/macOS (terminal):

```bash
python3.11 tools/setup_local.py
export QF_API_KEYS='uma-chave-local-longa-e-aleatoria'
./.venv/bin/python -m uvicorn src.api:app --host 127.0.0.1 --port 8000
```

`tools/setup_local.py` cria `.venv`, instala `requirements.txt` e registra o modelo embalado. A API fica em `http://127.0.0.1:8000`, com documentação interativa em `http://127.0.0.1:8000/docs`. Chamada de exemplo:

```powershell
curl.exe -X POST 'http://127.0.0.1:8000/credit-score/v1/predict' `
  -H 'Content-Type: application/json' `
  -H 'X-API-Key: uma-chave-local-longa-e-aleatoria' `
  --data-binary '@examples/cliente.json'
```

Contrato completo, respostas, erros e FAQ: [docs/api.md](docs/api.md).

## Retreinar (opcional)

O retreino **não** é necessário para usar a API. Dois caminhos:

1. **CSV da disciplina** (favor usar quando estiver disponível no curso):

   ```powershell
   .\.venv\Scripts\python.exe -m src.train --data '<caminho-do-seu-train.csv>'
   ```

   O CSV contém `Name`, `SSN` e `Customer_ID`: mantenha-o **fora** do Git e do pacote. O treino registra a nova versão no Registry local e só promove se F1 ≥ 0,70 **e** melhoria ≥ 0,005 sobre Production. Veja os critérios em `src/train.py`.

2. **CSV demo sintético** (incluído, sem PII) para exercitar o pipeline em qualquer máquina:

   ```powershell
   .\.venv\Scripts\python.exe -m src.train --data 'data/raw/demo_train.csv' --quick
   ```

   O demo é pequeno e artificial; na grade rápida ele costuma promover (o modelo do demo **substituirá** o embalado no Registry local — se quiser preservar o embalado, rode o demo com outro `MLFLOW_TRACKING_URI`). O resultado real do treino completo no CSV da disciplina está em [docs/validacao_local.md](docs/validacao_local.md).

Em Linux/macOS, troque `.\.venv\Scripts\python.exe` por `./.venv/bin/python` e `$env:` por `export`. Se treino e API rodarem em ambientes diferentes, configure o mesmo backend via `MLFLOW_TRACKING_URI`.

## Testes e evidências

- **Notebook de execução da API:** abra `notebooks/execucao_api.ipynb` (já executado no pacote). Ele sobe o servidor, faz 10 chamadas HTTP reais (health 200, sem chave 401, chave inválida 401, predição 200, JSON inválido 400, campo ausente 400, limite 429 com `Retry-After` e registro sem modelo 503) e mostra o **access log do uvicorn** de cada caso. Para reexecutar em qualquer máquina: `python -m pip install -r requirements-notebook.txt` e `jupyter notebook notebooks/execucao_api.ipynb`. Os logs copiados para `docs/evidencias/` (`execucao_api_principal.log`, `execucao_api_sem_modelo.log`) também estão no pacote.
- **Testes:** `.\.venv\Scripts\python.exe -m pytest -q` (5 testes).
- **Validação HTTP real:** após ter um modelo em Production, `.\.venv\Scripts\python.exe tools/validate_local.py` comprova 200/401/429 com servidor temporário; `tools/gerar_evidencias.py` ainda grava logs, JSON e capturas em `docs/evidencias/` (exige Microsoft Edge no Windows).
- **Resultados documentados:** [docs/validacao_local.md](docs/validacao_local.md) — treino completo no CSV da disciplina promoveu **XGBoost v1** (F1 de validação **0,7064**); respostas **200/401/429** registradas. A v1 embalada em `models/credit-score-v1/` é a mesma versão promovida por esse treino.
- **Inspeção do Tracking:** `.\.venv\Scripts\python.exe -m mlflow ui --backend-store-uri ./mlruns` (http://127.0.0.1:5000).

## Entregáveis

1. Organização/ciclo de vida: [docs/arquitetura.md](docs/arquitetura.md).
2. Treinamento, MLflow tracking, decisão e promoção: [src/train.py](src/train.py).
3. Inferência a partir do último `Production`: [src/predict.py](src/predict.py).
4. Contrato, exemplos, erros, FAQ e inicialização: [docs/api.md](docs/api.md). Para a aba **Testar** do Azure ML mostrada na captura, use [examples/azure_endpoint_input.json](examples/azure_endpoint_input.json), que é diferente do payload da API local. Para habilitar throttling **no Azure**, há um [passo a passo do API Management](docs/throttling_azure.md) e uma [política XML](deploy/apim-policy.xml): são templates, **não estão implantados**.

## Segurança

O CSV real tem `Name`, `SSN` e `Customer_ID`: não vai no pacote. Arquivo `.env`, `mlruns`, o modelo binário embalado, dataset e saídas de clientes estão ignorados pelo Git (o modelo embalado entra **somente** no ZIP). Nunca suba o exemplo local na internet sem TLS, gerenciamento de chaves, rate limiting global e avaliação de privacidade. O script `score.py` da pasta original do autor descreve um fluxo Azure distinto. Capturas do Azure confirmam autenticação `Key`, endpoint `/score` e implantação v9, mas mostram **0% de tráfego roteado para v9** e não comprovam throttling por parceiro. Consulte [docs/api.md](docs/api.md) antes de tratar o Azure como API pronta para os parceiros.