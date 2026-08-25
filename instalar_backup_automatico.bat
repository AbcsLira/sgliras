@echo off
title Instalar Backup Automatico - Estoque Lira's
cd /d "%~dp0"

echo.
echo  ============================================
echo   Instalando backup automatico...
echo  ============================================
echo.

:: Verificar se está rodando como administrador
net session >nul 2>&1
if errorlevel 1 (
    echo  [ERRO] Execute este arquivo como Administrador!
    echo  Clique com botao direito - Executar como administrador
    pause
    exit /b 1
)

:: Configurar o caminho absoluto do script de backup
set SCRIPT_PATH=%~dp0backup_externo.bat

:: Criar a tarefa agendada
:: Roda todo dia às 03:00 da manhã
schtasks /create ^
    /tn "EstoqueLiras_BackupExterno" ^
    /tr "\"%SCRIPT_PATH%\"" ^
    /sc daily ^
    /st 03:00 ^
    /ru SYSTEM ^
    /rl highest ^
    /f

if errorlevel 1 (
    echo.
    echo  [ERRO] Nao foi possivel criar a tarefa agendada.
    echo  Certifique-se de estar rodando como Administrador.
    pause
    exit /b 1
)

echo.
echo  ============================================
echo   [OK] Backup automatico instalado!
echo  ============================================
echo.
echo  O sistema vai fazer backup automatico
echo  todo dia as 03:00 da manha para o
echo  HD externo/pen drive.
echo.
echo  Para verificar: Agendador de Tarefas do
echo  Windows - procure "EstoqueLiras_BackupExterno"
echo.
echo  Para remover:
echo  schtasks /delete /tn "EstoqueLiras_BackupExterno" /f
echo.

:: Rodar o primeiro backup agora mesmo
echo  Rodando primeiro backup agora...
call "%SCRIPT_PATH%"
if errorlevel 1 (
    echo.
    echo  [AVISO] Primeiro backup falhou.
    echo  Verifique se o HD externo esta conectado
    echo  e a letra da unidade no backup_externo.bat
) else (
    echo  [OK] Primeiro backup realizado com sucesso!
)

echo.
pause
