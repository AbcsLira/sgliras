@echo off
title Diagnostico Estoque Lira's
cd /d "%~dp0"

echo ==========================================
echo  DIAGNOSTICO - Estoque Lira's
echo ==========================================
echo.

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    echo [OK] Ambiente virtual ativado.
) else (
    echo [AVISO] Sem ambiente virtual, usando Python global.
)

echo.
echo --- Verificando Python ---
python --version
echo.

echo --- Verificando dependencias ---
python -c "import flask; print('Flask OK:', flask.__version__)"
python -c "import waitress; print('Waitress OK')"
python -c "import sqlite3; print('SQLite3 OK')"
echo.

echo --- Testando importacao do app ---
python -c "import app; print('app.py importado OK')"
echo.

echo --- Testando banco de dados ---
python -c "import app; app.init_db(); print('Banco OK')"
echo.

echo --- Iniciando servidor com log completo ---
python -u app.py

echo.
echo ==========================================
echo  FIM DO DIAGNOSTICO
echo ==========================================
pause
