@echo off
title Parar Estoque Lira's
cd /d "%~dp0"

echo.
echo  Encerrando Estoque Lira's...

:: Le a porta configurada no config.ini (padrao 5000 se nao encontrar)
set PORTA=5000
for /f "tokens=2 delims==" %%p in ('findstr /b "porta" config.ini 2^>nul') do (
    set PORTA=%%p
)
:: Remove espacos em branco
set PORTA=%PORTA: =%

echo  Porta detectada: %PORTA%

:: Para cada processo escutando na porta, tenta encerramento normal primeiro
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORTA% " ^| findstr "LISTENING"') do (
    echo  Enviando sinal de encerramento ao processo %%a...
    taskkill /PID %%a >nul 2>&1
)

:: Aguarda alguns segundos para o Flask encerrar sozinho
timeout /t 3 /nobreak >nul

:: Se ainda estiver rodando, forca o encerramento
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORTA% " ^| findstr "LISTENING"') do (
    echo  Processo ainda ativo, forcando encerramento...
    taskkill /PID %%a /F >nul 2>&1
)

echo  Servidor encerrado com sucesso.
echo.
timeout /t 2 /nobreak >nul
