"""OCR para PDFs escaneados (imagem), sem binário externo.

Renderiza cada página com o PyMuPDF (fitz) e reconhece o texto com o RapidOCR
(ONNX, pip puro). Reconstrói "linhas" agrupando as caixas de texto pela posição
vertical, para o resultado alimentar o mesmo pipeline dos PDFs digitais.

O OCR é caro; o resultado é cacheado por (caminho, mtime, dpi). As dependências
pesadas (fitz, rapidocr, PIL, numpy) são importadas sob demanda, para o import
deste módulo não falhar quando o OCR não é necessário.
"""

from __future__ import annotations

import io
import os

_cache: dict[tuple, list[str]] = {}


class OCRIndisponivel(RuntimeError):
    """OCR necessário mas as dependências não estão instaladas."""


def _reconstruir_linhas(result, tol: float = 25.0) -> list[str]:
    """Agrupa as caixas do RapidOCR em linhas (por y) e ordena por x."""
    if not result:
        return []
    itens = []
    for box, txt, _score in result:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        itens.append((min(ys), min(xs), txt))
    itens.sort(key=lambda t: (t[0], t[1]))

    linhas: list[str] = []
    atual: list[tuple[float, str]] = []
    y_ref = None
    for y, x, txt in itens:
        if y_ref is None or abs(y - y_ref) <= tol:
            atual.append((x, txt))
            y_ref = y if y_ref is None else y_ref
        else:
            linhas.append(" ".join(t for _, t in sorted(atual)))
            atual = [(x, txt)]
            y_ref = y
    if atual:
        linhas.append(" ".join(t for _, t in sorted(atual)))
    return linhas


def _ocr(caminho: str, dpi: int) -> list[str]:
    try:
        import fitz  # PyMuPDF
        import numpy as np
        from PIL import Image
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:  # pragma: no cover
        raise OCRIndisponivel(
            "PDF escaneado: leitura por OCR não está disponível nesta versão "
            "(online). Use o aplicativo local para PDFs escaneados, ou implante "
            "no Render (que suporta OCR)."
        ) from exc

    engine = RapidOCR()
    linhas: list[str] = []
    doc = fitz.open(caminho)
    try:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            result, _ = engine(np.array(img))
            linhas.extend(_reconstruir_linhas(result))
    finally:
        doc.close()
    return linhas


def linhas_ocr(caminho: str, dpi: int = 300) -> list[str]:
    """Linhas de texto reconhecidas por OCR.

    Usa um cache curto (por arquivo+mtime+dpi) só para evitar rodar o OCR duas
    vezes na MESMA requisição (detecção + parsing). O servidor limpa o cache ao
    fim de cada requisição (`limpar_cache`), então o texto não persiste na RAM.
    """
    try:
        mtime = os.path.getmtime(caminho)
    except OSError:
        mtime = 0
    chave = (os.path.abspath(caminho), mtime, dpi)
    if chave not in _cache:
        _cache[chave] = _ocr(caminho, dpi)
    return _cache[chave]


def limpar_cache() -> None:
    """Descarta da memória todo o texto de OCR em cache (privacidade)."""
    _cache.clear()


def disponivel() -> bool:
    """True se as dependências de OCR estão instaladas."""
    try:
        import fitz  # noqa: F401
        import rapidocr_onnxruntime  # noqa: F401
        return True
    except ImportError:
        return False
