"""Orquestração: de arquivos PDF até os bytes do Excel, com auditoria."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .auditoria import Auditoria, auditar
from .categorizador import categorizar
from .detector import detectar
from .excel import gerar_excel
from .normalizar import Extrato, Transacao, pos_processar
from .parsers import obter_parser
from .parsers.base import texto_do_pdf

# Rótulos amigáveis dos tipos de documento (para o relatório/UI).
_TIPO_LABEL = {
    "conta_corrente": "Conta corrente",
    "fatura": "Fatura de cartão",
    "investimento": "Investimento",
}


@dataclass
class ResultadoArquivo:
    nome: str
    banco: str
    tipo_documento: str
    n_transacoes: int
    auditoria: Auditoria = field(default_factory=Auditoria)
    categorias: dict[str, int] = field(default_factory=dict)
    erro: str = ""

    @property
    def tipo_label(self) -> str:
        return _TIPO_LABEL.get(self.tipo_documento, self.tipo_documento)


def processar_pdf(caminho: str, nome_exibicao_arquivo: str) -> tuple[Extrato, ResultadoArquivo]:
    """Processa um único PDF. Nunca levanta exceção: erros vão no resultado."""
    try:
        texto = texto_do_pdf(caminho, paginas=3)
        chave, nome_banco, tipo = detectar(texto)
        parser = obter_parser(chave, nome_banco, tipo)
        extrato = parser(caminho)
        extrato.transacoes = pos_processar(extrato.transacoes)
        categorizar(extrato.transacoes)
        aud = auditar(extrato)
        cats = dict(Counter(t.categoria for t in extrato.transacoes if t.categoria))
        return extrato, ResultadoArquivo(
            nome=nome_exibicao_arquivo,
            banco=nome_banco,
            tipo_documento=extrato.tipo_documento,
            n_transacoes=len(extrato.transacoes),
            auditoria=aud,
            categorias=cats,
        )
    except Exception as exc:  # noqa: BLE001 - reportamos ao usuário
        from .ocr import OCRIndisponivel
        msg = str(exc) if isinstance(exc, OCRIndisponivel) else f"{type(exc).__name__}: {exc}"
        return Extrato(banco="—"), ResultadoArquivo(
            nome=nome_exibicao_arquivo,
            banco="—",
            tipo_documento="—",
            n_transacoes=0,
            erro=msg,
        )


def converter(arquivos: list[tuple[str, str]]) -> tuple[bytes, list[ResultadoArquivo]]:
    """Converte vários PDFs num único Excel.

    arquivos: lista de (caminho_no_disco, nome_original).
    Retorna (bytes_xlsx, relatorio_por_arquivo). A auditoria de cada arquivo
    (reconciliação de saldos) fica no relatório — é a checagem feita ANTES de
    montar a planilha.
    """
    todas: list[Transacao] = []
    relatorio: list[ResultadoArquivo] = []
    for caminho, nome in arquivos:
        extrato, res = processar_pdf(caminho, nome)
        todas.extend(extrato.transacoes)
        relatorio.append(res)
    return gerar_excel(todas, relatorio), relatorio
