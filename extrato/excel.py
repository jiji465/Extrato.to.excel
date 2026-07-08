"""Geração do arquivo Excel a partir das transações normalizadas."""

from __future__ import annotations

from collections import defaultdict
from io import BytesIO
from typing import Iterable

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from .normalizar import Transacao

_MOEDA = 'R$ #,##0.00;[Red]-R$ #,##0.00'
_DATA_FMT = "DD/MM/YYYY"

_HEADER_FILL = PatternFill("solid", fgColor="4F46E5")
_HEADER_FONT = Font(bold=True, color="FFFFFF")
_THIN = Side(style="thin", color="D9D9D9")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

_COLUNAS = ["Data", "Descrição", "Valor", "Tipo", "Categoria", "Saldo",
            "Documento", "Banco"]


def _escrever_cabecalho(ws, colunas: list[str]) -> None:
    for c, titulo in enumerate(colunas, start=1):
        cel = ws.cell(row=1, column=c, value=titulo)
        cel.fill = _HEADER_FILL
        cel.font = _HEADER_FONT
        cel.alignment = Alignment(horizontal="center")
        cel.border = _BORDER


def _aba_transacoes(wb: Workbook, transacoes: list[Transacao]) -> None:
    ws = wb.active
    ws.title = "Transações"
    _escrever_cabecalho(ws, _COLUNAS)

    for t in transacoes:
        ws.append([
            t.data,
            t.descricao,
            t.valor,
            t.tipo,
            t.categoria,
            t.saldo,
            t.documento,
            t.banco,
        ])

    ultima = ws.max_row
    for row in ws.iter_rows(min_row=2, max_row=ultima):
        row[0].number_format = _DATA_FMT           # Data
        row[2].number_format = _MOEDA              # Valor
        if row[5].value is not None:
            row[5].number_format = _MOEDA          # Saldo
        for cel in row:
            cel.border = _BORDER

    larguras = [12, 46, 15, 10, 22, 15, 16, 20]
    for i, w in enumerate(larguras, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws.freeze_panes = "A2"
    if ultima >= 1:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(_COLUNAS))}{ultima}"


def _aba_resumo(wb: Workbook, transacoes: list[Transacao]) -> None:
    ws = wb.create_sheet("Resumo")
    _escrever_cabecalho(ws, ["Banco", "Entradas", "Saídas", "Saldo do período", "Nº transações"])

    por_banco: dict[str, list[Transacao]] = defaultdict(list)
    for t in transacoes:
        por_banco[t.banco].append(t)

    for banco, itens in sorted(por_banco.items()):
        entradas = sum(t.valor for t in itens if t.valor > 0)
        saidas = sum(t.valor for t in itens if t.valor < 0)
        ws.append([banco, entradas, saidas, entradas + saidas, len(itens)])

    for row in ws.iter_rows(min_row=2):
        for i in (1, 2, 3):
            row[i].number_format = _MOEDA
        for cel in row:
            cel.border = _BORDER

    for i, w in enumerate([22, 16, 16, 18, 14], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"


def _aba_categorias(wb: Workbook, transacoes: list[Transacao]) -> None:
    """Quebra por categoria — visão contábil (entradas, saídas, total, nº)."""
    ws = wb.create_sheet("Categorias")
    _escrever_cabecalho(ws, ["Categoria", "Entradas", "Saídas", "Total", "Nº transações"])

    por_cat: dict[str, list[Transacao]] = defaultdict(list)
    for t in transacoes:
        por_cat[t.categoria or "Não classificado"].append(t)

    # ordena por maior movimento absoluto (categorias mais relevantes no topo)
    def _peso(itens):
        return sum(abs(t.valor) for t in itens)

    for categoria, itens in sorted(por_cat.items(), key=lambda kv: -_peso(kv[1])):
        entradas = sum(t.valor for t in itens if t.valor > 0)
        saidas = sum(t.valor for t in itens if t.valor < 0)
        ws.append([categoria, entradas, saidas, entradas + saidas, len(itens)])

    for row in ws.iter_rows(min_row=2):
        for i in (1, 2, 3):
            row[i].number_format = _MOEDA
        for cel in row:
            cel.border = _BORDER

    for i, w in enumerate([26, 16, 16, 16, 14], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"


def _aba_auditoria(wb: Workbook, relatorio: list) -> None:
    """Registra no próprio arquivo a conferência de saldos feita antes de gerar."""
    ws = wb.create_sheet("Auditoria")
    _escrever_cabecalho(ws, ["Arquivo", "Banco", "Tipo", "Transações",
                             "Conferência", "Detalhes"])

    for r in relatorio:
        aud = getattr(r, "auditoria", None)
        tipo = getattr(r, "tipo_label", "—")
        if r.erro:
            status, detalhes = "ERRO", r.erro
        elif aud is not None:
            status = aud.resumo
            detalhes = " | ".join(aud.mensagens)
        else:
            status, detalhes = "—", ""
        linha = ws.max_row + 1
        ws.append([r.nome, r.banco, tipo, r.n_transacoes, status, detalhes])
        # cor do status
        cel = ws.cell(row=linha, column=5)
        if aud is not None and aud.conferido and aud.ok and not r.erro:
            cel.font = Font(bold=True, color="16A34A")   # verde
        elif r.erro or (aud is not None and aud.conferido and not aud.ok):
            cel.font = Font(bold=True, color="DC2626")   # vermelho
        else:
            cel.font = Font(bold=True, color="B45309")   # amarelo

    for row in ws.iter_rows(min_row=2):
        for cel in row:
            cel.border = _BORDER
            cel.alignment = Alignment(vertical="top", wrap_text=(cel.column == 6))
    for i, w in enumerate([32, 18, 16, 12, 22, 66], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"


def gerar_excel(transacoes: Iterable[Transacao], relatorio: list | None = None) -> bytes:
    """Monta o workbook e devolve os bytes do .xlsx.

    relatorio: resultados por arquivo (inclui a auditoria). Quando fornecido,
    gera a aba 'Auditoria' com o resultado da conferência de saldos.
    """
    transacoes = list(transacoes)
    wb = Workbook()
    _aba_transacoes(wb, transacoes)
    _aba_resumo(wb, transacoes)
    _aba_categorias(wb, transacoes)
    if relatorio:
        _aba_auditoria(wb, relatorio)

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
