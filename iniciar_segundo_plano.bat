@echo off
title S.G. Lira's - Segundo Plano
cd /d "%~dp0"

:: Verifica se já está rodando
netstat -ano | findstr ":8888" >nul 2>&1
if not errorlevel 1 (
    echo.
    echo  [AVISO] O servidor ja esta rodando na porta 8888!
    echo  Acesse: http://192.168.0.220:8888
    echo.
    pause
    exit /b
)

:: Ativa o ambiente virtual
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

:: Garante que Waitress está instalado
python -c "import waitress" 2>nul
if errorlevel 1 (
    pip install waitress >nul 2>&1
)

echo.
echo  Iniciando S.G. Lira's em segundo plano...

:: Inicia minimizado
start "S.G. Lira's" /min cmd /c "call venv\Scripts\activate.bat && python app.py"

:: Aguarda e abre o navegador
timeout /t 4 /nobreak >nul
start http://192.168.0.220:8888

echo  Servidor iniciado!
echo  Para parar, execute "parar.bat"
echo.
timeout /t 3 /nobreak >nul
