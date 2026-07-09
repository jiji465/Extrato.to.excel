"""Extrai a identificação do extrato (titular/empresa e período) para nomear o
Excel de forma autoexplicativa: "Extrato - <Empresa> - <Banco> - <Mês>.xlsx".
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

_MESES = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
          "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


def _limpa_nome(nome: str) -> str:
    nome = re.split(r"\|", nome)[0]                 # corta "| CNPJ ..."
    nome = re.sub(r"\bCNPJ\b.*|\bCPF\b.*", "", nome, flags=re.I)
    nome = re.sub(r"\s+", " ", nome).strip(" -\t")
    return nome


def extrair_titular(texto: str, banco_chave: str) -> str:
    """Nome do titular/empresa do extrato, conforme o layout de cada banco."""
    linhas = [l.strip() for l in (texto or "").split("\n")]

    if banco_chave == "santander":
        for i, l in enumerate(linhas):
            if l.lower() == "nome" and i + 1 < len(linhas):
                return _limpa_nome(linhas[i + 1])

    if banco_chave == "nubank":
        for l in linhas:
            if l and not re.match(r"(cnpj|cpf|agência|conta|valores|\d)", l, re.I):
                return _limpa_nome(l)

    if banco_chave == "bradesco":
        for l in linhas:
            if re.search(r"\|\s*cnpj", l, re.I):
                return _limpa_nome(l)

    # BB, Caixa e genérico: linha "Cliente <NOME>"
    for l in linhas:
        m = re.match(r"cliente\s+(.+)", l, re.I)
        if m:
            return _limpa_nome(m.group(1))
    return ""


def periodo_das_datas(datas: list[Optional[date]]) -> str:
    """Rótulo de período a partir das datas dos lançamentos (uniforme p/ todos)."""
    ds = [d for d in datas if d]
    if not ds:
        return ""
    dmin, dmax = min(ds), max(ds)
    if dmin.year == dmax.year and dmin.month == dmax.month:
        return f"{_MESES[dmin.month]}-{dmin.year}"
    if dmin.year == dmax.year:
        return f"{_MESES[dmin.month]}-a-{_MESES[dmax.month]}-{dmin.year}"
    return f"{_MESES[dmin.month]}-{dmin.year}-a-{_MESES[dmax.month]}-{dmax.year}"


def sanitizar_arquivo(nome: str) -> str:
    """Remove caracteres inválidos em nomes de arquivo."""
    nome = re.sub(r'[\\/:*?"<>|]+', " ", nome)
    nome = re.sub(r"\s+", " ", nome).strip(" .-")
    return nome[:120] or "extrato"
