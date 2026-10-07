# Throttling no Azure — configuração e evidência (APIM aplicado)

**Estado atual (aplicado e testado em 07/10/2026):**

- **Managed Online Endpoint** `mlw-quantumfinance-credit-ocqjl` (auth `Key`) respondendo `{"predictions":["Good"],"model_version":"1"}`; deployment `quantumfinance-credit-score-v9` com **100% do tráfego ao vivo** (confirmado também por CLI em [`azure_endpoint_estado.json`](evidencias/azure_endpoint_estado.json) e [`azure_deployments.json`](evidencias/azure_deployments.json)).
- **Azure API Management (plano Consumption, `southafricanorth`)** criado e configurado: instância `apim-quantumfinance-credit`, gateway `https://apim-quantumfinance-credit.azure-api.net`, API `QuantumFinance Score` (path `credit-score/v1`, **Subscription required**, operação `POST /predict`), Named Value secreto `aml-endpoint-key` (chave Azure ML exclusiva do gateway), política `rate-limit calls="60" renewal-period="60"` por assinatura e assinatura de exemplo `parceiro-exemplo` com scope na API.
- **Testado com HTTP real no gateway:** sem chave → **401**; chave de assinatura correta → **200** com predição e `X-RateLimit-Limit: 60`; chave errada → **401** ([`apim_teste_http.log`](evidencias/apim_teste_http.log)). Com `calls="3"` temporário e 5 chamadas rápidas: **3× 429** com `Retry-After`; política **restaurada para 60 e validada** ([`apim_teste_throttle.log`](evidencias/apim_teste_throttle.log)). Evidência dos recursos em [`apim_servico.json`](evidencias/apim_servico.json), [`apim_api.json`](evidencias/apim_api.json), [`apim_assinatura.json`](evidencias/apim_assinatura.json), [`apim_namedvalue.json`](evidencias/apim_namedvalue.json) e [`apim_politica.json`](evidencias/apim_politica.json).

As seções abaixo documentam o **procedimento** (portal ou CLI) para reprodução. O teste pode ser repetido com `python tools/testar_apim.py` (401/200/401) e `python tools/testar_throttle_apim.py` (aplica `calls="3"`, dispara chamadas, restaura `calls="60"`).

## Opção recomendada: Azure API Management (APIM)

```
Parceiro → HTTPS APIM (chave exclusiva, 60 chamadas/60 s)
         → Authorization: Bearer <chave interna Azure ML> → Azure ML /score
```

A chave do endpoint ML **não é entregue aos parceiros**. Eles recebem somente a chave de assinatura individual do APIM. Com isso, o limite aplicado pelo APIM vale para o tráfego que atravessa o gateway. Para uma demonstração econômica, **Consumption** admite a política `rate-limit` por assinatura e é cobrado por requisição acima da franquia, sem custo fixo do APIM; **não suporta `rate-limit-by-key`** nem conexão privada de entrada, verifique disponibilidade e custo na sua assinatura Azure for Students antes de criar. **Developer** aceita `rate-limit-by-key` mas custa por tempo provisionado, não possui SLA e não serve produção. Para integração corporativa com backend privado, avaliar plano com saída para VNet e Private Endpoint do Azure ML (ex.: Standard v2), com custo maior. Não há configuração que faça o rate limit do código FastAPI local valer automaticamente na URI Azure.

## Passo a passo no portal

1. **Roteamento Azure ML:** em Azure ML Studio → **Pontos de extremidade** → `mlw-quantumfinance-credit-ocqjl` → **Detalhes → Atualizar tráfego**. Configure v9 com **100%** se for o único deployment que deve receber produção, ou a porcentagem aprovada em um rollout. Confira o resultado fora da aba **Testar**; ela pode chamar diretamente v9 mesmo com 0% do tráfego. Não redirecione parceiros sem aprovar o modelo/versão efetiva.
2. **Custo:** no Portal Azure configure orçamento/alerta de gastos e confirme disponibilidade do APIM em sua assinatura/região antes de criar. Nunca coloque uma chave real em capturas de tela, políticas no Git ou conversas.
3. **Criar APIM:** Portal Azure → **Criar recurso → API Management**; selecione o grupo de recursos, uma região adequada e um plano compatível. Para demonstrar 60/min por parceiro, o plano **Consumption** basta; para ambiente de produção selecione SKU com disponibilidade/SLA e redes compatíveis com a política de segurança. Aguarde provisionamento.
4. **Criar API:** recurso APIM → **APIs → + Add API → HTTP** (ou **Blank API**, dependendo do portal). Nome: `QuantumFinance Score`; URL suffix/path: `credit-score/v1`; Web service/backend URL: `https://mlw-quantumfinance-credit-ocqjl.southafricanorth.inference.ml.azure.com` (sem `/score`). Exija **Subscription required**. Defina apenas a operação **POST `/predict`**. O APIM irá expor `https://<seu-apim>.azure-api.net/credit-score/v1/predict`.
5. **Guardar chave do backend:** APIM → **Named values → + Add**. Display name/name: `aml-endpoint-key`; tipo **Secret** (ou referência a Azure Key Vault); valor: chave do Azure ML copiada por você da aba **Consumir**. Named Value guarda só a chave bruta, **sem** o prefixo `Bearer`. Não enviar a chave para terceiros.
6. **Aplicar a política:** em **APIs → QuantumFinance Score → All operations → Inbound processing → Code editor/Policy editor**, cole [`../deploy/apim-policy.xml`](../deploy/apim-policy.xml) inteiro e salve. A política limita 60 chamadas a cada 60 segundos **por assinatura APIM** (não por IP nem por chave do Azure ML), troca as credenciais e reescreve `/predict` para `/score`. Um cliente acima do limite recebe HTTP **429**, tipicamente com `Retry-After`. Se o editor já tiver outras políticas, integre-as sem remover políticas de segurança preexistentes.
7. **Uma assinatura por parceiro:** APIM → **Subscriptions → + Add**. Crie uma assinatura para cada empresa com **Scope** restrito à API/produto QuantumFinance; entregue somente a respectiva chave de assinatura. Não compartilhe a assinatura de administração/all-access. Na API, confirme que **Subscription required** permaneceu ativo. Revogação: suspender a assinatura individual.
8. **Verificar:** no gateway APIM, envie `POST /credit-score/v1/predict`, `Content-Type: application/json`, header `Ocp-Apim-Subscription-Key: <CHAVE_DA_EMPRESA>` e body de `examples/azure_endpoint_input.json`. **Não** envie `Authorization` do Azure ML; o gateway insere o header do backend. Uma chamada autorizada deve obter a predição. Sem assinatura, deve ser recusada. Para testar limite com custo menor, altere provisoriamente `calls="60"` para `calls="3"`, envie **4 chamadas** com a mesma assinatura: a 4ª deve dar **429**. Outra assinatura deve ter seu contador independente. Depois restaure **60**. As cotas são aproximadas por natureza distribuída e não substituem um limite de custo no Azure ML.

**Atenção ao bypass:** o Azure ML tem acesso público `Enabled` nas capturas. A política APIM **não** limita requisições feitas diretamente ao Azure ML com uma chave válida. Como mínimo, mantenha a chave Azure ML **exclusiva do gateway**, não a forneça aos parceiros, armazene-a como secret e faça rotação se já tiver sido compartilhada. Para impedir bypass por rede, configure **Private Endpoint + public_network_access disabled** no endpoint Azure ML e um plano APIM que alcance o backend privado por VNet; valide essa conectividade antes de desligar acesso público. Até isso estar pronto, não afirme que o endpoint Azure ML bruto tem throttling: a **URL publicada aos parceiros deve ser a do APIM**.

### Exemplo de chamada ao APIM (PowerShell)

```powershell
# Não grave segredos reais no código-fonte. Defina sua chave em ambiente seguro.
curl.exe -X POST 'https://<seu-apim>.azure-api.net/credit-score/v1/predict' `
  -H 'Content-Type: application/json' `
  -H 'Ocp-Apim-Subscription-Key: <CHAVE_DA_EMPRESA>' `
  --data-binary '@examples/azure_endpoint_input.json'
```

### Reprodução e validação (Azure CLI + scripts do repositório)

O ambiente que você viu nesta entrega foi criado/verificado assim (sem segredos no Git):

```powershell
# Login único e ambiente:
az login
az provider register -n Microsoft.ApiManagement   # aguarde ficar 'Registered'

# 1) Instância (Consumption == pago por chamada; valide o custo antes):
az apim create --name apim-quantumfinance-credit -g rg-quantumfinance-mlops `
  -l southafricanorth --publisher-email <seu-email> --publisher-name QuantumFinance `
  --sku-name Consumption

# 2) API + operação:
az apim api create --service-name apim-quantumfinance-credit -g rg-quantumfinance-mlops `
  --api-id quantumfinance-credit --path '/credit-score/v1' --display-name 'QuantumFinance Score' `
  --service-url https://mlw-quantumfinance-credit-ocqjl.southafricanorth.inference.ml.azure.com `
  --subscription-required true --protocols https
az apim api operation create -g rg-quantumfinance-mlops --service-name apim-quantumfinance-credit `
  --api-id quantumfinance-credit --operation-id predict --url-template '/predict' `
  --method POST --display-name 'Predict'

# 3) Named Value secreto (chave Azure ML): use PUT ARM com corpo em arquivo e
#    header If-Match '*' (o valor não passa na linha de comando). Nunca commite a chave.
```

- **Política e assinatura:** `az rest`/`Invoke-RestMethod` com token `az account get-access-token --resource https://management.azure.com`, `PUT .../apis/quantumfinance-credit/policies/policy?api-version=2022-08-01` (formato `rawxml`, corpo gerado a partir de `deploy/apim-policy.xml`) e `PUT .../subscriptions/parceiro-exemplo?api-version=2022-08-01` com `scope` restrito à API. Atualizações de recurso existente exigem o header `If-Match: *`.
- **Tirar a prova (scripts incluídos no ZIP):**
  - `python tools/testar_apim.py` — com `QF_APIM_GATEWAY` e `QF_APIM_SUB_KEY` definidos, testa 401 (sem chave) / 200 (chave correta, mostra `X-RateLimit-Limit`) / 401 (chave errada).
  - `python tools/testar_throttle_apim.py` — aplica `calls="3"` temporário, dispara 5 chamadas (recupera **429** com `Retry-After`), **restaura `calls="60"`** e valida o conteúdo da política.
- **Estado atual dos recursos** e os resultados de cada teste estão em `docs/evidencias/apim_*.json`, `apim_teste_http.log` e `apim_teste_throttle.log`.

**Referências Microsoft:** [rate-limit por assinatura (suporta Consumption)](https://learn.microsoft.com/azure/api-management/rate-limit-policy), [matriz de políticas por plano](https://learn.microsoft.com/azure/api-management/api-management-policies), [criar assinaturas](https://learn.microsoft.com/azure/api-management/api-management-howto-create-subscriptions), [segurança da rede Azure ML](https://learn.microsoft.com/azure/machine-learning/how-to-secure-online-endpoint?view=azureml-api-2), [custos APIM](https://learn.microsoft.com/azure/api-management/plan-manage-costs).
