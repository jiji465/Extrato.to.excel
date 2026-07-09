"""Servidor web do conversor de extratos.

Uso local: `python app.py` (abre em http://127.0.0.1:5000).
Uso em produção (internet): rodar via gunicorn (ver Procfile) atrás de HTTPS.

Segurança: o acesso exige LOGIN (senha compartilhada da equipe). Configure por
variáveis de ambiente:
  EXTRATO_SENHA   -> senha de acesso da equipe (OBRIGATÓRia em produção)
  EXTRATO_SECRET  -> chave secreta das sessões (defina um valor aleatório fixo)

Os PDFs enviados são processados em memória/arquivo temporário e APAGADOS logo
em seguida — nada é armazenado no servidor.
"""

from __future__ import annotations

import base64
import hmac
import os
import tempfile
from functools import wraps

from flask import (
    Flask, jsonify, redirect, render_template, request, session, url_for
)

from extrato.conversor import converter

# Caminho absoluto dos templates — robusto em serverless (Vercel) e local.
_BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(_BASE, "templates"))
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB por requisição

# Chave de sessão: defina EXTRATO_SECRET em produção (fixa entre reinícios/workers).
app.secret_key = os.environ.get("EXTRATO_SECRET") or os.urandom(32)

# Senha de acesso da equipe. Em produção, defina EXTRATO_SENHA.
_SENHA = os.environ.get("EXTRATO_SENHA", "")


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
    return render_template("index.html", protegido=bool(_SENHA))


@app.route("/converter", methods=["POST"])
@login_required
def rota_converter():
    enviados = request.files.getlist("arquivos")
    if not enviados:
        return jsonify({"erro": "Nenhum arquivo enviado."}), 400

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

        xlsx_bytes, relatorio = converter(temporarios)
    finally:
        for caminho, _ in temporarios:
            try:
                os.remove(caminho)
            except OSError:
                pass

    # Retornamos o Excel (base64) + o relatório por arquivo, para exibir na tela.
    return jsonify({
        "arquivo_b64": base64.b64encode(xlsx_bytes).decode("ascii"),
        "nome": "extrato.xlsx",
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
