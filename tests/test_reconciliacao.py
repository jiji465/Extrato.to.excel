"""Testes de reconciliação e unidade do conversor de extratos.

- test_caso_*: roda PDFs reais (manifesto em casos.py) pelo pipeline e afirma
  banco/tipo detectados, contagem mínima e auditoria fechando.
- test_fixtures_nao_quebram: qualquer PDF solto em tests/fixtures/ deve ser
  processado sem exceção.
- testes unitários de parsing de valor/data/categoria.
"""

from __future__ import annotations

import glob
import os

import pytest

from extrato.conversor import processar_pdf
from extrato.normalizar import parse_valor, parse_data, valores_brl
from extrato.categorizador import classificar
from tests.casos import CASOS, _FIXTURES


# ---------------------------------------------------------------------------
# Casos reais (reconciliação)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("caso", CASOS, ids=[c["id"] for c in CASOS])
def test_caso_reconciliacao(caso):
    if not os.path.exists(caso["arquivo"]):
        pytest.skip(f"PDF ausente: {caso['arquivo']}")

    extrato, res = processar_pdf(caso["arquivo"], os.path.basename(caso["arquivo"]))

    assert res.erro == "", f"erro no pipeline: {res.erro}"
    assert res.banco == caso["banco"], f"banco {res.banco} != {caso['banco']}"
    assert extrato.tipo_documento == caso["tipo"]
    assert res.n_transacoes >= caso["min_transacoes"], \
        f"apenas {res.n_transacoes} transações"

    if caso.get("auditoria_ok"):
        assert res.auditoria.conferido, "auditoria não teve dados para conferir"
        assert res.auditoria.ok, \
            "auditoria falhou: " + " | ".join(res.auditoria.mensagens)


# ---------------------------------------------------------------------------
# Qualquer fixture solta não pode quebrar o pipeline
# ---------------------------------------------------------------------------
_soltos = sorted(glob.glob(os.path.join(_FIXTURES, "*.pdf")))


@pytest.mark.skipif(not _soltos, reason="sem PDFs em tests/fixtures/")
@pytest.mark.parametrize("pdf", _soltos, ids=[os.path.basename(p) for p in _soltos])
def test_fixtures_nao_quebram(pdf):
    _, res = processar_pdf(pdf, os.path.basename(pdf))
    assert res.erro == "", f"pipeline quebrou em {pdf}: {res.erro}"


# ---------------------------------------------------------------------------
# Unidade: valores em reais (o bug que originou a auditoria)
# ---------------------------------------------------------------------------
def test_parse_valor_debito_sufixo():
    assert parse_valor("5,93-") == pytest.approx(-5.93)
    assert parse_valor("3.000,00-") == pytest.approx(-3000.00)
    assert parse_valor("1.234,56") == pytest.approx(1234.56)


def test_valores_brl_ignora_documento():
    # nº de documento (inteiro sem centavos) NÃO deve virar valor
    vals = valores_brl("PAGAMENTO CARTAO CREDITO BCE 090827 3.000,00-")
    assert len(vals) == 1
    valor, neg, _, _ = vals[0]
    assert valor == pytest.approx(3000.00) and neg is True


def test_valores_brl_movimento_e_saldo():
    vals = valores_brl("PIX ENVIADO - 5,93- 4.870,00")
    assert [round(v[0], 2) for v in vals] == [5.93, 4870.00]
    assert vals[0][1] is True and vals[1][1] is False  # débito, saldo


# ---------------------------------------------------------------------------
# Unidade: datas
# ---------------------------------------------------------------------------
def test_parse_data_formatos():
    assert parse_data("02/01/2026").isoformat() == "2026-01-02"
    assert parse_data("01 FEV 2024").isoformat() == "2024-02-01"
    assert parse_data("15/03", ano_padrao=2026).isoformat() == "2026-03-15"


# ---------------------------------------------------------------------------
# Unidade: categorização
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("descricao,esperado", [
    ("PIX ENVIADO Fulano", "Pix enviado"),
    ("PIX RECEBIDO Cliente", "Pix recebido"),
    ("PAGAMENTO IPVA-CANAIS", "Impostos e Tributos"),
    ("DEBITO AUT. FAT.CARTAO MASTER CARD", "Cartão de crédito"),
    ("LIQUIDO DE VENCIMENTO", "Folha e Salários"),
    ("REMUNERACAO APLICACAO AUTOMATICA", "Rendimentos e Aplicações"),
    ("CONTA DE AGUA E ESGOTO EM CANAIS", "Concessionárias"),
    ("MENSALIDADE DE SEGURO TOKIO MARINE", "Seguros"),
])
def test_categorizacao(descricao, esperado):
    assert classificar(descricao) == esperado
