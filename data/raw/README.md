# Dados originais

- **`demo_train.csv`** (incluído no pacote): CSV **sintético, sem PII**, que espelha o esquema do dataset da disciplina. Serve apenas para exercitar o pipeline (`python -m src.train --data 'data/raw/demo_train.csv' --quick`). Gerado por `tools/gerar_demo_csv.py`.
- **`train.csv` da disciplina**: fornecido pelo curso, **não** é incluído no Git nem no pacote (contém `Name`, `SSN` e `Customer_ID`). Para retreinar com ele, informe o caminho externo:

  ```powershell
  .\.venv\Scripts\python.exe -m src.train --data '<caminho-do-seu-train.csv>'
  ```

O código rastreia o SHA-256 do arquivo no MLflow, sem registrar o CSV como artefato. **Usar a API não exige nenhum CSV**: o modelo promovido vem embalado em `models/credit-score-v1/` e é registrado por `tools/seed_registry.py`.