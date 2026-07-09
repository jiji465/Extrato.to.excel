"""Parser do Nubank — extrato de conta (NuConta / Nu Pagamentos).

Layout real (2026):

    Saldo inicial 53,20
    Rendimento líquido +0,00
    Saldo final do período 1.871,23
    Total de entradas +89.764,90
    Total de saídas -87.946,87
    Movimentações
    05 JAN 2026 Total de saídas - 20,00
    Transferência enviada pelo Pix Imina ... - NU 20,00
    PAGAMENTOS - IP (0260) Agência: 1 Conta: 21459580-0   <- continuação
    Saldo do dia 33,20
    ...

Regras:
- O sinal do lançamento vem da SEÇÃO: após "Total de entradas" os lançamentos
  são entradas (+); após "Total de saídas" são saídas (-). Isso cobre todos os
  tipos (Pix, Compra no débito, Boleto, Aplicação/Resgate RDB) sem enumerá-los.
- A data vem da linha de cabeçalho do dia ("05 JAN 2026 ...").
- O valor do lançamento é o último token monetário da linha.
- "Saldo do dia X" fecha o dia; anexamos como saldo parcial ao último lançamento.
- Linhas sem valor monetário = continuação (dados da conta/favorecido).
"""

from __future__ import annotations

import re

from ...normalizar import CONTA_CORRENTE, Extrato, Transacao, valores_brl
from ..base import linhas_do_pdf

BANCO = "Nubank"

_MESES = {
    "JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12,
}

from datetime import date

_DIA = re.compile(r"^(\d{2})\s+([A-Z]{3})\s+(\d{4})\b")
_SALDO_DIA = re.compile(r"^Saldo do dia\b")
_TOTAL_ENTRADAS = re.compile(r"Total de entradas")
_TOTAL_SAIDAS = re.compile(r"Total de sa[íi]das")
_SKIP = re.compile(
    r"^(Saldo inicial|Saldo final|Rendimento|VALORES EM|A V |CNPJ|Agência|"
    r"Movimentações|Tem alguma dúvida|Caso a solução|disponíveis em|"
    r"Extrato gerado|R\$ |\d{6,})"
)

# tipos de lançamento do Nubank, para separar o favorecido da descrição
_TIPO_NUBANK = re.compile(
    r"^(Transferência\s+(?:enviada|recebida)(?:\s+pelo\s+Pix)?|"
    r"Compra no débito|Pagamento de boleto|Pagamento de fatura|"
    r"Aplicação RDB|Resgate RDB|Estorno|Reembolso|Débito automático)",
    re.IGNORECASE,
)


def _valor_label(linhas: list[str], rotulo: str):
    """Primeiro valor que aparece LOGO APÓS o rótulo (na mesma linha)."""
    r = rotulo.lower()
    for l in linhas:
        idx = l.lower().find(r)
        if idx >= 0:
            vals = valores_brl(l[idx + len(rotulo):])
            if vals:
                v, neg, _, _ = vals[0]
                return -v if neg else v
    return None


def parse(caminho: str) -> Extrato:
    linhas = linhas_do_pdf(caminho)

    # --- cabeçalho (antes de "Movimentações") ---
    corte = next((i for i, l in enumerate(linhas)
                  if l.strip().startswith("Movimentações")), 0)
    cab = linhas[:corte] if corte else linhas
    extrato = Extrato(
        banco=BANCO,
        tipo_documento=CONTA_CORRENTE,
        saldo_inicial=_valor_label(cab, "Saldo inicial"),
        total_creditos=_valor_label(cab, "Total de entradas"),
        total_debitos=abs(_valor_label(cab, "Total de saídas") or 0) or None,
        rendimento=_valor_label(cab, "Rendimento líquido"),
    )
    # saldo final: última ocorrência de "Saldo final do período" com valor
    for l in cab:
        if "saldo final do período" in l.lower():
            vals = valores_brl(l)
            if vals:
                extrato.saldo_final = vals[-1][0]

    # --- movimentações ---
    transacoes: list[Transacao] = []
    sinal = -1                 # padrão até ver a 1ª seção
    data_atual: date | None = None

    for linha in linhas[corte + 1:]:
        ls = linha.strip()
        if not ls:
            continue

        md = _DIA.match(ls)
        if md:
            mes = _MESES.get(md.group(2).upper())
            if mes:
                data_atual = date(int(md.group(3)), mes, int(md.group(1)))
            # a própria linha do dia traz a 1ª seção (entradas/saídas)
            if _TOTAL_ENTRADAS.search(ls):
                sinal = 1
            elif _TOTAL_SAIDAS.search(ls):
                sinal = -1
            continue

        if _TOTAL_ENTRADAS.search(ls):
            sinal = 1
            continue
        if _TOTAL_SAIDAS.search(ls):
            sinal = -1
            continue

        if _SALDO_DIA.match(ls):
            vals = valores_brl(ls)
            if vals and transacoes:
                s = vals[-1]
                transacoes[-1].saldo = -s[0] if s[1] else s[0]
            continue

        if _SKIP.match(ls):
            continue

        vals = valores_brl(ls)
        if not vals:
            # linha de continuação = dados bancários (agência/conta) — ignorada
            continue

        valor_abs = vals[-1][0]
        texto = ls[: vals[-1][2]].strip(" -\t")
        m = _TIPO_NUBANK.match(texto)
        if m:
            descricao = re.sub(r"\s+", " ", m.group(1)).strip()
            resto = texto[m.end():]
            # favorecido = nome antes do CPF mascarado / separador " - "
            favorecido = re.split(r"\s+[-–]\s+|\s+•", resto)[0].strip(" -\t")
        else:
            descricao, favorecido = texto, ""

        transacoes.append(
            Transacao(
                data=data_atual,
                descricao=descricao,
                favorecido=favorecido,
                valor=sinal * valor_abs,
                banco=BANCO,
            )
        )

    extrato.transacoes = transacoes
    return extrato
