# Fixtures de teste

Coloque aqui PDFs de exemplo (um por banco/tipo). Podem ter nomes/valores
redigidos, desde que a estrutura das colunas fique intacta.

- Qualquer `*.pdf` nesta pasta é processado pelo teste `test_fixtures_nao_quebram`
  (garante que o pipeline não quebra).
- Para conferência de saldos, adicione um caso em `tests/casos.py` com o esperado
  (banco, tipo, contagem mínima, `auditoria_ok`).

Rodar os testes:

```
python -m pytest tests/ -v
```
