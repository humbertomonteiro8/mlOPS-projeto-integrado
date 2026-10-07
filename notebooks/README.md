# Notebooks

- **`execucao_api.ipynb`** — demonstração da **API em execução real**: inicia o `uvicorn`, faz 10 chamadas HTTP (sucesso e falha: 200/401/400/429/503) e mostra o **log de conexão** do servidor em cada caso. O arquivo do pacote **já vem executado**; para reexecutá-lo em outra máquina:

  ```powershell
  .\.venv\Scripts\python.exe -m pip install -r requirements-notebook.txt
  .\.venv\Scripts\python.exe -m jupyter notebook notebooks\execucao_api.ipynb
  ```

  O notebook gera uma chave aleatória por execução (não impressa), usa `examples/cliente.json` (sem PII) e copia os logs finais para `docs/evidencias/`. Reconstrução do arquivo a partir do código-fonte das células: `tools/gerar_notebook.py`.

- O notebook original da disciplina, `analise_score_credito.ipynb`, permanece com o autor, **fora do pacote**. Não foi incluído automaticamente no ZIP porque saídas de EDA podem expor dados pessoais do `train.csv` (`SSN`, `Name`, `Customer_ID`).