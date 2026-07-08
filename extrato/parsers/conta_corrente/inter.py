"""Parser de conta corrente do Banco Inter. Placeholder: usa o extrator genérico
até termos um PDF de exemplo. A auditoria avisa quando o layout não fecha."""

from __future__ import annotations

from ...normalizar import CONTA_CORRENTE, Extrato
from ..base import parse_generico

BANCO = "Banco Inter"


def parse(caminho: str) -> Extrato:
    return parse_generico(caminho, BANCO, CONTA_CORRENTE)
