@echo off
title S.G. Lira's
cd /d "%~dp0"

echo.
echo  ==========================================
echo   S.G. Lira's - Iniciando servidor...
echo  ==========================================
echo.

:: Ativa o ambiente virtual se existir
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    echo  [OK] Ambiente virtual ativado.
) else (
    echo  [AVISO] Ambiente virtual nao encontrado.
    echo  Usando Python global do sistema.
    echo.
)

:: Verifica se o Flask está instalado
python -c "import flask" 2>nul
if errorlevel 1 (
    echo  [INFO] Instalando dependencias...
    pip install -r requirements.txt
    echo.
)

:: Verifica se o Waitress está instalado
python -c "import waitress" 2>nul
if errorlevel 1 (
    echo  [INFO] Instalando Waitress...
    pip install waitress
    echo.
)

echo  Servidor rodando. Acesse: http://192.168.0.220:8888
echo  Pressione Ctrl+C para parar.
echo.

:: Roda o servidor e captura erros
python app.py 2>&1
if errorlevel 1 (
    echo.
    echo  ==========================================
    echo   ERRO ao iniciar o servidor!
    echo  ==========================================
    echo.
    echo  Detalhes do erro acima ^(scroll para ver^).
    echo  Tire um print desta tela e mande pro suporte.
    echo.
)

echo.
echo  Servidor encerrado.
pause
