"""Parser do Bradesco — "Extrato Mensal / Por Período" (conta corrente).

Layout colunar:

    Data Lançamento Dcto. Crédito (R$) Débito (R$) Saldo (R$)
    31/12/2025 SALDO ANTERIOR 317.045,88
    26/01/2026 RENTAB.INVEST FACILCRED* 8392111 0,30 317.046,18
    PAGTO ELETRON COBRANCA                       <- descrição (linha sem valor)
    3 -166,40 316.879,78                         <- dcto, débito, saldo
    ODONTOPREV S/A                               <- continuação da descrição
    Total 0,30 -166,40 316.879,78                <- totais (conferência)

Regras:
- Débito vem com sinal '-'; crédito é positivo. O 1º token monetário da linha é
  o movimento (com sinal), o último é o saldo parcial.
- A descrição pode aparecer em linhas sem valor, antes e/ou depois da linha do
  valor; acumulamos essas linhas na descrição.
- A linha "Total" traz total de créditos, débitos e o saldo final.
"""

from __future__ import annotations

import re

from ...normalizar import CONTA_CORRENTE, Extrato, Transacao, parse_data, valores_brl
from ..base import linhas_do_pdf

BANCO = "Bradesco"

_HEADER = re.compile(r"Data\s+Lançamento.*Saldo", re.IGNORECASE)
_DATA = re.compile(r"^(\d{2}/\d{2}/\d{4})\b")
_FIM = re.compile(r"^(Os dados acima|Últimos Lançamentos|Não há lançamentos)")


def parse(caminho: str) -> Extrato:
    linhas = linhas_do_pdf(caminho)
    extrato = Extrato(banco=BANCO, tipo_documento=CONTA_CORRENTE)

    transacoes: list[Transacao] = []
    in_sec = False
    data_atual = None
    buffer: list[str] = []          # linhas de descrição sem valor

    def _desc_pre(texto: str) -> str:
        # remove nº de documento (inteiro) no fim do trecho de descrição
        return re.sub(r"\s*\d{3,}\s*$", "", texto).strip(" -\t")

    for linha in linhas:
        ls = linha.strip()
        if _HEADER.search(ls):
            in_sec = True
            continue
        if not in_sec or not ls:
            continue

        if _FIM.match(ls):
            break

        # data no início?
        md = _DATA.match(ls)
        if md:
            data_atual = parse_data(md.group(1))
            resto = ls[md.end():].strip()
        else:
            resto = ls

        # saldo anterior (abertura)
        if "SALDO ANTERIOR" in resto.upper():
            vals = valores_brl(resto)
            if vals:
                extrato.saldo_inicial = -vals[-1][0] if vals[-1][1] else vals[-1][0]
            continue

        # linha de totais (fechamento)
        if resto.lower().startswith("total"):
            vals = valores_brl(resto)
            if len(vals) >= 3:
                extrato.total_creditos = vals[0][0]
                extrato.total_debitos = vals[1][0]
                extrato.saldo_final = -vals[2][0] if vals[2][1] else vals[2][0]
            if buffer and transacoes:
                transacoes[-1].descricao += " " + " ".join(buffer)
                buffer.clear()
            continue

        vals = valores_brl(resto)
        if not vals:
            buffer.append(resto)       # descrição pura
            continue

        # linha com valor => fecha uma transação
        mov = vals[0]
        valor = -mov[0] if mov[1] else mov[0]
        saldo = None
        if len(vals) >= 2:
            s = vals[-1]
            saldo = -s[0] if s[1] else s[0]

        pre = _desc_pre(resto[: mov[2]])
        partes = [p for p in ([" ".join(buffer).strip()] + [pre]) if p]
        descricao = " ".join(partes).strip(" -\t")
        buffer.clear()

        transacoes.append(
            Transacao(
                data=data_atual,
                descricao=descricao,
                valor=valor,
                saldo=saldo,
                banco=BANCO,
            )
        )

    extrato.transacoes = transacoes
    return extrato
