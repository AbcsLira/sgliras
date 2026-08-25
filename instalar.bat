@echo off
title Instalacao - Estoque Lira's
cd /d "%~dp0"

echo.
echo  ==========================================
echo   Estoque Lira's - Instalacao inicial
echo  ==========================================
echo.

:: Verifica Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERRO] Python nao encontrado!
    echo  Baixe em: https://www.python.org/downloads/
    echo  Lembre de marcar "Add Python to PATH" na instalacao.
    pause
    exit /b
)

echo  [OK] Python encontrado.

:: Cria ambiente virtual
echo  Criando ambiente virtual...
python -m venv venv
call venv\Scripts\activate.bat

:: Instala dependencias (Flask + Waitress)
echo  Instalando dependencias...
pip install -r requirements.txt

echo.
echo  ==========================================
echo   Instalacao concluida!
echo   Execute "iniciar.bat" para rodar o sistema.
echo  ==========================================
echo.
pause
