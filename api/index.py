"""Ponto de entrada para o Vercel (Python serverless).

O Vercel serve o objeto WSGI `app`. Todas as rotas são reescritas para cá pelo
vercel.json. OCR não está disponível nesta versão (PDFs escaneados mostram aviso);
para OCR online, use o Render.
"""

import os
import sys

# garante que a raiz do projeto está no path para importar `app` e `extrato`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402,F401
