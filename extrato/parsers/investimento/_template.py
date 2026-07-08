"""TEMPLATE de parser de EXTRATO DE INVESTIMENTOS — copie para `<banco>.py`,
implemente `parse` e registre em `extrato/parsers/__init__.py` com a chave
(chave_banco, INVESTIMENTO).

Convenções (para a auditoria em auditoria.py):
- Preencha no `Extrato`: `saldo_anterior`, `saldo_atual` e `rendimento`.
  A auditoria confere: saldo_anterior + rendimento = saldo_atual.
- As `transacoes` podem representar aplicações (valor negativo = saiu da conta
  para investir) e resgates (valor positivo), ou os movimentos por produto —
  defina conforme o layout e documente aqui.

Referência de estilo: `extrato/parsers/conta_corrente/santander.py`.
Ferramentas de extração: `extrato/extracao.py`.
"""

from __future__ import annotations

from ...normalizar import INVESTIMENTO, Extrato, Transacao, parse_data, valores_brl
from ..base import linhas_do_pdf

BANCO = "NOME DO BANCO"


def parse(caminho: str) -> Extrato:
    raise NotImplementedError(
        "Parser de investimento ainda não implementado — envie um PDF de exemplo."
    )
