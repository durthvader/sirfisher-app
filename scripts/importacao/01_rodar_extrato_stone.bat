@echo off
chcp 65001 >nul
title Importar Extrato Stone
setlocal EnableDelayedExpansion

cd /d "%~dp0"

set "SCRIPT=01_importar_extrato_stone.py"
set "OLD=relatorio-stone-extrato-old"
set "ARQUIVO="

if not exist "%SCRIPT%" (
    echo.
    echo ERRO: Script nao encontrado:
    echo "%SCRIPT%"
    echo Coloque este BAT na mesma pasta do arquivo Python.
    echo.
    pause
    exit /b 1
)

if not exist "%OLD%" (
    mkdir "%OLD%"
)

echo Procurando arquivo de extrato Stone...
echo Padrao: "Comprovante de Extrato*.csv"
echo.

for %%F in ("Comprovante de Extrato*.csv") do (
    if exist "%%~fF" (
        set "ARQUIVO=%%~fF"
        set "NOME_ARQUIVO=%%~nxF"
        goto :achou
    )
)

:achou

if not defined ARQUIVO (
    echo.
    echo ERRO: Nenhum arquivo encontrado no padrao:
    echo "Comprovante de Extrato*.csv"
    echo.
    pause
    exit /b 1
)

echo.
echo Arquivo encontrado:
echo "%NOME_ARQUIVO%"
echo.

echo Importando no banco...
python "%SCRIPT%" "%ARQUIVO%"

if !ERRORLEVEL! NEQ 0 (
    echo.
    echo ERRO ao importar:
    echo "%NOME_ARQUIVO%"
    echo Arquivo NAO foi movido.
    echo Processo interrompido.
    pause
    exit /b 1
)

echo.
echo Importacao OK. Movendo para "%OLD%"...
move /Y "%ARQUIVO%" "%OLD%\%NOME_ARQUIVO%" >nul

if !ERRORLEVEL! NEQ 0 (
    echo.
    echo ERRO: Importou, mas nao conseguiu mover o arquivo:
    echo "%NOME_ARQUIVO%"
    echo Verifique se a pasta "%OLD%" existe e se o arquivo nao esta aberto.
    echo.
    pause
    exit /b 1
) else (
    echo Arquivo movido com sucesso:
    echo "%NOME_ARQUIVO%"
)

echo.
echo ============================================
echo Processo finalizado.
echo ============================================
pause