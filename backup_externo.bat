@echo off
setlocal enabledelayedexpansion
title Backup Externo - Estoque Lira's
cd /d "%~dp0"

:: ============================================================
::  Backup Externo - Estoque Lira's
::  Copia o banco e backups para o HD externo/pen drive
:: ============================================================

:: CONFIGURAÇÃO — altere a letra da unidade se necessário
set UNIDADE_EXTERNA=G:
set PASTA_DESTINO=%UNIDADE_EXTERNA%\Backup_EstoqueLiras

set LOG_FILE=%~dp0backup_externo.log
set DATA_HORA=%date:~6,4%-%date:~3,2%-%date:~0,2%_%time:~0,2%-%time:~3,2%
set DATA_HORA=%DATA_HORA: =0%

echo. >> "%LOG_FILE%"
echo ============================================ >> "%LOG_FILE%"
echo Iniciando backup externo: %date% %time% >> "%LOG_FILE%"

:: 1. Verificar se o dispositivo externo está conectado
if not exist "%UNIDADE_EXTERNA%\" (
    echo [ERRO] Dispositivo externo nao encontrado em %UNIDADE_EXTERNA% >> "%LOG_FILE%"
    echo [ERRO] Dispositivo externo nao encontrado em %UNIDADE_EXTERNA%
    echo Verifique se o HD/pen drive esta conectado e tente novamente.
    exit /b 1
)

:: 2. Criar pasta de destino se não existir
if not exist "%PASTA_DESTINO%" mkdir "%PASTA_DESTINO%"
if not exist "%PASTA_DESTINO%\banco" mkdir "%PASTA_DESTINO%\banco"
if not exist "%PASTA_DESTINO%\logs" mkdir "%PASTA_DESTINO%\logs"

:: 3. Copiar o banco de dados principal
echo Copiando banco de dados principal... >> "%LOG_FILE%"
copy /Y "%~dp0estoque.db" "%PASTA_DESTINO%\banco\estoque_%DATA_HORA%.db" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo [ERRO] Falha ao copiar banco principal >> "%LOG_FILE%"
) else (
    echo [OK] Banco principal copiado >> "%LOG_FILE%"
)

:: 4. Copiar o backup diario mais recente (se existir)
if exist "%~dp0backups\" (
    echo Copiando backups diarios... >> "%LOG_FILE%"
    xcopy /Y /Q "%~dp0backups\*" "%PASTA_DESTINO%\banco\" >> "%LOG_FILE%" 2>&1
    echo [OK] Backups diarios copiados >> "%LOG_FILE%"
)

:: 5. Manter apenas os últimos 60 arquivos no HD externo (evita lotar)
echo Limpando arquivos antigos no destino... >> "%LOG_FILE%"
set COUNT=0
for /f "delims=" %%f in ('dir /b /o-d "%PASTA_DESTINO%\banco\estoque_*.db" 2^>nul') do (
    set /a COUNT+=1
    if !COUNT! gtr 60 (
        del "%PASTA_DESTINO%\banco\%%f" >> "%LOG_FILE%" 2>&1
        echo [OK] Removido arquivo antigo: %%f >> "%LOG_FILE%"
    )
)

:: 6. Salvar um arquivo de status legível
echo Ultimo backup: %date% %time% > "%PASTA_DESTINO%\ULTIMO_BACKUP.txt"
echo Computador: %COMPUTERNAME% >> "%PASTA_DESTINO%\ULTIMO_BACKUP.txt"
echo Pasta origem: %~dp0 >> "%PASTA_DESTINO%\ULTIMO_BACKUP.txt"

:: 7. Copiar log pro HD externo também
copy /Y "%LOG_FILE%" "%PASTA_DESTINO%\logs\backup_externo.log" >nul 2>&1

echo [OK] Backup externo concluido com sucesso >> "%LOG_FILE%"
echo Backup externo concluido: %date% %time%
exit /b 0
