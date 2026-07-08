@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   Conversor de Extratos PDF -^> Excel
echo ============================================
echo.

REM Instala as dependencias na primeira execucao (inclui OCR; silencioso se ja instaladas)
python -m pip install -q -r requirements-ocr.txt

echo Abrindo no navegador: http://127.0.0.1:5000
echo Para encerrar, feche esta janela.
echo.

REM Abre o navegador apos 2s e sobe o servidor
start "" /min cmd /c "timeout /t 2 >nul & start http://127.0.0.1:5000"
python app.py
pause
