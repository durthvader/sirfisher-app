@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

cd /d "%~dp0"

set "SCRIPT=04_importar_bb.py"
set "OLD=relatorio-bb-extrato-old"
set "ENCONTROU=0"

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

echo Procurando arquivos do Banco do Brasil...
echo Padrao: "Extrato conta corrente - ??????.csv"
echo.

for %%F in ("Extrato conta corrente - ??????.csv") do (
    if exist "%%~fF" (
        set "ENCONTROU=1"

        echo ========================================
        echo Arquivo encontrado:
        echo "%%~nxF"
        echo.

        echo Importando no banco...
        python "%SCRIPT%" "%%~fF"

        if !ERRORLEVEL! EQU 0 (
            echo.
            echo Importacao OK. Movendo arquivo para "%OLD%"...
            move /Y "%%~fF" "%OLD%\%%~nxF" >nul

            if !ERRORLEVEL! EQU 0 (
                echo Arquivo movido com sucesso.
            ) else (
                echo ERRO: Importou, mas nao conseguiu mover o arquivo.
            )
        ) else (
            echo.
            echo ERRO: Falha na importacao. Arquivo NAO foi movido.
        )

        echo.
    )
)

if "%ENCONTROU%"=="0" (
    echo ERRO: Nenhum arquivo encontrado no padrao:
    echo "Extrato conta corrente - ??????.csv"
    echo.
    pause
    exit /b 1
)

echo ========================================
echo Finalizado.
pause