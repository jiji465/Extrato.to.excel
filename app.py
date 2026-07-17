"""Servidor web do conversor de extratos.

Uso local: `python app.py` (abre em http://127.0.0.1:5000).
Uso em produção (internet): rodar via gunicorn (ver Procfile) atrás de HTTPS.

Privacidade: os PDFs são processados em arquivo temporário e APAGADOS logo em
seguida; o Excel é montado em memória. Nada é armazenado nem registrado no
servidor. Após cada requisição, o cache de OCR também é limpo da memória.

Segurança:
- Login é OPCIONAL. Sem `EXTRATO_SENHA`, o acesso é público (sem senha).
  Com `EXTRATO_SENHA` definida (+ `EXTRATO_SECRET`), exige login da equipe.
- Cabeçalhos de segurança e `Cache-Control: no-store` em toda resposta.
- Rate limit por IP e limite de arquivos por requisição contra abuso.
"""

from __future__ import annotations

import base64
import hmac
import os
import tempfile
import time
from collections import deque
from functools import wraps

from flask import (
    Flask, jsonify, redirect, render_template, request, session, url_for
)

from extrato import ocr
from extrato.conversor import converter
from extrato.identificacao import sanitizar_arquivo

# Caminho absoluto dos templates — robusto em serverless (Vercel) e local.
_BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(_BASE, "templates"))
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB por requisição
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=True,   # cookie de sessão só por HTTPS
)

# Chave de sessão: defina EXTRATO_SECRET em produção (fixa entre reinícios/workers).
app.secret_key = os.environ.get("EXTRATO_SECRET") or os.urandom(32)

# Senha de acesso da equipe. Vazia => acesso público (sem login).
_SENHA = os.environ.get("EXTRATO_SENHA", "")

# Limites contra abuso.
MAX_ARQUIVOS = 30          # arquivos por requisição
RATE_LIMITE = 20           # requisições de conversão...
RATE_JANELA = 60           # ...por IP a cada 60 s
_req_por_ip: dict[str, deque] = {}


def _ip_cliente() -> str:
    xff = request.headers.get("X-Forwarded-For", "")
    return xff.split(",")[0].strip() if xff else (request.remote_addr or "?")


def _rate_ok(ip: str) -> bool:
    agora = time.time()
    dq = _req_por_ip.setdefault(ip, deque())
    while dq and dq[0] < agora - RATE_JANELA:
        dq.popleft()
    if len(dq) >= RATE_LIMITE:
        return False
    dq.append(agora)
    return True


def _nome_excel(relatorio) -> str:
    """Monta 'Extrato - <Empresa> - <Banco> - <Mês>.xlsx' a partir dos extratos.

    Quando há vários arquivos com valores diferentes, usa 'Vários' na parte que
    difere.
    """
    validos = [r for r in relatorio if not r.erro and r.n_transacoes]
    if not validos:
        return "extrato.xlsx"

    def unico(vals, plural):
        u = list(dict.fromkeys(v for v in vals if v))
        if len(u) == 1:
            return u[0]
        return plural if len(u) > 1 else ""

    partes = ["Extrato"]
    for p in (unico((r.titular for r in validos), "Vários titulares"),
              unico((r.banco for r in validos), "Vários bancos"),
              unico((r.periodo for r in validos), "Vários períodos")):
        if p:
            partes.append(p)
    return sanitizar_arquivo(" - ".join(partes)) + ".xlsx"


@app.after_request
def _cabecalhos_seguranca(resp):
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self'; object-src 'none'; base-uri 'none'; "
        "form-action 'self'; frame-ancestors 'none'"
    )
    return resp


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        # Sem senha configurada => acesso público (sem login).
        if _SENHA and not session.get("auth"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    erro = ""
    if request.method == "POST":
        senha = request.form.get("senha", "")
        if not _SENHA:
            erro = ("Senha de acesso não configurada no servidor "
                    "(defina EXTRATO_SENHA).")
        elif hmac.compare_digest(senha, _SENHA):
            session["auth"] = True
            destino = request.args.get("next") or url_for("index")
            return redirect(destino)
        else:
            erro = "Senha incorreta."
    return render_template("login.html", erro=erro)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    # `protegido` controla a exibição do link "Sair" (só quando há senha).
    # `ocr_disponivel` evita prometer OCR onde ele não roda (ex.: Vercel).
    return render_template(
        "index.html", protegido=bool(_SENHA), ocr_disponivel=ocr.disponivel()
    )


@app.route("/converter", methods=["POST"])
@login_required
def rota_converter():
    if not _rate_ok(_ip_cliente()):
        return jsonify({"erro": "Muitas conversões em pouco tempo. "
                                "Aguarde um minuto e tente novamente."}), 429

    enviados = request.files.getlist("arquivos")
    if not enviados:
        return jsonify({"erro": "Nenhum arquivo enviado."}), 400
    if len(enviados) > MAX_ARQUIVOS:
        return jsonify({"erro": f"Máximo de {MAX_ARQUIVOS} arquivos por vez."}), 400

    temporarios: list[tuple[str, str]] = []
    try:
        for f in enviados:
            if not f.filename.lower().endswith(".pdf"):
                continue
            fd, caminho = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
            f.save(caminho)
            temporarios.append((caminho, f.filename))

        if not temporarios:
            return jsonify({"erro": "Envie ao menos um arquivo PDF."}), 400

        xlsx_bytes, relatorio, transacoes = converter(temporarios)
    finally:
        for caminho, _ in temporarios:
            try:
                os.remove(caminho)
            except OSError:
                pass
        # apaga da memória qualquer texto de OCR desta requisição
        ocr.limpar_cache()

    # Retornamos o Excel (base64) + o relatório por arquivo + as transações
    # (para a pré-visualização na tela).
    return jsonify({
        "arquivo_b64": base64.b64encode(xlsx_bytes).decode("ascii"),
        "nome": _nome_excel(relatorio),
        "transacoes": [
            {
                "data": t.data.isoformat() if t.data else "",
                "hora": t.hora,
                "descricao": t.descricao,
                "favorecido": t.favorecido,
                "documento": t.documento,
                "valor": t.valor,
                "tipo": t.tipo,
                "categoria": t.categoria,
                "saldo": t.saldo,
                "banco": t.banco,
            }
            for t in transacoes
        ],
        "relatorio": [
            {
                "nome": r.nome,
                "banco": r.banco,
                "tipo": r.tipo_label,
                "transacoes": r.n_transacoes,
                "categorias": r.categorias,
                "erro": r.erro,
                "auditoria": {
                    "conferido": r.auditoria.conferido,
                    "ok": r.auditoria.ok,
                    "resumo": r.auditoria.resumo,
                    "mensagens": r.auditoria.mensagens,
                },
            }
            for r in relatorio
        ],
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
