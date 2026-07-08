"""Parser do Banco do Brasil — "Extrato de Conta Corrente".

Layout (conta PJ com varredura automática "BB Rende Fácil"):

    Dia Lote Documento Histórico Valor
    Saldo Anterior 0,00 (+)
    Pix - Recebido                                   <- histórico (linha anterior)
    02/01/2026                                        <- data
    14397 20757055324411 02/01 07:57 04871817350 Romario Ribeir 200,00 (+)
    02/01/2026 Transferência enviada                  <- data + histórico
    99021 610895000000294 6.000,00 (-)
    02/01 08:52 JOSE O ATAIDES                        <- detalhe (após)
    30/01/2026
    9903 BB Rende Fácil 13.846,53 (-)                 <- varredura p/ investimento
    Saldo do dia 0,00 (+)                             <- fecha o dia em 0
    S A L D O 0,00 (+)                                 <- saldo final

Regras:
- Cada linha que termina em "valor (+)" ou "valor (-)" é um lançamento; o sinal
  entre parênteses define crédito/débito. Linhas com "Saldo" são marcadores.
- A descrição (histórico) vem do texto após a data OU da linha imediatamente
  anterior à data; tenta-se anexar o nome do favorecido presente na linha do valor.
- "Saldo Anterior" = abertura; "S A L D O" (final) = fechamento; "Saldo do dia"
  fecha cada dia (aqui sempre 0,00 pela varredura Rende Fácil).
"""

from __future__ import annotations

import re

from ...normalizar import CONTA_CORRENTE, Extrato, Transacao, parse_data, valores_brl
from ..base import linhas_do_pdf

BANCO = "Banco do Brasil"

_DATA = re.compile(r"^(\d{2}/\d{2}/\d{4})\b")
_VALOR_SINAL = re.compile(r"^(.*?)(-?\d{1,3}(?:\.\d{3})*,\d{2})\s*\(([+-])\)\s*$")
_SKIP = re.compile(
    r"^(Extrato de Conta|Cliente|Agência:|Lançamentos$|"
    r"Dia Lote Documento|\* Saldos|Sujeitos a|Total Aplica)"
)


def _nome_favorecido(pre: str) -> str:
    """Extrai o trecho alfabético (nome/histórico) da parte antes do valor,
    descartando lote, documento, data/hora e CPF/CNPJ (tokens numéricos)."""
    tokens = pre.split()
    palavras = []
    for tk in tokens:
        # descarta puramente numéricos, datas dd/dd e horas hh:mm
        if re.fullmatch(r"[\d./:\-]+", tk):
            continue
        palavras.append(tk)
    return " ".join(palavras).strip(" -\t")


def parse(caminho: str) -> Extrato:
    linhas = linhas_do_pdf(caminho)
    extrato = Extrato(banco=BANCO, tipo_documento=CONTA_CORRENTE)

    transacoes: list[Transacao] = []
    data_atual = None
    hist = ""                    # histórico pendente para o próximo lançamento
    texto_anterior = ""          # última linha de texto puro (candidata a histórico)

    for linha in linhas:
        ls = linha.strip()
        if not ls or _SKIP.match(ls):
            continue

        m = _VALOR_SINAL.match(ls)
        if m:
            pre, num, sinal = m.group(1), m.group(2), m.group(3)
            baixo = pre.lower()
            valor = valores_brl(num)
            v = valor[0][0] if valor else 0.0

            # marcadores de saldo
            if "saldo anterior" in baixo:
                extrato.saldo_inicial = v if sinal == "+" else -v
                texto_anterior = ""
                continue
            if re.search(r"s\s*a\s*l\s*d\s*o", baixo) and "dia" not in baixo:
                extrato.saldo_final = v if sinal == "+" else -v
                continue
            if "saldo do dia" in baixo:
                if transacoes:
                    transacoes[-1].saldo = v if sinal == "+" else -v
                continue

            # lançamento
            nome = _nome_favorecido(pre)
            desc = (hist + " " + nome).strip() if hist else nome
            transacoes.append(
                Transacao(
                    data=data_atual,
                    descricao=re.sub(r"\s+", " ", desc).strip(" -\t"),
                    valor=v if sinal == "+" else -v,
                    banco=BANCO,
                )
            )
            hist = ""
            texto_anterior = ""
            continue

        # linha de data (pode trazer histórico no fim)
        md = _DATA.match(ls)
        if md:
            d = parse_data(md.group(1))
            if d:
                data_atual = d
            resto = ls[md.end():].strip()
            hist = resto if resto else texto_anterior
            texto_anterior = ""
            continue

        # linha de texto puro: candidata a histórico do próximo lançamento
        texto_anterior = ls
        hist = ls

    extrato.transacoes = transacoes
    return extrato
