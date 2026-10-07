# Entregável 4 — API QuantumFinance (execução local)

**Servidor local:** `http://127.0.0.1:8000`. **Endpoint Azure ML mostrado pelo autor:** `https://mlw-quantumfinance-credit-ocqjl.southafricanorth.inference.ml.azure.com/score` (POST; modo de autenticação `Key`). A URL antiga `api.quantumfinance.com` era ilustrativa: **não use como endpoint real**. A implementação FastAPI deste ZIP é um serviço local separado; o `score.py` da pasta original é o script de scoring da implantação Azure `quantumfinance-credit-score-v9`, que fixa o modelo no deploy e não consulta a versão `Production` do Registry a cada chamada. Após promoção, só um novo deployment/atualização de modelo no Azure muda a versão servida. A autenticação `Key` foi confirmada por captura, mas **não há evidência de throttling no Azure**; o rate limit da API local não o protege.

## Testar a implantação já criada no Azure ML

Na aba **Testar** do Azure ML, selecione `quantumfinance-credit-score-v9`, cole o conteúdo completo de [`examples/azure_endpoint_input.json`](../examples/azure_endpoint_input.json) em **Input** e clique em **Teste**. O arquivo segue o contrato de `score.py` da pasta original (`input_data.data`, lista de registros); a linha contém as **58 features numéricas/indicadoras** geradas por `train.py` da pasta original, sem `SSN`, `Name` nem identificadores. O modelo antigo foi treinado com pré-processamento **fora** do artefato, logo os 22 campos crus de `examples/cliente.json` não substituem essa entrada. Se a implantação v9 usar outro script/esquema, confira a aba **Consumir**, o modelo registrado e os logs antes de adaptar a requisição. **Resposta observada no teste feito pelo autor com esse payload e a implantação v9:**

```json
{"predictions":["Good"],"model_version":"1"}
```

`Good` é a classe prevista **para este exemplo**, não para todos os clientes. O `v9` é parte do nome da implantação no Azure; `model_version: "1"` vem do script de scoring (que tenta extrair a versão do caminho `AZUREML_MODEL_DIR`) e **não comprova**, por si só, que a versão registrada do modelo seja 1. Para conferir a versão efetivamente associada ao deployment, veja os detalhes do modelo na aba **Detalhes** do endpoint ou em **Modelos** no Azure ML. **Os exemplos HTTP 400/401/429/503 abaixo são da API FastAPI local, não do Azure ML:** `score.py` original captura exceções e devolve `{"error":"..."}`, podendo responder HTTP 200 até em erros de inferência. A proteção de autenticação HTTP 401 do Azure é aplicada na borda do serviço, não por `score.py`.

**Consumo externo do Azure ML:** use `POST` na URI `/score` acima, headers `Content-Type: application/json` e `Authorization: Bearer <CHAVE_DO_ENDPOINT_AZURE>`, e corpo `examples/azure_endpoint_input.json`. A chave primária/secundária é obtida na aba **Consumir**; **não** é a `X-API-Key` da API local. Nunca inclua a chave em arquivo, Git ou captura. O tráfego ao vivo do deployment v9 foi configurado no Portal Azure para **100%** (aba **Detalhes → Atualizar tráfego**), de modo que chamadas reais ao endpoint são atendidas pela implantação `quantumfinance-credit-score-v9`. O header de diagnóstico `azureml-model-deployment: quantumfinance-credit-score-v9` permite confirmar qual implantação atendeu cada requisição. As **capturas do portal** desta entrega seguem o [checklist de capturas](checklist_capturas_azure.md) (caminho de cada tela, arquivo esperado em `docs/evidencias/` e regras de privacidade — chaves sempre mascaradas).

**Segurança na nuvem:** a autenticação por chave do Azure ML está habilitada, porém as capturas **não mostram limite por parceiro**. Duas chaves do endpoint (primária/secundária) servem à autenticação/rotação; não equivalem a planos por empresa. O template e o passo a passo para inserir o [API Management como gateway com política `rate-limit` por assinatura](throttling_azure.md) estão incluídos em `deploy/apim-policy.xml` e `docs/throttling_azure.md`. **Ainda precisam ser aplicados e testados no Azure**; enquanto isso, o throttling apenas está implementado na API local. Para evitar bypass, não compartilhe a chave do Azure ML com parceiros e planeje backend privado. Referências: [autenticação Azure ML](https://learn.microsoft.com/azure/machine-learning/how-to-authenticate-online-endpoint?view=azureml-api-2), [implantação/tráfego](https://learn.microsoft.com/azure/machine-learning/concept-endpoints-online?view=azureml-api-2).

## Iniciar o servidor (Windows/Linux/macOS)

O caminho mais rápido **não exige dataset nem treino** (usa o modelo embalado `models/credit-score-v1/`):

```powershell
python tools/setup_local.py        # cria .venv, instala requirements e registra o modelo embalado
# Windows:
$env:QF_API_KEYS = 'minha-chave-local-longa-e-aleatoria'
.\.venv\Scripts\python.exe -m uvicorn src.api:app --host 127.0.0.1 --port 8000
# Linux/macOS:
export QF_API_KEYS='minha-chave-local-longa-e-aleatoria'
./.venv/bin/python -m uvicorn src.api:app --host 127.0.0.1 --port 8000
```

Manual (sem `setup_local.py`):

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe tools\seed_registry.py   # registra o modelo embalado como Production
$env:QF_API_KEYS = 'minha-chave-local-longa-e-aleatoria'
.\.venv\Scripts\python.exe -m uvicorn src.api:app --host 127.0.0.1 --port 8000
```

Para **retreinar** antes de iniciar, informe o CSV da disciplina (fica fora do pacote por conter dados pessoais):
`.\.venv\Scripts\python.exe -m src.train --data '<caminho-do-seu-train.csv>'`; ou use o CSV demo sintético incluído:
`.\.venv\Scripts\python.exe -m src.train --data 'data/raw/demo_train.csv' --quick`.

O treino completo realiza 3 candidatos com busca CV e pode demorar. Para validação rápida use `--quick` com `--max-customers 150` **ou** o CSV demo incluído (`--data 'data/raw/demo_train.csv' --quick`); F1 abaixo de 0,70 **não** promove. Não é preciso treinar para subir a API: o modelo embalado já é registrado pelo `seed_registry.py`. Depois de promover um modelo, rode `python tools/validate_local.py` para iniciar um servidor HTTP temporário e verificar respostas 200/401/429 usando limite **temporário** de 2 chamadas/minuto. Veja runs em `./mlruns` ou execute `mlflow ui --backend-store-uri ./mlruns` (ou o tracking server configurado). `.env.example` é um modelo, **não é carregado automaticamente**; defina variáveis no ambiente do processo. O serviço nunca aceita chamadas sem chave configurada. A documentação interativa local é `http://127.0.0.1:8000/docs` (não exponha publicamente sem proteção).

## Endpoints e autenticação

| Rota | Método | Autenticação | Descrição |
|---|---|---|---|
| `/credit-score/v1/predict` | POST | `X-API-Key: <chave>` | Um cliente por requisição. |
| `/credit-score/v1/health` | GET | nenhuma | Liveness do processo, **não** garante modelo Production disponível. |

`Content-Type: application/json` é necessário em POST. `X-Request-Id: <identificador>` é opcional; na ausência, o servidor gera UUID. Não envie `Name`, `SSN`, `Customer_ID`, `ID`, `Credit_Score` ou outros campos extras. Configure `QF_API_KEYS` com uma ou mais chaves separadas por vírgula (segredos nunca no Git); comparação em tempo constante. Rode **somente em loopback para desenvolvimento**; produção requer TLS, armazenamento/rotação de segredos e limitação centralizada. Chaves não possuem revogação dinâmica neste exemplo: remova-as da variável e reinicie a API.

Limites: 60 requisições por minuto e 10 por segundo **por chave, por processo**. Ao exceder, recebe HTTP 429 + `Retry-After` em segundos; em sucesso, headers `X-RateLimit-Limit` e `X-RateLimit-Remaining` informam a janela de minuto. Para demonstração, `QF_RATE_PER_MINUTE` e `QF_RATE_PER_SECOND` podem ser ajustados no ambiente **antes** de iniciar; não é uma cota global para múltiplos workers.

## Payload JSON (campos com nomes e maiúsculas iguais aos do CSV)

Todos os campos abaixo são obrigatórios. `Age`, `Num_Bank_Accounts`, `Num_Credit_Card`, `Interest_Rate`, `Num_of_Loan`, `Delay_from_due_date`, `Num_of_Delayed_Payment` são **inteiros**. `Annual_Income`, `Monthly_Inhand_Salary`, `Changed_Credit_Limit`, `Num_Credit_Inquiries`, `Outstanding_Debt`, `Credit_Utilization_Ratio`, `Total_EMI_per_month`, `Amount_invested_monthly`, `Monthly_Balance` são **números finitos**. `Occupation`, `Type_of_Loan`, `Credit_Mix`, `Payment_of_Min_Amount`, `Payment_Behaviour` e `Credit_History_Age` são **strings**. A idade do histórico aceita por exemplo `22 Years and 1 Months`. Use o corpo completo de `examples/cliente.json`; valores ilustrativos, sem informações identificadoras.

```powershell
$env:QF_API_KEYS = 'minha-chave-local-longa-e-aleatoria'  # na sessão do servidor
curl.exe -X POST 'http://127.0.0.1:8000/credit-score/v1/predict' `
  -H 'Content-Type: application/json' `
  -H 'X-API-Key: minha-chave-local-longa-e-aleatoria' `
  -H 'X-Request-Id: teste-001' `
  --data-binary '@examples/cliente.json'
```

`curl.exe` evita que o alias `curl` do PowerShell mude o formato da chamada. Não informe chave ou dados pessoais em logs compartilhados.

### Respostas

**200** (resposta observada no servidor local após o treino completo, para `examples/cliente.json`):

```json
{"credit_score_predicted":"Good","model_version":"1","request_id":"teste-local"}
```

A classe e a versão variam conforme o modelo promovido; veja as [evidências do treinamento e testes HTTP](validacao_local.md).

Classes possíveis: `Good`, `Poor`, `Standard`. `model_version` é a versão *Production* realmente usada pelo processo; após nova promoção, a próxima chamada consulta o Registry. `X-Request-Id` também é devolvido no header.

**Erros** usam sempre `{"error":{"code":"...","message":"...","request_id":"..."}}`:

| HTTP | `code` | Causa / exemplo |
|---|---|---|
| 400 | `invalid_payload` | JSON inválido, campos ausentes/extras ou tipo incorreto. |
| 401 | `invalid_api_key` | `X-API-Key` ausente/não cadastrada. |
| 429 | `rate_limit_exceeded` | Excedeu limite; aguarde `Retry-After`. |
| 503 | `service_not_configured` | Variável `QF_API_KEYS` vazia. |
| 503 | `model_not_available` | Sem modelo Production ou Registry indisponível. |
| 500 | `internal_error` | Erro inesperado na predição; servidor não revela detalhes. |

Exemplo de erro de entrada (HTTP 400):

```json
{"error":{"code":"invalid_payload","message":"JSON inválido ou campos faltando/com tipo inválido.","request_id":"teste-001"}}
```

O corpo é validado antes do handler de autenticação: se **ambos** chave e JSON forem inválidos, a validação pode responder 400 primeiro. `GET /credit-score/v1/health` responde `{"status":"ok"}` com 200.

## Troubleshooting / FAQ

- **401**: confira `X-API-Key` e `QF_API_KEYS` no **processo** do servidor (a variável não é carregada do `.env` automaticamente). Não compartilhe a chave.
- **400**: payload deve ser um objeto JSON plano com todos os 22 campos, respeitando grafia/case, tipos e sem PII/target; confira `examples/cliente.json`.
- **429**: espere `Retry-After` segundos e implemente backoff; muitos envios em 1 s também atingem o limite burst.
- **503 `model_not_available`**: execute `python -m src.train --data ...`; confira F1 mínimo, store compartilhado, o modelo em `Production`, acesso ao diretório `mlruns` e compatibilidade de dependências; se o baseline falhar, a versão anterior permanece em Production (se existir).
- **503 `service_not_configured`**: defina uma chave forte em `QF_API_KEYS` e reinicie o processo.
- **O score não muda após treino**: veja no log se houve promoção; se foi recusada, a versão continua a mesma. Se usar `score.py` no Azure, ele lê a versão vinculada no deployment, não acompanha o Registry.
- **API no ar, health OK, mas /predict falha**: health é apenas liveness. Confira `MLFLOW_TRACKING_URI` idêntica no treino e na API. Para reiniciar localmente, não apague `mlruns/` (isso apaga runs e versões).
