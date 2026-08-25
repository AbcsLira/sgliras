@echo off
title Verificar Backup - Estoque Lira's
cd /d "%~dp0"

echo.
echo  ============================================
echo   Status do Backup - Estoque Lira's
echo  ============================================
echo.

:: --- Banco principal ---
if exist "%~dp0estoque.db" (
    echo  [OK] Banco principal encontrado
    for %%f in ("%~dp0estoque.db") do (
        echo       Tamanho: %%~zf bytes
        echo       Modificado: %%~tf
    )
) else (
    echo  [ERRO] Banco principal NAO encontrado!
)

echo.

:: --- Backups internos ---
echo  --- Backups internos (pasta backups\) ---
if exist "%~dp0backups\" (
    set COUNT=0
    set MAIS_RECENTE=
    for /f "delims=" %%f in ('dir /b /o-d "%~dp0backups\*.db" 2^>nul') do (
        set /a COUNT+=1
        if !COUNT!==1 set MAIS_RECENTE=%%f
    )
    echo  Total de backups: !COUNT!
    if defined MAIS_RECENTE (
        echo  Mais recente: !MAIS_RECENTE!
    )
) else (
    echo  [AVISO] Pasta de backups nao encontrada
)

echo.

:: --- Backup externo ---
set UNIDADE_EXTERNA=E:
set PASTA_DESTINO=%UNIDADE_EXTERNA%\Backup_EstoqueLiras

echo  --- Backup externo (%UNIDADE_EXTERNA%) ---
if not exist "%UNIDADE_EXTERNA%\" (
    echo  [AVISO] Dispositivo externo nao conectado em %UNIDADE_EXTERNA%
) else (
    if exist "%PASTA_DESTINO%\ULTIMO_BACKUP.txt" (
        echo  [OK] Backup externo encontrado
        echo.
        echo  Informacoes do ultimo backup:
        type "%PASTA_DESTINO%\ULTIMO_BACKUP.txt"
        echo.
        set COUNT_EXT=0
        for /f %%f in ('dir /b "%PASTA_DESTINO%\banco\estoque_*.db" 2^>nul') do set /a COUNT_EXT+=1
        echo  Arquivos no HD externo: !COUNT_EXT!
    ) else (
        echo  [AVISO] Nenhum backup externo encontrado ainda
        echo  Execute instalar_backup_automatico.bat para configurar
    )
)

echo.

:: --- Tarefa agendada ---
echo  --- Tarefa agendada ---
schtasks /query /tn "EstoqueLiras_BackupExterno" >nul 2>&1
if errorlevel 1 (
    echo  [AVISO] Backup automatico NAO esta instalado
    echo  Execute instalar_backup_automatico.bat para configurar
) else (
    echo  [OK] Backup automatico instalado
    schtasks /query /tn "EstoqueLiras_BackupExterno" /fo list | findstr /i "status proxima"
)

echo.
echo  ============================================
pause
