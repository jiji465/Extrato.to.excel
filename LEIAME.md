# Conversor de Extratos PDF → Excel

Transforma documentos bancários em PDF (extratos de conta corrente, faturas de
cartão e extratos de investimento) de vários bancos (Nubank, Itaú, Bradesco,
Santander, Banco do Brasil, Caixa, Sicoob, Inter, C6 e outros) numa planilha
Excel única, padronizada, **categorizada** e **auditada**.

Também roda online: **https://extrato-to-excel.vercel.app** (PDFs escaneados
são lidos por OCR **no próprio navegador** — nada de dados fica em servidor).

## Como usar (mais fácil)

1. Dê **duplo-clique em `iniciar.bat`**.
   - Na primeira vez ele instala o necessário automaticamente.
2. O navegador abre em `http://127.0.0.1:5000`.
3. **Arraste os PDFs** para a área indicada (pode misturar bancos, tipos e
   vários arquivos de uma vez).
4. Clique em **Converter para Excel** → baixa um arquivo com nome
   autoexplicativo, ex.: `Extrato - EMPRESA X - Sicoob - Junho-2026.xlsx`.

Para encerrar, feche a janela preta do programa.

## O que sai no Excel

- Aba **Transações**: Data, Hora, Descrição, Favorecido, Documento, Valor,
  Tipo (Crédito/Débito), **Categoria**, Saldo, Banco, Arquivo e a coluna
  **Confere** (fórmula viva que checa o saldo linha a linha).
- Aba **Conferência**: por arquivo, saldo inicial + entradas − saídas = saldo
  final, comparado com o impresso no extrato (verde/vermelho, recalcula ao editar).
- Aba **Resumo**: entradas, saídas e saldo do período por banco.
- Aba **Categorias**: quebra por categoria (entradas, saídas, total, nº) —
  visão contábil.
- Aba **Auditoria**: resultado da conferência de saldos de cada arquivo.

## Auditoria de saldos (conferência antes de gerar)

Antes de montar a planilha, a ferramenta **reconcilia os números** usando os
próprios dados do documento. A conferência depende do tipo:

- **Conta corrente:** saldo inicial + Σ lançamentos = saldo final; totais de
  crédito/débito do resumo; e cada saldo parcial impresso linha a linha.
- **Fatura de cartão:** saldo anterior + Σ lançamentos = total da fatura.
- **Investimento:** saldo anterior + rendimento = saldo atual.

Se algo não bate, aparece **❌ DIVERGÊNCIA** na tela e na aba Auditoria — assim
você nunca gera um Excel silenciosamente errado.

## Categorização automática

Cada lançamento é classificado (Impostos e Tributos, Tarifas e Juros, Folha e
Salários, Pix enviado/recebido, Boletos e Fornecedores, Cartão, Rendimentos e
Aplicações, Concessionárias, Seguros, Transferências, Saques e Depósitos…). As
regras ficam num único arquivo fácil de editar: [categorizador.py](extrato/categorizador.py).

## Precisão por banco/tipo

Cada banco/tipo tem um layout diferente. Estão **ajustados e testados, com
auditoria conferindo 100% dos saldos** (conta corrente):

- **Santander PF** (Extrato Consolidado Inteligente) — testado jan e abr.
- **Nubank** (layout 2026, 272 lançamentos reconciliados).
- **Bradesco** (Extrato Mensal / Por Período).
- **Banco do Brasil** (conta PJ com varredura "Rende Fácil", 361 lançamentos).
- **Caixa Econômica Federal** (PDF **escaneado**, lido por OCR — reconciliado).
- **Sicoob** (SISBR, 966 lançamentos reconciliados por coordenadas de coluna).

Os demais bancos usam um **leitor genérico** (funciona na maioria dos casos; a
auditoria avisa quando não fecha). Faturas de cartão e investimentos têm a
estrutura pronta e viram parsers dedicados assim que houver um PDF real.

## PDFs escaneados (OCR)

PDFs que são **imagem** (sem texto selecionável, como o extrato da Caixa) são
lidos automaticamente por **OCR**, com dois motores conforme onde o app roda:

- **App local e Render:** OCR no servidor (RapidOCR/ONNX, sem binário externo).
- **Site no Vercel:** OCR **no seu navegador** (pdf.js + tesseract.js, servidos
  pelo próprio site) — o PDF escaneado nem sobe: só o texto reconhecido é
  enviado. A 1ª vez baixa ~8 MB de bibliotecas (depois fica em cache).

O melhor: a **auditoria continua valendo** — se o OCR errar um número, os saldos
não fecham e você é avisado, em vez de receber um Excel silenciosamente errado.
(No layout da Caixa há até autocorreção: valor com vírgula ilegível é derivado
da diferença de saldos impressa no próprio extrato.) O OCR é mais lento
(alguns segundos por página).

👉 Para deixar 100% preciso, envie **um PDF de exemplo** de cada (banco, tipo) —
pode redigir nomes/valores, desde que as colunas fiquem visíveis — que eu ajusto o
leitor específico.

## Estrutura do projeto

```
app.py                 Servidor web (Flask) — local, Render e Vercel
iniciar.bat            Duplo-clique para rodar tudo
api/index.py           Ponto de entrada do Vercel (serverless)
vercel.json            Config do Vercel · render.yaml: config do Render
requirements.txt       Dependências core · requirements-ocr.txt: OCR do servidor
templates/index.html   Página de arrastar-e-soltar (inclui o OCR no navegador)
static/vendor/         pdf.js + tesseract.js (OCR no navegador, sem CDN externo)
extrato/
  extracao.py          Toolkit de extração (linhas, palavras/colunas, tabelas)
  detector.py          Identifica banco + tipo de documento
  identificacao.py     Titular/período (para nomear o Excel)
  normalizar.py        Datas pt-BR, valores em R$, modelo Transacao/Extrato
  categorizador.py     Motor de categorização por regras (editável)
  auditoria.py         Reconciliação de saldos por tipo de documento
  ocr.py               OCR do servidor (RapidOCR) p/ PDFs escaneados
  excel.py             Geração do .xlsx (Transações/Conferência/Resumo/Categorias/Auditoria)
  conversor.py         Orquestra PDF → transações → Excel
  parsers/
    base.py            Extrator genérico (fallback)
    conta_corrente/    santander.py, nubank.py, sicoob.py, caixa.py, ...
    fatura/            (parsers dedicados; _template.py mostra o contrato)
    investimento/      (parsers dedicados; _template.py mostra o contrato)
tests/
  test_reconciliacao.py  Testes (reconciliação + unidade)
  casos.py               Manifesto de PDFs esperados
  fixtures/              Coloque aqui PDFs de exemplo
DEPLOY.md              Como publicar (Vercel/Render) e proteger com senha
```

## Rodar pelo terminal / testes

```
python -m pip install -r requirements-dev.txt   # core + OCR + pytest
python app.py                 # sobe o app
python -m pytest tests/ -v    # roda os testes (reconciliação + unidade)
```

## Como adicionar um novo banco/tipo

1. Copie o parser de referência
   ([conta_corrente/santander.py](extrato/parsers/conta_corrente/santander.py))
   ou o `_template.py` do tipo (fatura/investimento).
2. Implemente `parse(caminho) -> Extrato`, preenchendo os metadados de
   conferência (saldos/totais) para a auditoria.
3. Registre o par `(banco, tipo)` em [parsers/__init__.py](extrato/parsers/__init__.py).
4. Adicione um caso em [tests/casos.py](tests/casos.py) e rode os testes.
