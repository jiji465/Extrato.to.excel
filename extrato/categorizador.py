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


# (categoria, [padrões], so_descricao). Ordem = prioridade. Padrões já sem
# acento/minúsculos. Mais específicos (impostos, pix) antes dos genéricos.
# so_descricao=True: a regra NÃO é aplicada ao favorecido — tokens curtos
# ("tim", "luz", "folha"...) casariam nomes de pessoas/empresas da contraparte.
REGRAS: list[tuple[str, list[str], bool]] = [
    ("Impostos e Tributos", [
        # sem r"\bdas\b" solto: casaria a preposição "das" ("compra das peças")
        r"\bdarf\b", r"\bgps\b", r"\bgru\b", r"\bdare\b",
        r"simples nacional", r"das\s*-\s*simples", r"pagamento de das\b",
        r"\bicms\b", r"\biss\b", r"\bipva\b", r"\birpj\b",
        r"\binss\b", r"\bfgts\b", r"tribut", r"imposto", r"licenciamento",
        r"\bpgdas\b", r"receita federal", r"prefeitura", r"sefaz",
    ], False),
    ("Tarifas e Juros", [
        r"tarifa", r"\btar\b", r"pacote de servic", r"cesta", r"manutenc",
        r"manut", r"anuidade", r"\biof\b", r"juros", r"multa", r"encargo",
        r"\bced\b", r"cta garantida",
    ], True),
    ("Empréstimos e Financiamentos", [
        r"empr[eé]stimo", r"capital giro", r"financiam", r"\bpeac\b",
        r"\bfgi\b", r"consignad", r"cr[eé]dito parcelad",
    ], False),
    ("Folha e Salários", [
        # sem r"\b13\b" ("rua 13 de maio") e sem r"vencimento" genérico
        # (vencimento de boleto); o caso de folha fica em "liquido de vencimento"
        r"salario", r"\bfolha\b", r"pro.?labore", r"liquido de vencimento",
        r"adiantamento", r"rescis", r"decimo terceiro", r"13[oº°]?\s*salario",
        r"ferias",
        r"remuneracao (?!aplicac)",  # remuneração de folha, não de aplicação
    ], True),
    ("Rendimentos e Aplicações", [
        r"remuneracao aplicac", r"aplicac", r"resgate", r"rendimento",
        r"rende f[aá]cil", r"\bcdb\b", r"\brdb\b", r"\blci\b", r"\blca\b",
        r"investiment", r"tesouro", r"fundo",
    ], True),
    ("Seguros", [
        r"seguro", r"segurador", r"tokio", r"porto seguro", r"previdenc",
    ], False),
    ("Concessionárias", [        # nomes inequívocos: valem também no favorecido
        r"agua", r"esgoto", r"saneament", r"energia", r"eletric",
        r"telefon", r"\binternet\b", r"copasa", r"cemig", r"enel",
        r"sabesp", r"copel", r"light",
    ], False),
    ("Concessionárias", [        # tokens curtos: só na descrição (são nomes
        r"\bgas\b", r"\bluz\b", r"celular", r"\bvivo\b",   # comuns de pessoas)
        r"\bclaro\b", r"\btim\b", r"\boi\b",
    ], True),
    ("Cartão de crédito", [
        r"cartao de credito", r"fatura", r"mastercard", r"master card",
        r"\bvisa\b", r"\belo\b", r"pagamento cartao",
    ], True),
    ("Pix recebido", [
        r"pix[\s\-]*recebido", r"recebida pelo pix", r"recebido pelo pix",
        r"pix[\s.\-]*receb", r"transf[\s.\-]*receb[\s.\-]*pix",  # Sicoob: PIX RECEB.OUTRA IF
    ], True),
    ("Pix enviado", [
        r"pix[\s\-]*enviado", r"pix[\s\-]*agendado", r"enviada pelo pix",
        r"enviado pelo pix",
        r"pix[\s.\-]*emit", r"transf[\s.]*pix",  # Sicoob: PIX EMIT.OUTRA IF / TRANSF. PIX
    ], True),
    ("Compras", [
        r"compra no debito", r"compra no credito", r"compra com cartao",
        r"\bcompra\b",
    ], True),
    ("Boletos e Fornecedores", [
        r"boleto", r"pagamento de boleto", r"fornecedor", r"pagamento a",
        r"tit\.?\s*compe", r"deb\.?\s*tit", r"tit\.?\s*cobran",  # Sicoob: DÉB.TIT.COMPE / DÉB.TIT.COBRANÇA
    ], True),
    ("Cobrança recebida", [
        r"liq\.?\s*cobran", r"cred\.?\s*liq",  # Sicoob: CRÉD.LIQ.COBRANÇA (títulos recebidos)
    ], True),
    ("Transferências", [
        r"\bted\b", r"\btev\b", r"\bdoc\b", r"transferenc", r"transf",
        r"envio.*transf",  # Caixa (OCR junta palavras): ENVIOTRANSFINTERNETTEV
    ], True),
    ("Saques e Depósitos", [
        r"saque", r"deposito", r"deposit", r"dep dinheiro", r"dep .*atm",
        r"dep\.?\s*dinheiro", r"dep\s+din",  # Sicoob: DEP.DINHEIRO / DEP DIN AG
    ], True),
]

# Pré-compila para eficiência.
_REGRAS_COMPILADAS = [
    (cat, [re.compile(p) for p in pats], so_desc) for cat, pats, so_desc in REGRAS
]


def _classificar(alvo_sem_acento: str, incluir_so_descricao: bool = True) -> str:
    for categoria, padroes, so_desc in _REGRAS_COMPILADAS:
        if so_desc and not incluir_so_descricao:
            continue
        for p in padroes:
            if p.search(alvo_sem_acento):
                return categoria
    return NAO_CLASSIFICADO


def classificar(descricao: str) -> str:
    """Categoria de uma descrição isolada (ou NAO_CLASSIFICADO)."""
    return _classificar(_sem_acento(descricao))


def categorizar(transacoes: Iterable[Transacao]) -> list[Transacao]:
    """Preenche `categoria` de cada transação (respeita valor já definido).

    Primeiro classifica pela DESCRIÇÃO (tipo do lançamento, texto do banco);
    só quando ela não decide, tenta o FAVORECIDO — e aí pulando as regras de
    tokens curtos (so_descricao), que casariam nomes de pessoas ("TIM SILVA",
    "MARIA LUZ")."""
    lista = list(transacoes)
    for t in lista:
        if not t.categoria:
            cat = _classificar(_sem_acento(t.descricao))
            if cat == NAO_CLASSIFICADO and t.favorecido:
                cat = _classificar(_sem_acento(t.favorecido),
                                   incluir_so_descricao=False)
            t.categoria = cat
    return lista
