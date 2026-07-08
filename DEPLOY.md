# Como publicar (GitHub → Vercel ou Render)

> ⚠️ **Dados sensíveis (LGPD).** Este app processa extratos bancários. Ele **não
> armazena** os PDFs (processa e apaga na hora), mas, se publicar na internet:
> - Prefira proteger com **senha** (variável `EXTRATO_SENHA`).
> - Nunca versione PDFs de clientes (o `.gitignore` já bloqueia `*.pdf`).
> - Ciente do risco, dá para deixar público (sem senha) — é sua decisão.

## Resumo da escolha

| Plataforma | PDFs digitais | PDF escaneado (OCR) | Dificuldade |
|-----------|:---:|:---:|---|
| **Vercel** | ✅ | ❌ (limite de tamanho/tempo) | Fácil |
| **Render** | ✅ | ✅ | Fácil |

Se você precisa ler **PDF escaneado (Caixa)** online, use **Render**. Se só usa
os bancos digitais online (e escaneado só no app local), o **Vercel** serve.

---

## 1) Subir para o GitHub (uma vez)

Já deixei o repositório local pronto (commit feito). Falta autenticar e enviar:

```bash
gh auth login          # escolha GitHub.com > HTTPS > login pelo navegador
git push -u origin main
```

Repositório: https://github.com/jiji465/Extrato.to.excel

> Se pedir usuário/senha em vez do navegador, gere um token em
> github.com → Settings → Developer settings → Personal access tokens e use-o
> como senha.

---

## 2A) Publicar no Vercel (versão digital)

1. Acesse **vercel.com** e faça login com o GitHub.
2. **Add New… → Project** e selecione o repositório `Extrato.to.excel`.
3. O Vercel detecta Python automaticamente (arquivos `vercel.json` e
   `api/index.py` já estão prontos). Clique **Deploy**.
4. Em ~1 min você recebe uma URL pública `https://....vercel.app`.

**Opcional — proteger com senha:** Project → **Settings → Environment
Variables** → adicione:
- `EXTRATO_SENHA` = a senha da equipe
- `EXTRATO_SECRET` = qualquer texto aleatório longo (mantém o login estável)

Depois, **Redeploy**. Sem `EXTRATO_SENHA`, o site fica **público**.

> No Vercel, PDFs escaneados mostram um aviso de "OCR indisponível online".

---

## 2B) Publicar no Render (versão completa, com OCR)

1. Acesse **render.com** e faça login com o GitHub.
2. **New → Blueprint** e selecione o repositório. O Render lê o `render.yaml`
   e configura tudo (build com OCR + gunicorn).
3. Clique **Apply**. Em alguns minutos sai a URL `https://....onrender.com`.
4. `EXTRATO_SECRET` é gerado sozinho. Para exigir senha, defina `EXTRATO_SENHA`
   no painel (Environment) e salve.

> O plano grátis do Render “dorme” após inatividade (a 1ª visita demora uns
> segundos) e tem 512 MB de RAM. Se o OCR faltar memória, suba para o plano
> **Starter**.

---

## Alternativa mais segura: rede privada (Tailscale)

Se preferir “acessar de qualquer lugar” **sem expor à internet pública**:
1. Instale o **Tailscale** (tailscale.com) no PC que roda o app e no de cada
   colega (todos entram na mesma conta/rede).
2. Rode o app nesse PC com `python app.py` (ou `waitress`/`gunicorn`).
3. Os colegas acessam pelo IP Tailscale desse PC (ex.: `http://100.x.y.z:5000`).

Assim o tráfego é criptografado e só quem está na sua rede privada acessa —
melhor para dados financeiros.

---

## Atualizar depois de mudar o código

```bash
git add -A
git commit -m "descrição da mudança"
git push
```

Vercel e Render **reimplantam sozinhos** a cada push.
