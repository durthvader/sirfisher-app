@echo off
chcp 65001 >nul
title Importar Vendas Stone
setlocal EnableDelayedExpansion

cd /d "%~dp0"

set "SCRIPT=02_importar_vendas_stone.py"
set "OLD=relatorio-stone-vendas-old"
set "ACHOU=0"

if not exist "%SCRIPT%" (
    echo ERRO: Script %SCRIPT% nao encontrado.
    echo Coloque este BAT na mesma pasta do arquivo Python.
    echo.
    pause
    exit /b 1
)

if not exist "%OLD%" (
    mkdir "%OLD%"
)

echo Procurando arquivos CSV cujo nome seja UUID v4...
echo.

for /f "delims=" %%F in ('powershell -NoProfile -Command "Get-ChildItem -File -Filter *.csv | Where-Object { $_.Name -match '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\.csv$' } | Sort-Object Name | ForEach-Object { $_.Name }"') do (
    set "ACHOU=1"

    echo ============================================
    echo Importando: %%F
    echo ============================================

    python "%SCRIPT%" "%%F"

    if !ERRORLEVEL! NEQ 0 (
        echo.
        echo ERRO ao importar: %%F
        echo Arquivo NAO foi movido.
        echo Processo interrompido.
        pause
        exit /b 1
    )

    echo.
    echo Importacao OK. Movendo para "%OLD%"...
    move /Y "%%F" "%OLD%\%%F" >nul

    if !ERRORLEVEL! NEQ 0 (
        echo.
        echo ERRO: Importou, mas nao conseguiu mover o arquivo: %%F
        echo Verifique se a pasta "%OLD%" existe e se o arquivo nao esta aberto.
        pause
        exit /b 1
    ) else (
        echo Arquivo movido com sucesso: %%F
    )

    echo.
)

if "%ACHOU%"=="0" (
    echo Nenhum arquivo encontrado no padrao UUID v4:
    echo xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx.csv
    echo.
    pause
    exit /b 1
)

echo ============================================
echo Processo finalizado.
echo ============================================
pause