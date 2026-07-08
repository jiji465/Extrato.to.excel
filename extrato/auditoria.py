"""Auditoria de reconciliação: confere se os números batem ANTES de gerar o
Excel. A estratégia depende do tipo de documento:

- conta corrente: saldo inicial + Σ lançamentos = saldo final; totais de
  crédito/débito do resumo; e cada saldo parcial impresso linha a linha.
- fatura:         saldo anterior + Σ lançamentos = total da fatura.
- investimento:   saldo anterior + rendimento = saldo atual.

Usa os metadados que o parser leu no próprio extrato.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .normalizar import CONTA_CORRENTE, FATURA, INVESTIMENTO, Extrato


_TOL = 0.01  # tolerância de 1 centavo para arredondamento


@dataclass
class Auditoria:
    conferido: bool = False          # havia dados suficientes para conferir?
    ok: bool = True                  # todas as conferências disponíveis passaram?
    mensagens: list[str] = field(default_factory=list)
    divergencias_saldo: int = 0      # nº de saldos parciais que não bateram

    @property
    def resumo(self) -> str:
        if not self.conferido:
            return "sem dados p/ conferir"
        return "OK — saldos batem" if self.ok else "DIVERGÊNCIA"


def auditar(extrato: Extrato) -> Auditoria:
    """Despacha para a estratégia do tipo de documento."""
    if extrato.tipo_documento == FATURA:
        return _auditar_fatura(extrato)
    if extrato.tipo_documento == INVESTIMENTO:
        return _auditar_investimento(extrato)
    return _auditar_conta_corrente(extrato)


# ---------------------------------------------------------------------------
# Conta corrente
# ---------------------------------------------------------------------------
def _auditar_conta_corrente(extrato: Extrato) -> Auditoria:
    a = Auditoria()
    trans = extrato.transacoes
    if not trans:
        a.mensagens.append("Nenhuma transação extraída.")
        return a

    soma = round(sum(t.valor for t in trans), 2)
    creditos = round(sum(t.valor for t in trans if t.valor > 0), 2)
    debitos = round(sum(-t.valor for t in trans if t.valor < 0), 2)

    # 1) Saldo inicial + movimento = saldo final
    if extrato.saldo_inicial is not None and extrato.saldo_final is not None:
        a.conferido = True
        calc = round(extrato.saldo_inicial + soma, 2)
        if abs(calc - extrato.saldo_final) <= _TOL:
            a.mensagens.append(
                f"Saldo final confere: {extrato.saldo_inicial:.2f} + "
                f"{soma:.2f} = {calc:.2f}"
            )
        else:
            a.ok = False
            a.mensagens.append(
                f"Saldo final NÃO bate: calculado {calc:.2f} vs "
                f"impresso {extrato.saldo_final:.2f} "
                f"(diferença {calc - extrato.saldo_final:+.2f})"
            )

    # 2) Totais de crédito/débito informados no resumo do extrato
    if extrato.total_creditos is not None:
        a.conferido = True
        if abs(creditos - extrato.total_creditos) <= _TOL:
            a.mensagens.append(f"Total de créditos confere: {creditos:.2f}")
        else:
            a.ok = False
            a.mensagens.append(
                f"Total de créditos NÃO bate: somado {creditos:.2f} vs "
                f"resumo {extrato.total_creditos:.2f}"
            )
    if extrato.total_debitos is not None:
        a.conferido = True
        if abs(debitos - extrato.total_debitos) <= _TOL:
            a.mensagens.append(f"Total de débitos confere: {debitos:.2f}")
        else:
            a.ok = False
            a.mensagens.append(
                f"Total de débitos NÃO bate: somado {debitos:.2f} vs "
                f"resumo {extrato.total_debitos:.2f}"
            )

    # 3) Saldos parciais impressos linha a linha (a checagem mais sensível)
    if extrato.saldo_inicial is not None:
        run = extrato.saldo_inicial
        divergencias = 0
        for t in trans:
            run = round(run + t.valor, 2)
            if t.saldo is not None and abs(run - t.saldo) > _TOL:
                divergencias += 1
        if divergencias:
            a.conferido = True
            a.ok = False
            a.divergencias_saldo = divergencias
            a.mensagens.append(
                f"{divergencias} saldo(s) parcial(is) divergente(s) — "
                f"provável linha extraída errada."
            )
        elif any(t.saldo is not None for t in trans):
            a.conferido = True
            a.mensagens.append("Saldos parciais conferem em todas as linhas.")

    if not a.conferido:
        a.mensagens.append(
            "Extrato sem saldo/totais de referência — não foi possível "
            "auditar automaticamente."
        )
    return a


# ---------------------------------------------------------------------------
# Fatura de cartão (convenção: compra = valor positivo; pagamento/estorno = negativo)
# ---------------------------------------------------------------------------
def _auditar_fatura(extrato: Extrato) -> Auditoria:
    a = Auditoria()
    trans = extrato.transacoes
    if not trans:
        a.mensagens.append("Nenhum lançamento extraído.")
        return a

    soma = round(sum(t.valor for t in trans), 2)
    base = extrato.saldo_anterior or 0.0

    if extrato.total_fatura is not None:
        a.conferido = True
        calc = round(base + soma, 2)
        if abs(calc - extrato.total_fatura) <= _TOL:
            det = f"{base:.2f} + " if extrato.saldo_anterior is not None else ""
            a.mensagens.append(
                f"Total da fatura confere: {det}{soma:.2f} = {calc:.2f}"
            )
        else:
            a.ok = False
            a.mensagens.append(
                f"Total da fatura NÃO bate: calculado {calc:.2f} vs "
                f"impresso {extrato.total_fatura:.2f} "
                f"(diferença {calc - extrato.total_fatura:+.2f})"
            )
    else:
        a.mensagens.append(
            "Fatura sem 'total da fatura' de referência — não foi possível "
            "auditar automaticamente."
        )
    return a


# ---------------------------------------------------------------------------
# Investimento
# ---------------------------------------------------------------------------
def _auditar_investimento(extrato: Extrato) -> Auditoria:
    a = Auditoria()
    if (extrato.saldo_anterior is not None
            and extrato.saldo_atual is not None
            and extrato.rendimento is not None):
        a.conferido = True
        calc = round(extrato.saldo_anterior + extrato.rendimento, 2)
        if abs(calc - extrato.saldo_atual) <= _TOL:
            a.mensagens.append(
                f"Saldo de investimento confere: {extrato.saldo_anterior:.2f} + "
                f"{extrato.rendimento:.2f} = {calc:.2f}"
            )
        else:
            a.ok = False
            a.mensagens.append(
                f"Saldo de investimento NÃO bate: calculado {calc:.2f} vs "
                f"impresso {extrato.saldo_atual:.2f}"
            )
    else:
        a.mensagens.append(
            "Investimento sem saldo anterior/atual/rendimento de referência — "
            "não foi possível auditar automaticamente."
        )
    return a
