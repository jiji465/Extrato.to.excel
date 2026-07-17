"""Parser do Caixa Econômica Federal — "Extrato por período".

O PDF da Caixa costuma ser ESCANEADO (imagem); o pipeline cai no OCR
automaticamente (ver extrato/ocr.py) e este parser trabalha sobre as linhas
reconhecidas:

    SALDO ANTERIOR R$ 507,82 C
    Lancamentos Nr. Doc Historico/Complemento Favorecido CPF/CNPJ Valor Saldo
    02/02/2026-00:00:00 000000 SALDO DIA 0,00 C 2.271,21 C          <- marcador
    02/02/2026-10:59:24 021059 PIX RECEBIDO Credi Shop ... 136,45 C 2.271,21 C
    05/01/2026-05:30:48 202512 MENSALIDADE CESTA SERVICO 75,00 D 530,87 C

Regras:
- Valor e saldo vêm com sufixo de natureza: 'C' = crédito (+), 'D' = débito (-).
- Os dois últimos tokens "NNN,NN C|D" da linha são valor e saldo.
- Lançamentos vêm em ordem cronológica INVERSA; ordenamos por data/hora.
- "SALDO ANTERIOR" = abertura; linhas "SALDO DIA" são marcadores (ignoradas).
- Tolerância a OCR: se a vírgula de UM dos dois números da linha se perdeu
  (ex.: "12247 C 1.404,66 C"), o extrato tem redundância — cada linha traz o
  saldo após o lançamento. O número legível é classificado pela posição (saldo
  fica no fim da linha) e o valor faltante é DERIVADO da diferença de saldos.
  A auditoria global (saldo inicial + Σ = saldo final) segue validando tudo.
"""

from __future__ import annotations

import re
from datetime import datetime

from ...normalizar import CONTA_CORRENTE, Extrato, Transacao, parse_data
from ..base import linhas_do_pdf

BANCO = "Caixa Econômica Federal"

# token monetário com natureza C/D (ex.: "1.234,56 C", "75,00 D")
_VAL_CD = re.compile(r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*([CD])\b")
# data-hora no início (OCR às vezes insere espaços em volta do '-')
_DT = re.compile(r"^(\d{2}/\d{2}/\d{4})\s*-?\s*(\d{2}):(\d{2}):(\d{2})")
_CPF_MASK = re.compile(r"\*+\.?[\d./*]+\*+")


# reinsere espaços perdidos pelo OCR em termos conhecidos da Caixa
_OCR_ESPACO = [
    (re.compile(r"PIX\s*RECEBIDO", re.I), "PIX RECEBIDO"),
    (re.compile(r"PIX\s*ENVIADO", re.I), "PIX ENVIADO"),
    (re.compile(r"MENSALIDADE\s*CESTA\s*SERVICO", re.I), "MENSALIDADE CESTA SERVICO"),
    (re.compile(r"SALDO\s*DIA", re.I), "SALDO DIA"),
    (re.compile(r"COMPRA\s*C\s*ARTAO|COMPRA\s*CARTAO", re.I), "COMPRA CARTAO"),
    (re.compile(r"SAQUE", re.I), "SAQUE"),
    (re.compile(r"TARIFA", re.I), "TARIFA"),
]
# histórico (tipo) conhecido, para separar do favorecido
_HIST = re.compile(
    r"^(PIX RECEBIDO|PIX ENVIADO|MENSALIDADE CESTA SERVICO|COMPRA CARTAO|"
    r"SAQUE|TARIFA[\w ]*|TED|DOC|DEPOSITO)",
    re.I,
)


def _num(txt: str, nat: str) -> float:
    v = float(txt.replace(".", "").replace(",", "."))
    return -v if nat.upper() == "D" else v


def _normaliza_ocr(texto: str) -> str:
    for rgx, sub in _OCR_ESPACO:
        texto = rgx.sub(sub, texto)
    return re.sub(r"\s+", " ", texto).strip(" -\t")


def parse(caminho: str) -> Extrato:
    linhas = linhas_do_pdf(caminho)   # cai no OCR se escaneado
    extrato = Extrato(banco=BANCO, tipo_documento=CONTA_CORRENTE)

    registros: list[tuple[datetime, Transacao]] = []

    for linha in linhas:
        ls = linha.strip()
        up = ls.upper()

        if "SALDO ANTERIOR" in up:
            m = _VAL_CD.search(ls)
            if m:
                extrato.saldo_inicial = _num(m.group(1), m.group(2))
            continue
        if "SALDO DIA" in up:
            continue

        dt = _DT.match(ls)
        if not dt:
            continue
        vals = _VAL_CD.findall(ls)
        if not vals:
            continue

        if len(vals) >= 2:
            valor = _num(*vals[-2])
            saldo = _num(*vals[-1])
        else:
            # Só um número legível: o OCR perdeu a vírgula do outro. O saldo é
            # o ÚLTIMO token da linha; se o número achado termina perto do fim,
            # ele é o saldo (valor será derivado depois); senão é o valor.
            m_unico = list(_VAL_CD.finditer(ls))[-1]
            if len(ls) - m_unico.end() <= 3:
                valor, saldo = None, _num(*vals[-1])
            else:
                valor, saldo = _num(*vals[-1]), None
        quando = datetime(int(dt.group(1)[6:10]), int(dt.group(1)[3:5]),
                          int(dt.group(1)[0:2]), int(dt.group(2)),
                          int(dt.group(3)), int(dt.group(4)))

        # entre a data e o 1º valor: nº documento + histórico + favorecido + CPF
        pos_val = _VAL_CD.search(ls).start()
        meio = ls[dt.end():pos_val]
        doc_m = re.match(r"\s*(\d{4,})", meio)         # nº do documento
        documento = doc_m.group(1) if doc_m else ""
        meio = re.sub(r"^\s*\d{4,}\s*", "", meio)
        meio = _CPF_MASK.sub("", meio)                 # remove CPF/CNPJ mascarado
        # resto de número quebrado pelo OCR no fim (ex.: "12247 C") não é nome
        meio = re.sub(r"[\d.,]+\s*[CD]?\s*$", "", meio)
        meio = _normaliza_ocr(meio)                    # reinsere espaços do OCR

        hm = _HIST.match(meio)
        if hm:
            descricao = hm.group(1).upper()
            favorecido = meio[hm.end():].strip(" -\t")
        else:
            descricao, favorecido = meio, ""

        registros.append((quando, Transacao(
            data=parse_data(dt.group(1)),
            descricao=descricao,
            favorecido=favorecido,
            documento=documento,
            hora=f"{dt.group(2)}:{dt.group(3)}:{dt.group(4)}",
            valor=valor,
            saldo=saldo,
            banco=BANCO,
        )))

    # ordena cronologicamente (o extrato vem em ordem inversa)
    registros.sort(key=lambda r: r[0])
    transacoes = [t for _, t in registros]

    # Deriva valores que o OCR perdeu (vírgula sumida) pela cadeia de saldos:
    # valor = saldo desta linha − saldo anterior. Linhas sem como derivar são
    # descartadas — a auditoria acusará o buraco na cadeia (nunca silencioso).
    saldo_ant = extrato.saldo_inicial
    completas: list[Transacao] = []
    for t in transacoes:
        if t.valor is None:
            if t.saldo is not None and saldo_ant is not None:
                t.valor = round(t.saldo - saldo_ant, 2)
            else:
                continue
        completas.append(t)
        if t.saldo is not None:
            saldo_ant = t.saldo
        elif saldo_ant is not None:
            saldo_ant = round(saldo_ant + t.valor, 2)

    extrato.transacoes = completas
    if completas:
        # saldo do último lançamento; se ilegível no OCR, usa o acumulado
        extrato.saldo_final = completas[-1].saldo if completas[-1].saldo is not None else saldo_ant
    return extrato
