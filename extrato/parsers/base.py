"""Extrator genérico reutilizável (fallback para (banco, tipo) sem parser
dedicado) e utilidades comuns reexportadas do toolkit de extração.

A estratégia genérica varre as linhas de texto procurando o padrão mais comum
de extrato de conta corrente:

    <data>  <descrição...>  <valor>  [<saldo>]
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

# Reexporta o toolkit para os parsers (compatibilidade: `from .base import ...`)
from ..extracao import (  # noqa: F401
    linhas_do_pdf,
    texto_do_pdf,
    ano_do_texto,
    palavras_do_pdf,
    linhas_por_coordenada,
    texto_em_faixa,
)
from ..normalizar import CONTA_CORRENTE, Extrato, Transacao, parse_data, apenas_valores

# Alias interno mantido por parsers que já o usavam.
_ano_do_texto = ano_do_texto


# Linha começando com uma data dd/mm[/aa[aa]]
_DATA_INICIO = re.compile(r"^\s*(\d{1,2}[/.\-]\d{1,2}(?:[/.\-]\d{2,4})?)\b")


def parse_generico(caminho: str, banco: str, tipo: str = CONTA_CORRENTE) -> Extrato:
    """Melhor esforço para um layout desconhecido: uma transação por linha que
    comece com data e contenha ao menos um valor monetário (com centavos)."""
    linhas = linhas_do_pdf(caminho)
    ano = ano_do_texto(linhas)
    transacoes: list[Transacao] = []

    for linha in linhas:
        m = _DATA_INICIO.match(linha)
        if not m:
            continue
        data = parse_data(m.group(1), ano_padrao=ano)
        if not data:
            continue

        valores = apenas_valores(linha)  # já exige centavos (,dd)
        if not valores:
            continue

        # Convenção: último número = saldo se houver 2+, senão o único é o valor.
        if len(valores) >= 2:
            valor, saldo = valores[-2], valores[-1]
        else:
            valor, saldo = valores[-1], None

        # Descrição = trecho entre a data e o primeiro valor.
        resto = linha[m.end():]
        corte = re.search(r"\d{1,3}(?:\.\d{3})*,\d{2}", resto)
        descricao = resto[: corte.start()] if corte else resto

        transacoes.append(
            Transacao(
                data=data,
                descricao=descricao.strip(" -\t"),
                valor=valor,
                saldo=saldo,
                banco=banco,
            )
        )
    # Muitos extratos vêm do mais recente ao mais antigo; a auditoria de
    # saldos parciais pressupõe ordem cronológica crescente. Sort estável:
    # empates de data preservam a ordem do PDF.
    transacoes.sort(key=lambda t: t.data or date.min)
    return Extrato(banco=banco, tipo_documento=tipo, transacoes=transacoes)
