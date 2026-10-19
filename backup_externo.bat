@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Backup Externo - Estoque Lira's
cd /d "%~dp0"

:: CONFIGURACAO - altere a letra da unidade se necessario
set "UNIDADE_EXTERNA=G:"
set "PASTA_DESTINO=%UNIDADE_EXTERNA%\Backup_EstoqueLiras"
set "LOG_FILE=%~dp0backup_externo.log"

echo. >> "%LOG_FILE%"
echo ============================================ >> "%LOG_FILE%"
echo Iniciando backup externo: %date% %time% >> "%LOG_FILE%"

if not exist "%UNIDADE_EXTERNA%\" (
    echo [ERRO] Dispositivo externo nao encontrado em %UNIDADE_EXTERNA% >> "%LOG_FILE%"
    echo [ERRO] Verifique se o HD/pen drive esta conectado em %UNIDADE_EXTERNA%
    exit /b 1
)

for %%d in ("%PASTA_DESTINO%" "%PASTA_DESTINO%\banco" "%PASTA_DESTINO%\logs") do (
    if not exist "%%~d\" mkdir "%%~d" >> "%LOG_FILE%" 2>&1
    if not exist "%%~d\" goto :falha_destino
)

:: Usa o mesmo ambiente virtual da aplicacao, quando disponivel.
set "PY_ARGS="
set "PYEXE=%~dp0venv\Scripts\python.exe"
if exist "%PYEXE%" goto :python_encontrado
set "PYEXE=%~dp0.venv\Scripts\python.exe"
if exist "%PYEXE%" goto :python_encontrado
where python >nul 2>&1
if not errorlevel 1 (
    set "PYEXE=python"
    goto :python_encontrado
)
where py >nul 2>&1
if not errorlevel 1 (
    set "PYEXE=py"
    set "PY_ARGS=-3"
    goto :python_encontrado
)
echo [ERRO] Python nao encontrado. Execute instalar.bat. >> "%LOG_FILE%"
echo [ERRO] Python nao encontrado. Execute instalar.bat.
exit /b 1

:python_encontrado
:: A API SQLite inclui o WAL e nunca substitui um backup existente.
echo Gerando copia consistente do banco principal... >> "%LOG_FILE%"
"%PYEXE%" %PY_ARGS% "%~dp0backup_banco.py" --pasta "%PASTA_DESTINO%\banco" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :falha_principal
echo [OK] Banco principal copiado e verificado >> "%LOG_FILE%"

:: Copias diarias tambem sao verificadas; arquivos existentes sao preservados.
if exist "%~dp0backups\" (
    for %%f in ("%~dp0backups\*.db") do (
        if exist "%%~ff" (
            if not exist "%PASTA_DESTINO%\banco\%%~nxf" (
                "%PYEXE%" %PY_ARGS% "%~dp0backup_banco.py" "%PASTA_DESTINO%\banco\%%~nxf" --origem "%%~ff" >> "%LOG_FILE%" 2>&1
                if errorlevel 1 goto :falha_diarios
            )
        )
    )
)

:: Retencao por data no nome; copiar diarios nao os torna mais recentes.
:: Executada somente depois de confirmar os novos backups.
echo Limpando arquivos antigos no destino... >> "%LOG_FILE%"
for /f "skip=60 delims=" %%f in ('dir /b /a-d /o-n "%PASTA_DESTINO%\banco\estoque_*.db" 2^>nul') do (
    del "%PASTA_DESTINO%\banco\%%f" >> "%LOG_FILE%" 2>&1
    if errorlevel 1 goto :falha_limpeza
    echo [OK] Removido arquivo antigo: %%f >> "%LOG_FILE%"
)

(
    echo Ultimo backup: %date% %time%
    echo Computador: %COMPUTERNAME%
    echo Pasta origem: "%~dp0"
) > "%PASTA_DESTINO%\ULTIMO_BACKUP.txt"
if errorlevel 1 goto :falha_status
copy /Y "%LOG_FILE%" "%PASTA_DESTINO%\logs\backup_externo.log" >nul 2>&1
if errorlevel 1 goto :falha_status

echo [OK] Backup externo concluido com sucesso >> "%LOG_FILE%"
echo Backup externo concluido: %date% %time%
exit /b 0

:falha_destino
echo [ERRO] Nao foi possivel preparar a pasta de destino. >> "%LOG_FILE%"
echo [ERRO] Nao foi possivel preparar a pasta de destino.
exit /b 1

:falha_principal
echo [ERRO] Banco principal NAO copiado; backups antigos e status preservados. >> "%LOG_FILE%"
echo [ERRO] Backup principal falhou. Consulte backup_externo.log.
exit /b 1

:falha_diarios
echo [ERRO] Uma copia diaria falhou; limpeza e atualizacao de status canceladas. >> "%LOG_FILE%"
echo [ERRO] Copia diaria falhou. Consulte backup_externo.log.
exit /b 1

:falha_limpeza
echo [ERRO] Falha ao limpar backup antigo; status nao atualizado. >> "%LOG_FILE%"
echo [ERRO] Falha na limpeza. Consulte backup_externo.log.
exit /b 1

:falha_status
echo [ERRO] Backup criado, mas falhou a gravacao do status ou log externo. >> "%LOG_FILE%"
echo [ERRO] Falha ao gravar status ou log externo. Consulte backup_externo.log.
exit /b 1
