# Dados processados

Espaço reservado para snapshots derivados de futuras ingestões. **Nenhum arquivo é necessário aqui na entrega atual**: `src/train.py` prepara as features em memória e salva as transformações aprendidas dentro do Pipeline MLflow, usado também pela inferência.

Não versione snapshots de clientes no Git/ZIP. Para governança, registre fonte autorizada, consentimento, data do snapshot e hash no sistema de dados/experimentos antes de usar novos dados.
