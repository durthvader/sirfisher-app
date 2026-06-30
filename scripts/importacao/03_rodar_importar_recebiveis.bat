@echo off
chcp 65001 >nul
title Importar Recebiveis Stone
setlocal EnableDelayedExpansion

cd /d "%~dp0"

set "SCRIPT=03_importar_recebiveis_stone.py"
set "OLD=relatorio-stone-recebimentos-old"
set "ACHOU=0"

if not exist "%SCRIPT%" (
    echo ERRO: Script nao encontrado:
    echo "%SCRIPT%"
    echo.
    pause
    exit /b 1
)

if not exist "%OLD%" (
    mkdir "%OLD%"
)

echo Procurando arquivos relatorio-recebimentos-*.csv...
echo.

for %%F in ("relatorio-recebimentos-*.csv") do (
    if exist "%%~fF" (
        set "ACHOU=1"
        echo ============================================
        echo Importando: %%~nxF
        echo ============================================

        python "%SCRIPT%" "%%~fF"

        if !ERRORLEVEL! NEQ 0 (
            echo.
            echo ERRO ao importar: %%~nxF
            echo Arquivo NAO foi movido.
            echo Processo interrompido.
            pause
            exit /b 1
        )

        echo.
        echo Importacao OK. Movendo para "%OLD%"...
        move /Y "%%~fF" "%OLD%\%%~nxF" >nul

        if !ERRORLEVEL! NEQ 0 (
            echo ERRO: Importou, mas nao conseguiu mover o arquivo: %%~nxF
            pause
            exit /b 1
        ) else (
            echo Arquivo movido com sucesso: %%~nxF
        )

        echo.
    )
)

if "%ACHOU%"=="0" (
    echo Nenhum arquivo encontrado com o padrao:
    echo relatorio-recebimentos-*.csv
    echo.
    pause
    exit /b 1
)

echo ============================================
echo Processo finalizado.
echo ============================================
pause