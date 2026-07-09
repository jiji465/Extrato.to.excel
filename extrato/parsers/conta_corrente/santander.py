"""Parser do Santander PF — "Extrato Consolidado Inteligente" (conta corrente).

Layout da seção "Movimentação":

    Data Descrição Nº Documento Movimento (R$) Saldo (R$)
    SALDO EM 31/12 4.875,93
    02/01 PIX ENVIADO - 5,93- 4.870,00
    Paroquia de Nossa Senhora            <- linha de continuação (favorecido)
    09/01 PIX AGENDADO - 600,60-         <- sem saldo parcial nesta linha
    ...
    SALDO EM 31/01 7.800,00

Regras:
- Valor monetário sempre tem centavos (,dd); nº de documento é inteiro puro.
- '-' colado após os centavos = débito (saída). Sem '-' = crédito (entrada).
- Quando a linha tem 2 valores, o 1º é o movimento e o 2º é o saldo parcial.
- Linha sem valor = continuação da descrição da transação anterior.
- Data ausente na linha => herda a data da última transação (mesmo dia).

O parser também lê o resumo (saldo inicial/final e totais) para a auditoria.
"""

from __future__ import annotations

import re

from ...normalizar import CONTA_CORRENTE, Extrato, Transacao, parse_data, valores_brl
from ..base import linhas_do_pdf

BANCO = "Santander"

_MESES = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
}

_HEADER = re.compile(r"Movimento\s*\(R\$\).*Saldo\s*\(R\$\)")
_DATA = re.compile(r"^(\d{2}/\d{2})\b")
_NOISE = re.compile(
    r"^(Extrato_PF|BALP_|Pagina:|EXTRATO CONSOLIDADO|Conta Corrente$|"
    r"Movimentação$|[a-zç]+/20\d{2}$)"
)
_FIM_SECAO = re.compile(r"^(Saldos por Período|Débito Automático|Comprovantes)")


def _ano_referencia(linhas: list[str]) -> int:
    for l in linhas:
        m = re.search(r"([a-zç]+)/(20\d{2})", l.lower())
        if m and m.group(1) in _MESES:
            return int(m.group(2))
    return 2000


def _valor_resumo(linhas: list[str], rotulo: str):
    """Lê um valor do bloco 'Resumo' (ex.: '(+) Total de Créditos 45.519,84')."""
    for l in linhas:
        if rotulo.lower() in l.lower():
            vals = valores_brl(l)
            if vals:
                v, neg, _, _ = vals[-1]
                return -v if neg else v
    return None


def parse(caminho: str) -> Extrato:
    linhas = linhas_do_pdf(caminho)
    ano = _ano_referencia(linhas)

    # saldo inicial/final vêm das linhas "SALDO EM" da própria movimentação
    # (definidos no laço abaixo); do resumo pegamos só os totais de conferência.
    extrato = Extrato(
        banco=BANCO,
        tipo_documento=CONTA_CORRENTE,
        total_creditos=_valor_resumo(linhas, "Total de Créditos"),
        total_debitos=_valor_resumo(linhas, "Total de Débitos"),
    )

    transacoes: list[Transacao] = []
    in_mov = False
    data_atual = None

    for linha in linhas:
        ls = linha.strip()

        if _HEADER.search(linha):
            in_mov = True
            continue
        if not in_mov:
            continue

        if ls.startswith("SALDO EM"):
            vals = valores_brl(ls)
            if vals:
                saldo = -vals[-1][0] if vals[-1][1] else vals[-1][0]
                if extrato.saldo_inicial is None:
                    extrato.saldo_inicial = saldo   # SALDO EM 31/12 (abertura)
                else:
                    if extrato.saldo_final is None:
                        extrato.saldo_final = saldo  # SALDO EM 31/01 (fechamento)
                    in_mov = False
            continue

        if _FIM_SECAO.match(ls):
            in_mov = False
            continue
        if not ls or _NOISE.match(ls):
            continue

        # Data no início da linha?
        md = _DATA.match(ls)
        if md:
            data_atual = md.group(1)
            resto = ls[md.end():].strip()
        else:
            resto = ls

        vals = valores_brl(resto)
        if not vals:
            # linha de continuação = favorecido (contraparte) da última transação
            if transacoes and not _NOISE.match(ls):
                prev = transacoes[-1]
                prev.favorecido = (prev.favorecido + " " + ls).strip() if prev.favorecido else ls
            continue

        mov_valor, mov_neg, mov_ini, _ = vals[0]
        valor = -mov_valor if mov_neg else mov_valor
        # saldo parcial honra o sinal: "557,85-" = saldo negativo (uso do limite)
        if len(vals) >= 2:
            saldo = -vals[1][0] if vals[1][1] else vals[1][0]
        else:
            saldo = None

        pre = resto[:mov_ini]
        doc_m = re.search(r"(\d{3,})\s*$", pre)
        documento = doc_m.group(1) if doc_m else ""
        descricao = re.sub(r"\s*\d{3,}\s*$", "", pre).strip(" -\t")

        transacoes.append(
            Transacao(
                data=parse_data(f"{data_atual}/{ano}") if data_atual else None,
                descricao=descricao,
                valor=valor,
                saldo=saldo,
                documento=documento,
                banco=BANCO,
            )
        )

    extrato.transacoes = transacoes
    return extrato
