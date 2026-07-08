"""TEMPLATE de parser de FATURA DE CARTÃO — copie este arquivo para
`<banco>.py`, implemente `parse` e registre em `extrato/parsers/__init__.py`
com a chave (chave_banco, FATURA).

Convenções da fatura (importantes para a auditoria em auditoria.py):
- `valor` POSITIVO  = compra/débito lançado (aumenta o que se deve).
- `valor` NEGATIVO  = pagamento/estorno/crédito.
- Preencha no `Extrato`: `total_fatura`, e se houver `saldo_anterior` e
  `vencimento`. A auditoria confere: saldo_anterior + Σ valores = total_fatura.
- Campos extras da Transacao úteis em fatura: `parcela` ("3/12"),
  `moeda_origem` ("USD") e `valor_origem` (valor na moeda estrangeira).

Use o parser de conta corrente do Santander como referência de estilo:
`extrato/parsers/conta_corrente/santander.py`. Ferramentas de extração em
`extrato/extracao.py` (linhas, palavras por coordenada, tabelas).
"""

from __future__ import annotations

from ...normalizar import FATURA, Extrato, Transacao, parse_data, valores_brl
from ..base import linhas_do_pdf

BANCO = "NOME DO BANCO"


def parse(caminho: str) -> Extrato:
    raise NotImplementedError(
        "Parser de fatura ainda não implementado — envie um PDF de exemplo."
    )
