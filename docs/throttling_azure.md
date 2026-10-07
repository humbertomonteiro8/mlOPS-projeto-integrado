# Configurar throttling no Azure — procedimento a executar

**Estado atual:** o Managed Online Endpoint `mlw-quantumfinance-credit-ocqjl` exige `Key` e recebe chamadas de teste com `{"predictions":["Good"],"model_version":"1"}`. O deployment `quantumfinance-credit-score-v9` foi configurado no Portal Azure com **100% do tráfego ao vivo** (aba **Detalhes → Atualizar tráfego**). Ainda **não há evidência de limite por parceiro no Azure** (throttling). Este arquivo contém o **plano de configuração**, não prova que os recursos abaixo já existam.

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

**Referências Microsoft:** [rate-limit por assinatura (suporta Consumption)](https://learn.microsoft.com/azure/api-management/rate-limit-policy), [matriz de políticas por plano](https://learn.microsoft.com/azure/api-management/api-management-policies), [criar assinaturas](https://learn.microsoft.com/azure/api-management/api-management-howto-create-subscriptions), [segurança da rede Azure ML](https://learn.microsoft.com/azure/machine-learning/how-to-secure-online-endpoint?view=azureml-api-2), [custos APIM](https://learn.microsoft.com/azure/api-management/plan-manage-costs).
