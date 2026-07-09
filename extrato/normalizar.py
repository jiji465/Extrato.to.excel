"""Utilidades de normalização: datas pt-BR, valores em reais e o modelo comum
de transação usado por todos os parsers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Modelo comum de transação
# ---------------------------------------------------------------------------
# Tipos de documento suportados
CONTA_CORRENTE = "conta_corrente"
FATURA = "fatura"
INVESTIMENTO = "investimento"


@dataclass
class Transacao:
    """Uma linha de extrato, já normalizada.

    valor: número com sinal. Negativo = saída (débito), positivo = entrada.
    saldo: saldo após a transação, quando o extrato fornece (senão None).
    Campos opcionais cobrem faturas de cartão (parcela, moeda/valor de origem)
    e a categorização automática.
    """

    data: Optional[date]
    descricao: str            # histórico/tipo do lançamento (ex.: "PIX ENVIADO")
    valor: float
    banco: str
    tipo: str = ""            # "Crédito" ou "Débito" (preenchido em pos_processar)
    saldo: Optional[float] = None
    documento: str = ""       # nº do documento/identificador
    favorecido: str = ""      # contraparte (quem recebeu/enviou)
    hora: str = ""            # hora do lançamento, quando o extrato traz
    arquivo: str = ""         # nome do PDF de origem (p/ conferência por arquivo)
    categoria: str = ""       # preenchido pelo categorizador
    parcela: str = ""         # ex.: "3/12" (faturas)
    moeda_origem: str = ""    # ex.: "USD" (compras internacionais)
    valor_origem: Optional[float] = None

    def to_row(self) -> dict:
        d = asdict(self)
        return d


@dataclass
class Extrato:
    """Resultado da leitura de um PDF: transações + metadados de conferência.

    Os campos de resumo são preenchidos pelos parsers que conseguem lê-los no
    PDF; servem para a auditoria de reconciliação. Ficam None quando o layout
    não os fornece. Quais campos importam depende de `tipo_documento`:

    - conta corrente: saldo_inicial/final, total_creditos/debitos
    - fatura:         saldo_anterior, total_fatura, vencimento
    - investimento:   saldo_anterior, saldo_atual, rendimento
    """

    banco: str
    tipo_documento: str = CONTA_CORRENTE
    transacoes: list[Transacao] = field(default_factory=list)
    # conta corrente
    saldo_inicial: Optional[float] = None
    saldo_final: Optional[float] = None
    total_creditos: Optional[float] = None
    total_debitos: Optional[float] = None
    # fatura de cartão
    saldo_anterior: Optional[float] = None
    total_fatura: Optional[float] = None
    vencimento: Optional[date] = None
    # investimento
    saldo_atual: Optional[float] = None
    rendimento: Optional[float] = None


# ---------------------------------------------------------------------------
# Datas
# ---------------------------------------------------------------------------
_MESES = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}


def parse_data(texto: str, ano_padrao: Optional[int] = None) -> Optional[date]:
    """Converte formatos comuns de data brasileira em datetime.date.

    Aceita: 01/02/2024, 01/02/24, 01-02-2024, "01 FEV 2024", "01 FEV",
    "1 de fevereiro de 2024".
    """
    if not texto:
        return None
    t = texto.strip().lower()

    # dd/mm/aaaa ou dd/mm/aa (aceita / . -)
    m = re.search(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})", t)
    if m:
        dia, mes, ano = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if ano < 100:
            ano += 2000
        return _try_date(ano, mes, dia)

    # dd/mm (sem ano) -> usa ano_padrao
    m = re.search(r"(\d{1,2})[/.\-](\d{1,2})(?!\d)", t)
    if m and ano_padrao:
        return _try_date(ano_padrao, int(m.group(2)), int(m.group(1)))

    # "01 fev 2024" ou "01 de fevereiro de 2024" ou "01 fev"
    m = re.search(r"(\d{1,2})\s*(?:de\s+)?([a-zç]{3,})\.?\s*(?:de\s+)?(\d{4})?", t)
    if m:
        mes_txt = m.group(2)[:3]
        if mes_txt in _MESES:
            ano = int(m.group(3)) if m.group(3) else ano_padrao
            if ano:
                return _try_date(ano, _MESES[mes_txt], int(m.group(1)))
    return None


def _try_date(ano: int, mes: int, dia: int) -> Optional[date]:
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Valores monetários (R$ 1.234,56)
# ---------------------------------------------------------------------------
_VALOR_RE = re.compile(
    r"(?P<sinal>[-+]|\(|\bD\b|\bC\b)?\s*"
    r"R?\$?\s*"
    r"(?P<num>\d{1,3}(?:\.\d{3})*(?:,\d{2})|\d+,\d{2}|\d+)"
    r"\s*(?P<pos>-|\)|D|C)?",
    re.IGNORECASE,
)


def parse_valor(texto: str) -> Optional[float]:
    """Converte um valor monetário brasileiro em float com sinal.

    Reconhece sinais por: prefixo '-', parênteses (1.234,56), e sufixos
    'D' (débito) / 'C' (crédito) muito comuns em extratos brasileiros.
    """
    if texto is None:
        return None
    t = str(texto).strip()
    if not t:
        return None

    m = _VALOR_RE.search(t)
    if not m:
        return None

    num = m.group("num").replace(".", "").replace(",", ".")
    try:
        valor = float(num)
    except ValueError:
        return None

    sinal = (m.group("sinal") or "").upper()
    pos = (m.group("pos") or "").upper()
    negativo = (
        sinal in {"-", "("}
        or sinal == "D"
        or pos in {"-", ")"}
        or pos == "D"
    )
    return -valor if negativo else valor


# Token monetário brasileiro ESTRITO: exige centavos (,dd). Assim números de
# documento, agências e CNPJ (inteiros sem vírgula) nunca são confundidos com
# valores. O sinal de débito pode vir COLADO antes ("-166,40", padrão Bradesco)
# ou depois dos centavos ("5,93-", padrão Santander). Um "- " com espaço (coluna
# de documento vazia, ex. Santander) NÃO conta como sinal — por isso o '-' líder
# só vale quando encostado no número.
_BRL_RE = re.compile(
    r"(?<![\d.,\-])(-)?(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})(-)?"
)


def valores_brl(texto: str) -> list[tuple[float, bool, int, int]]:
    """Extrai valores monetários em reais de uma linha.

    Retorna tuplas (valor_absoluto, negativo, inicio, fim) na ordem em que
    aparecem. `negativo` é True quando há '-' colado antes ou depois do número.
    `inicio` aponta para o início do número (sem o sinal líder), preservando o
    comportamento de fatiar a descrição.
    """
    out: list[tuple[float, bool, int, int]] = []
    for m in _BRL_RE.finditer(texto):
        num = m.group(2).replace(".", "").replace(",", ".")
        try:
            valor = float(num)
        except ValueError:
            continue
        neg = (m.group(1) == "-") or (m.group(3) == "-")
        out.append((valor, neg, m.start(2), m.end()))
    return out


def apenas_valores(texto: str) -> list[float]:
    """Extrai todos os valores monetários (com sinal) de uma linha, na ordem.

    Exige centavos, portanto ignora inteiros soltos (nº de documento etc.)."""
    return [(-v if neg else v) for v, neg, _, _ in valores_brl(texto)]


# ---------------------------------------------------------------------------
# Pós-processamento comum
# ---------------------------------------------------------------------------
def pos_processar(transacoes: list[Transacao]) -> list[Transacao]:
    """Preenche o campo 'tipo' e limpa a descrição."""
    for t in transacoes:
        if not t.tipo:
            t.tipo = "Crédito" if t.valor >= 0 else "Débito"
        t.descricao = re.sub(r"\s+", " ", (t.descricao or "").strip())
    return transacoes
