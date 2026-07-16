"""Registro de parsers, chaveado por (banco, tipo_documento).

Cada parser expõe `parse(caminho) -> Extrato`. `obter_parser` devolve o parser
dedicado para o par (banco, tipo); se não houver, cai no extrator genérico
(`base.parse_generico`) preservando banco e tipo — a auditoria avisa quando o
layout genérico não fecha.
"""

from __future__ import annotations

from typing import Callable

from ..normalizar import CONTA_CORRENTE, FATURA, INVESTIMENTO, Extrato
from . import base
from .conta_corrente import (
    santander as cc_santander,
    nubank as cc_nubank,
    itau as cc_itau,
    bradesco as cc_bradesco,
    banco_do_brasil as cc_bb,
    caixa as cc_caixa,
    inter as cc_inter,
    c6 as cc_c6,
    sicoob as cc_sicoob,
)

Parser = Callable[[str], Extrato]

# (banco, tipo) -> parser dedicado
_REGISTRO: dict[tuple[str, str], Parser] = {
    ("santander", CONTA_CORRENTE): cc_santander.parse,
    ("nubank", CONTA_CORRENTE): cc_nubank.parse,
    ("itau", CONTA_CORRENTE): cc_itau.parse,
    ("bradesco", CONTA_CORRENTE): cc_bradesco.parse,
    ("banco_do_brasil", CONTA_CORRENTE): cc_bb.parse,
    ("caixa", CONTA_CORRENTE): cc_caixa.parse,
    ("inter", CONTA_CORRENTE): cc_inter.parse,
    ("c6", CONTA_CORRENTE): cc_c6.parse,
    ("sicoob", CONTA_CORRENTE): cc_sicoob.parse,
    # Faturas e investimentos: parsers dedicados serão registrados aqui
    # conforme os PDFs de exemplo forem chegando.
}


def obter_parser(chave_banco: str, nome_exibicao: str, tipo: str) -> Parser:
    parser = _REGISTRO.get((chave_banco, tipo))
    if parser is not None:
        return parser
    # Sem parser dedicado -> extrator genérico, preservando nome e tipo.
    return lambda caminho: base.parse_generico(caminho, nome_exibicao, tipo)
