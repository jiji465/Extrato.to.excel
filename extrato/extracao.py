"""Toolkit de extração de PDF.

Oferece três estratégias que os parsers escolhem conforme o layout:

1. `linhas_do_pdf`  — texto por linha (simples; funciona na maioria).
2. `palavras_do_pdf` / `linhas_por_coordenada` — reconstrói linhas e colunas a
   partir das coordenadas de cada palavra (x0, x1, top). Resolve layouts em que
   `extract_text` "achata" colunas ou embaralha a ordem.
3. `tabelas_do_pdf` — usa o detector de tabelas do pdfplumber.

Também concentra utilidades comuns: `texto_do_pdf` e `ano_do_texto`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import pdfplumber


# ---------------------------------------------------------------------------
# Estratégia 1 — por linhas de texto
# ---------------------------------------------------------------------------
def _texto_vazio(linhas: list[str]) -> bool:
    return len("".join(linhas).strip()) < 20


def _eh_texto_ocr(caminho: str) -> bool:
    """Arquivo .txt com linhas já reconhecidas por OCR no NAVEGADOR do usuário
    (caminho usado onde o OCR do servidor não existe, ex.: Vercel)."""
    return caminho.lower().endswith(".txt")


def _linhas_txt(caminho: str) -> list[str]:
    with open(caminho, encoding="utf-8", errors="replace") as fh:
        return [l.rstrip("\r\n") for l in fh]


def linhas_do_pdf(caminho: str, x_tolerance: int = 1) -> list[str]:
    """Todas as linhas de texto do PDF, na ordem de leitura.

    Se o PDF não tem camada de texto (escaneado), cai automaticamente no OCR.
    Um .txt (OCR feito no navegador) é lido diretamente como linhas.
    """
    if _eh_texto_ocr(caminho):
        return _linhas_txt(caminho)
    linhas: list[str] = []
    with pdfplumber.open(caminho) as pdf:
        for page in pdf.pages:
            texto = page.extract_text(x_tolerance=x_tolerance) or ""
            linhas.extend(texto.split("\n"))
    if _texto_vazio(linhas):
        from .ocr import linhas_ocr
        return linhas_ocr(caminho)
    return linhas


def texto_do_pdf(caminho: str, paginas: Optional[int] = None) -> str:
    """Texto concatenado do PDF (usado pelo detector de banco/tipo).

    Cai no OCR quando o PDF é escaneado (sem texto selecionável). Um .txt
    (OCR feito no navegador) é lido diretamente."""
    if _eh_texto_ocr(caminho):
        return "\n".join(_linhas_txt(caminho))
    partes: list[str] = []
    with pdfplumber.open(caminho) as pdf:
        pages = pdf.pages if paginas is None else pdf.pages[:paginas]
        for page in pages:
            partes.append(page.extract_text() or "")
    if _texto_vazio(partes):
        from .ocr import linhas_ocr
        linhas = linhas_ocr(caminho)
        if paginas is not None:
            # aproxima o corte por páginas limitando o volume de linhas
            return "\n".join(linhas)
        return "\n".join(linhas)
    return "\n".join(partes)


# ---------------------------------------------------------------------------
# Estratégia 2 — por coordenadas de palavra/coluna
# ---------------------------------------------------------------------------
@dataclass
class Palavra:
    texto: str
    x0: float
    x1: float
    top: float
    pagina: int


def palavras_do_pdf(caminho: str) -> list[Palavra]:
    """Todas as palavras com posição (x0, x1, top) e página."""
    palavras: list[Palavra] = []
    with pdfplumber.open(caminho) as pdf:
        for i, page in enumerate(pdf.pages):
            for w in page.extract_words(use_text_flow=False, keep_blank_chars=False):
                palavras.append(
                    Palavra(w["text"], w["x0"], w["x1"], w["top"], i)
                )
    return palavras


def linhas_por_coordenada(
    palavras: list[Palavra], tol_y: float = 2.5
) -> list[list[Palavra]]:
    """Agrupa palavras em linhas visuais pela coordenada vertical (top).

    Palavras cujo `top` difere menos que `tol_y` pontos ficam na mesma linha.
    Cada linha vem ordenada da esquerda para a direita.
    """
    linhas: list[list[Palavra]] = []
    for w in sorted(palavras, key=lambda p: (p.pagina, round(p.top, 1), p.x0)):
        if linhas and linhas[-1] and \
                linhas[-1][0].pagina == w.pagina and \
                abs(linhas[-1][-1].top - w.top) <= tol_y:
            linhas[-1].append(w)
        else:
            linhas.append([w])
    for linha in linhas:
        linha.sort(key=lambda p: p.x0)
    return linhas


def texto_em_faixa(linha: list[Palavra], x_ini: float, x_fim: float) -> str:
    """Concatena as palavras da linha cujo centro cai na faixa [x_ini, x_fim).

    Útil para extrair uma coluna específica quando se conhece as fronteiras x.
    """
    partes = [
        w.texto for w in linha
        if x_ini <= (w.x0 + w.x1) / 2 < x_fim
    ]
    return " ".join(partes)


# ---------------------------------------------------------------------------
# Estratégia 3 — tabelas
# ---------------------------------------------------------------------------
def tabelas_do_pdf(caminho: str) -> list[list[list[Optional[str]]]]:
    """Tabelas detectadas pelo pdfplumber (uma matriz por tabela)."""
    tabelas: list[list[list[Optional[str]]]] = []
    with pdfplumber.open(caminho) as pdf:
        for page in pdf.pages:
            for t in page.extract_tables():
                tabelas.append(t)
    return tabelas


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def ano_do_texto(linhas: list[str]) -> Optional[int]:
    """Primeiro ano de 4 dígitos encontrado (fallback simples)."""
    for l in linhas:
        m = re.search(r"\b(20\d{2})\b", l)
        if m:
            return int(m.group(1))
    return None
