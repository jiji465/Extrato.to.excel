"""Motor de categorização automática de lançamentos.

Classifica cada transação numa categoria útil para a contabilidade a partir de
regras (palavras-chave/regex) sobre a descrição. As regras ficam todas em
`REGRAS`, numa única tabela, ordenadas por prioridade — a primeira que casar
vence. Fáceis de editar/estender.

A comparação é insensível a acentos e maiúsculas.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable

from .normalizar import Transacao

NAO_CLASSIFICADO = "Não classificado"


def _sem_acento(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


# (categoria, [padrões]). Ordem = prioridade. Padrões já sem acento/minúsculos.
# Mais específicos (impostos, pix) antes dos mais genéricos (boleto, transf.).
REGRAS: list[tuple[str, list[str]]] = [
    ("Impostos e Tributos", [
        r"\bdarf\b", r"\bdas\b", r"\bgps\b", r"\bgru\b", r"\bdare\b",
        r"simples nacional", r"\bicms\b", r"\biss\b", r"\bipva\b", r"\birpj\b",
        r"\binss\b", r"\bfgts\b", r"tribut", r"imposto", r"licenciamento",
        r"\bpgdas\b", r"receita federal", r"prefeitura", r"sefaz",
    ]),
    ("Tarifas e Juros", [
        r"tarifa", r"\btar\b", r"pacote de servic", r"cesta", r"manutenc",
        r"manut", r"anuidade", r"\biof\b", r"juros", r"multa", r"encargo",
        r"\bced\b", r"cta garantida",
    ]),
    ("Empréstimos e Financiamentos", [
        r"empr[eé]stimo", r"capital giro", r"financiam", r"\bpeac\b",
        r"\bfgi\b", r"consignad", r"cr[eé]dito parcelad",
    ]),
    ("Folha e Salários", [
        r"salario", r"\bfolha\b", r"pro.?labore", r"vencimento",
        r"adiantamento", r"rescis", r"decimo terceiro", r"\b13\b", r"ferias",
        r"remuneracao (?!aplicac)",  # remuneração de folha, não de aplicação
    ]),
    ("Rendimentos e Aplicações", [
        r"remuneracao aplicac", r"aplicac", r"resgate", r"rendimento",
        r"rende f[aá]cil", r"\bcdb\b", r"\brdb\b", r"\blci\b", r"\blca\b",
        r"investiment", r"tesouro", r"fundo",
    ]),
    ("Seguros", [
        r"seguro", r"segurador", r"tokio", r"porto seguro", r"previdenc",
    ]),
    ("Concessionárias", [
        r"agua", r"esgoto", r"saneament", r"energia", r"eletric", r"\bgas\b",
        r"\bluz\b", r"telefon", r"internet", r"celular", r"\bvivo\b",
        r"\bclaro\b", r"\btim\b", r"\boi\b", r"copasa", r"cemig", r"enel",
        r"sabesp", r"copel", r"light",
    ]),
    ("Cartão de crédito", [
        r"cartao de credito", r"fatura", r"mastercard", r"master card",
        r"\bvisa\b", r"\belo\b", r"pagamento cartao",
    ]),
    ("Pix recebido", [
        r"pix[\s\-]*recebido", r"recebida pelo pix", r"recebido pelo pix",
    ]),
    ("Pix enviado", [
        r"pix[\s\-]*enviado", r"pix[\s\-]*agendado", r"enviada pelo pix",
        r"enviado pelo pix",
    ]),
    ("Compras", [
        r"compra no debito", r"compra no credito", r"compra com cartao",
        r"\bcompra\b",
    ]),
    ("Boletos e Fornecedores", [
        r"boleto", r"pagamento de boleto", r"fornecedor", r"pagamento a",
    ]),
    ("Transferências", [
        r"\bted\b", r"\bdoc\b", r"transferenc", r"transf ", r"transf\.",
    ]),
    ("Saques e Depósitos", [
        r"saque", r"deposito", r"deposit", r"dep dinheiro", r"dep .*atm",
    ]),
]

# Pré-compila para eficiência.
_REGRAS_COMPILADAS = [
    (cat, [re.compile(p) for p in pats]) for cat, pats in REGRAS
]


def classificar(descricao: str) -> str:
    """Categoria de uma descrição isolada (ou NAO_CLASSIFICADO)."""
    alvo = _sem_acento(descricao)
    for categoria, padroes in _REGRAS_COMPILADAS:
        for p in padroes:
            if p.search(alvo):
                return categoria
    return NAO_CLASSIFICADO


def categorizar(transacoes: Iterable[Transacao]) -> list[Transacao]:
    """Preenche `categoria` de cada transação (respeita valor já definido).

    Classifica pela descrição (tipo) + favorecido, já que o nome da contraparte
    às vezes carrega o sinal da categoria (ex.: concessionária, seguradora)."""
    lista = list(transacoes)
    for t in lista:
        if not t.categoria:
            t.categoria = classificar(f"{t.descricao} {t.favorecido}")
    return lista
