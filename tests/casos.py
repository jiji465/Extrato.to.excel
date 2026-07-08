"""Manifesto de casos de teste (fixtures).

Cada caso descreve o que se espera de um PDF real ao passar pelo pipeline.
A reconciliação (auditoria) é o principal oráculo: se `auditoria_ok` é True, o
teste exige que os saldos/totais batam — isso pega regressão quando novos
parsers forem adicionados.

Privacidade: os PDFs NÃO ficam no repositório (são dados sensíveis; a pasta
tests/fixtures/ é ignorada pelo git). Para rodar os testes de reconciliação,
copie os PDFs para tests/fixtures/ com os nomes abaixo. Casos cujo arquivo não
existe na máquina são automaticamente pulados (skip).
"""

from __future__ import annotations

import os

_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _fx(nome: str) -> str:
    return os.path.join(_FIXTURES, nome)


CASOS: list[dict] = [
    {
        "id": "santander_janeiro",
        "arquivo": _fx("santander_janeiro.pdf"),
        "banco": "Santander",
        "tipo": "conta_corrente",
        "min_transacoes": 40,
        "auditoria_ok": True,
    },
    {
        "id": "santander_abril",
        "arquivo": _fx("santander_abril.pdf"),
        "banco": "Santander",
        "tipo": "conta_corrente",
        "min_transacoes": 40,
        "auditoria_ok": True,
    },
    {
        "id": "bradesco",
        "arquivo": _fx("bradesco.pdf"),
        "banco": "Bradesco",
        "tipo": "conta_corrente",
        "min_transacoes": 2,
        "auditoria_ok": True,
    },
    {
        "id": "banco_do_brasil",
        "arquivo": _fx("banco_do_brasil.pdf"),
        "banco": "Banco do Brasil",
        "tipo": "conta_corrente",
        "min_transacoes": 300,
        "auditoria_ok": True,
    },
    {
        "id": "nubank",
        "arquivo": _fx("nubank.pdf"),
        "banco": "Nubank",
        "tipo": "conta_corrente",
        "min_transacoes": 250,
        "auditoria_ok": True,
    },
    {
        # PDF escaneado — exercita o caminho de OCR (RapidOCR) ponta a ponta.
        "id": "caixa_ocr",
        "arquivo": _fx("caixa.pdf"),
        "banco": "Caixa Econômica Federal",
        "tipo": "conta_corrente",
        "min_transacoes": 10,
        "auditoria_ok": True,
    },
]
