"""Parser de conta corrente do Sicoob (SISBR) — "Histórico de Movimentação".

Layout (uma transação por linha visual, na coluna certa):

    DATA   HISTÓRICO ..................................   VALOR[C|D]
    DOC.: <documento>
    <continuação: subtipo Pix, nome/CPF/CNPJ da contraparte, REM.:/FAV.:>

Particularidades resolvidas por COORDENADAS de palavra (extract_text embaralha
as quebras deste layout):

- A coluna VALOR é alinhada à direita (x1≈480). Quando o número é largo, o
  pdfplumber "quebra" o valor para a linha logo ACIMA da data e o indicador
  C/D para a linha logo ABAIXO — e, na virada de página, o C/D fica na PRÓPRIA
  linha da data. Por isso valor e sinal são associados por vizinhança vertical.
- Sufixo C = crédito (entrada); D = débito (saída); '*' = saldo bloqueado.
- O extrato vem em ordem cronológica INVERSA (30/06 → 'SALDO ANTERIOR' 29/05).
  'SALDO ANTERIOR' é o saldo inicial; o 'SALDO DO DIA' do último dia é o saldo
  final; cada 'SALDO DO DIA' vira checkpoint do saldo do último lançamento do
  dia (conferência linha a linha).
- Os acentos do histórico chegam corrompidos (fonte CID); um pequeno mapa do
  vocabulário fixo do Sicoob os restaura para o Excel.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

from ...normalizar import CONTA_CORRENTE, Extrato, Transacao, parse_data
from ...extracao import Palavra
from ..base import palavras_do_pdf, linhas_por_coordenada

BANCO = "Sicoob"

# Fronteiras de coluna (pt na página A4 do extrato Sicoob).
_X_DATA_MAX = 145        # data fica em x0≈115
_X_DESC_MAX = 430        # histórico entre ~154 e ~363
_X_VALOR_MIN = 430       # coluna VALOR alinhada à direita, x1≈480
_X_VALOR_DIR = 468       # borda direita mínima p/ um token da coluna VALOR

_DATA = re.compile(r"^\d{2}/\d{2}$")
_VALNUM = re.compile(r"^(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})([CD*])?$")
_CPF = re.compile(r"^\*{3}\.\d{3}\.\d{3}-\*{2}$")
_CNPJ = re.compile(r"^\d{2}\.\d{3}\.\d{3}\s*\d{4}-\d{2}$")
_SUBTIPO_PIX = re.compile(r"^(recebimento pix|transfer.*pix)$", re.IGNORECASE)

# Acentos perdidos (�) no vocabulário fixo de históricos do Sicoob.
_ACENTOS = [
    ("COBRAN�A", "COBRANÇA"),
    ("SERVI�OS", "SERVIÇOS"),
    ("ORG�OS", "ÓRGÃOS"),
    ("D�B", "DÉB"),
    ("CR�D", "CRÉD"),
]


def _limpar_desc(desc: str) -> str:
    for ruim, bom in _ACENTOS:
        desc = desc.replace(ruim, bom)
    return re.sub(r"\s+", " ", desc).strip()


def _ano(linhas_texto: list[str]) -> int:
    """Ano de referência: preferir a data inicial do PERÍODO; senão 1º ano visto."""
    for l in linhas_texto:
        if "PER" in l and "ODO" in l:
            m = re.search(r"\d{2}/\d{2}/(20\d{2})", l)
            if m:
                return int(m.group(1))
    for l in linhas_texto:
        m = re.search(r"\b(20\d{2})\b", l)
        if m:
            return int(m.group(1))
    return date.today().year


def _valor_da_palavra(w: Palavra) -> Optional[tuple[float, Optional[str]]]:
    """(numero, sinal|None) se `w` é um token monetário da coluna VALOR."""
    if w.x1 < _X_VALOR_DIR or w.x0 < _X_VALOR_MIN:
        return None
    m = _VALNUM.match(w.texto)
    if not m:
        return None
    num = float(m.group(1).replace(".", "").replace(",", "."))
    return num, m.group(2)


def _sinal_solto(linha: list[Palavra]) -> Optional[str]:
    """'C'/'D' isolado na coluna VALOR (indicador que 'vazou' de outra linha)."""
    if len(linha) == 1 and linha[0].texto in ("C", "D") and linha[0].x1 >= _X_VALOR_DIR:
        return linha[0].texto
    return None


def _aplicar_continuacao(ln: list[Palavra], t: Transacao, fav_travado: bool) -> bool:
    """Enriqulece a transação `t` com uma linha de continuação. Retorna True se o
    favorecido passou a vir de REM.:/FAV.: (autoritativo, trava sobrescrita)."""
    # órfão de valor ou sinal solto não são continuação de texto
    if len(ln) == 1 and (_valor_da_palavra(ln[0]) or _sinal_solto(ln)):
        return fav_travado
    txt = " ".join(w.texto for w in ln if w.x0 < _X_VALOR_MIN).strip()
    if not txt:
        return fav_travado

    if txt.startswith("DOC.:"):
        doc = txt[len("DOC.:"):].strip()
        if doc and doc.lower() != "pix":
            t.documento = doc
        return fav_travado

    m = re.match(r"^(?:REM\.:|FAV\.:)\s*(.+)$", txt)
    if m:
        t.favorecido = m.group(1).strip()
        return True

    if _SUBTIPO_PIX.match(txt) or _CPF.match(txt) or _CNPJ.match(txt):
        return fav_travado

    # primeira linha de nome vira favorecido (se ainda não veio de REM/FAV)
    if not fav_travado and not t.favorecido:
        t.favorecido = txt
    return fav_travado


def parse(caminho: str) -> Extrato:
    linhas = linhas_por_coordenada(palavras_do_pdf(caminho))
    linhas_texto = [" ".join(w.texto for w in ln) for ln in linhas]
    ano = _ano(linhas_texto)

    extrato = Extrato(banco=BANCO, tipo_documento=CONTA_CORRENTE)
    transacoes: list[Transacao] = []
    saldos_dia: dict[str, float] = {}   # "dd/mm" -> saldo de fechamento do dia
    atual: Optional[Transacao] = None   # transação recebendo linhas de continuação
    fav_travado = False                 # favorecido veio de REM.:/FAV.: (autoritativo)
    n = len(linhas)

    for i, ln in enumerate(linhas):
        primeiro = ln[0]
        eh_ancora = bool(_DATA.match(primeiro.texto)) and primeiro.x0 < _X_DATA_MAX

        if not eh_ancora:
            if atual is not None:
                fav_travado = _aplicar_continuacao(ln, atual, fav_travado)
            continue

        data_str = primeiro.texto
        desc = _limpar_desc(
            " ".join(w.texto for w in ln if _X_DATA_MAX <= w.x0 < _X_DESC_MAX)
        )

        # valor: token na própria linha, senão o "órfão" na linha imediatamente acima
        vv = None
        for w in ln:
            r = _valor_da_palavra(w)
            if r:
                vv = r
        if vv is None and i > 0 and len(linhas[i - 1]) == 1:
            vv = _valor_da_palavra(linhas[i - 1][0])
        if vv is None:
            atual = None
            continue

        valor, sinal = vv
        if sinal in (None, "*"):
            # 'C'/'D' isolado na PRÓPRIA linha da data (valor veio do rodapé da
            # página anterior) tem prioridade sobre o da linha de baixo.
            for w in ln:
                if w.texto in ("C", "D") and w.x1 >= _X_VALOR_DIR:
                    sinal = w.texto
                    break
        if sinal in (None, "*") and i + 1 < n:
            s = _sinal_solto(linhas[i + 1])
            if s:
                sinal = s

        assinado = -valor if sinal == "D" else valor

        # Marcadores de saldo (não são lançamentos).
        if "SALDO DO DIA" in desc:
            saldos_dia[data_str] = assinado
            if extrato.saldo_final is None:     # 1º encontrado = dia mais recente
                extrato.saldo_final = assinado
            atual = None
            continue
        if "SALDO ANTERIOR" in desc:
            extrato.saldo_inicial = assinado
            atual = None
            continue
        if "SALDO BLOQ" in desc or sinal == "*":
            atual = None
            continue

        t = Transacao(
            data=parse_data(f"{data_str}/{ano}"),
            descricao=desc,
            valor=assinado,
            banco=BANCO,
        )
        transacoes.append(t)
        atual = t
        fav_travado = False

    # Ordena cronologicamente (o PDF vem invertido) e fixa os checkpoints de saldo
    # no último lançamento de cada dia (bate com o 'SALDO DO DIA').
    transacoes.sort(key=lambda t: (t.data or date.min))
    ultimo_do_dia: dict[str, int] = {}
    for idx, t in enumerate(transacoes):
        if t.data:
            ultimo_do_dia[t.data.strftime("%d/%m")] = idx
    for dia, idx in ultimo_do_dia.items():
        if dia in saldos_dia:
            transacoes[idx].saldo = saldos_dia[dia]

    extrato.transacoes = transacoes
    return extrato
