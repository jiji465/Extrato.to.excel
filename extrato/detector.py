"""Identifica banco e tipo de documento de um PDF a partir do texto extraído."""

from __future__ import annotations

import re

from .normalizar import CONTA_CORRENTE, FATURA, INVESTIMENTO


# Cada entrada: (chave_do_banco, nome_exibicao, [padrões regex de assinatura]).
# A ordem importa: bancos mais específicos primeiro para evitar falso-positivo.
_ASSINATURAS = [
    ("nubank", "Nubank", [r"nubank", r"nu pagamentos", r"18\.236\.120/0001-58"]),
    ("inter", "Banco Inter", [r"banco inter", r"00\.416\.968/0001-01"]),
    ("c6", "C6 Bank", [r"c6\s*bank", r"banco c6", r"31\.872\.495/0001-72"]),
    ("sicoob", "Sicoob",
     [r"sicoob", r"\bsisbr\b", r"cooperativas de cr[eé]dito do brasil",
      r"02\.038\.232/0001-64"]),
    ("itau", "Itaú", [r"ita[uú]", r"60\.701\.190/0001-04"]),
    ("bradesco", "Bradesco",
     [r"bradesco", r"60\.746\.948/0001-12", r"rentab\.invest", r"facilcred",
      r"extrato mensal\s*/\s*por período"]),
    ("santander", "Santander", [r"santander", r"90\.400\.888/0001-42"]),
    ("banco_do_brasil", "Banco do Brasil",
     [r"banco do brasil", r"00\.000\.000/0001-91", r"bb rende", r"rende f[aá]cil",
      r"dia lote documento hist[oó]rico", r"capital giro peac"]),
    # "\bcaixa\b" sozinho casaria "caixa eletrônico"/"fluxo de caixa" de outros
    # bancos; usamos assinaturas específicas ("extrato por período" é o título
    # do layout da Caixa, presente inclusive no texto vindo do OCR).
    ("caixa", "Caixa Econômica Federal",
     [r"caixa econ[oô]mica", r"00\.360\.305/0001-04",
      r"extrato por per[ií]odo", r"caixa\s*tem", r"\bcef\b"]),
]

# Sinais de cada tipo de documento (pontuação por palavra-chave encontrada).
_SINAIS_TIPO = {
    FATURA: [
        r"fatura", r"vencimento da fatura", r"total da fatura",
        r"pagamento m[ií]nimo", r"limite de cr[eé]dito", r"limite total",
        r"melhor dia de compra", r"fecham?ento", r"cart[aã]o de cr[eé]dito",
    ],
    INVESTIMENTO: [
        r"saldo bruto", r"rendimento", r"\bCDB\b", r"\bRDB\b", r"\bLCI\b",
        r"\bLCA\b", r"tesouro direto", r"valor l[ií]quido", r"aplica[cç][aã]o",
        r"resgate", r"carteira de investimentos", r"posi[cç][aã]o consolidada",
    ],
    CONTA_CORRENTE: [
        r"movimenta[cç][aã]o", r"conta corrente", r"saldo em \d",
        r"movimento\s*\(r\$\)", r"saldo\s*\(r\$\)", r"saldo anterior",
        r"extrato", r"lan[cç]amentos", r"saldo do dia", r"saldo inicial",
        r"total de entradas", r"total de sa[íi]das",
        r"transfer[eê]ncia (enviada|recebida)",
    ],
}


def detectar_banco(texto: str) -> tuple[str, str]:
    """Retorna (chave, nome_exibicao). ('desconhecido', 'Desconhecido') se nada casar."""
    t = (texto or "").lower()
    for chave, nome, padroes in _ASSINATURAS:
        for p in padroes:
            if re.search(p, t):
                return chave, nome
    return "desconhecido", "Desconhecido"


def detectar_tipo(texto: str) -> str:
    """Classifica o documento em conta_corrente | fatura | investimento.

    Conta pontos por palavra-chave de cada tipo; desempate favorece conta
    corrente (caso mais comum). Fatura tem prioridade sobre conta corrente
    quando há sinais fortes e exclusivos ('total da fatura', 'pagamento mínimo').
    """
    t = (texto or "").lower()
    placar = {tipo: 0 for tipo in _SINAIS_TIPO}
    for tipo, padroes in _SINAIS_TIPO.items():
        for p in padroes:
            if re.search(p, t):
                placar[tipo] += 1

    # Sinais fortes e exclusivos de fatura vencem a conta corrente.
    fortes_fatura = any(
        re.search(p, t) for p in
        (r"total da fatura", r"pagamento m[ií]nimo", r"limite de cr[eé]dito")
    )
    if fortes_fatura:
        placar[FATURA] += 3

    # Desempate EXPLÍCITO a favor de conta corrente (caso mais comum): o max
    # sobre o dict venceria pela ordem de inserção (fatura), não pela intenção.
    ordem = [CONTA_CORRENTE, FATURA, INVESTIMENTO]
    melhor = max(ordem, key=lambda k: placar[k])
    return melhor if placar[melhor] > 0 else CONTA_CORRENTE


def detectar(texto: str) -> tuple[str, str, str]:
    """Retorna (banco_chave, banco_nome, tipo_documento)."""
    chave, nome = detectar_banco(texto)
    tipo = detectar_tipo(texto)
    return chave, nome, tipo
