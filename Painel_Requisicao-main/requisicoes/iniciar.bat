@echo off
setlocal enabledelayedexpansion
title REQ//PAINEL - Dark Neon Cyberpunk
color 0B

echo.
echo ==============================================================
echo   [+] REQ//PAINEL - Gestao de Requisicoes e Portfolio GitHub
echo   Identidade Visual Dark Neon Cyberpunk
echo ==============================================================
echo.

set "PY_CMD="

where python >nul 2>nul
if %errorlevel% equ 0 (
    set "PY_CMD=python"
) else (
    where py >nul 2>nul
    if !errorlevel! equ 0 (
        set "PY_CMD=py"
    ) else (
        if exist "C:\Python314\python.exe" (
            set "PY_CMD=C:\Python314\python.exe"
        ) else (
            for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
                if exist "%%D\python.exe" set "PY_CMD=%%D\python.exe"
            )
        )
    )
)

if "%PY_CMD%"=="" (
    echo [ERRO] Python nao foi encontrado no sistema.
    echo Por favor, instale o Python 3.10 ou superior para executar.
    echo Baixe em: https://www.python.org/downloads/
    pause
    exit /b 1
)

cd /d "%~dp0requisicoes" 2>nul || cd /d "%~dp0"

if not exist ".env" (
    if exist ".env.example" (
        echo [INFO] Criando .env local a partir de .env.example...
        copy /y ".env.example" ".env" >nul
    )
)

echo [INFO] Utilizando: %PY_CMD%
echo [INFO] Iniciando servidor do Painel em http://0.0.0.0:5000 ...
echo [INFO] Acesso Desktop Local:   http://localhost:5000
echo [INFO] Acesso Modo TV Kiosk:   http://localhost:5000/tv
echo.
echo [TV CORP] Para exibir em Smart TVs ou Raspberry Pi na mesma rede:
echo           Acesse http://^<IP-DESTE-PC^>:5000/tv no navegador da TV.
echo [DICA]    Pressione F11 ou a tecla F na TV para Tela Cheia sem bordas.
echo [DICA]    Para encerrar o servidor, pressione CTRL + C nesta janela.
echo.

start "" "http://127.0.0.1:5000"
%PY_CMD% run.py

if %errorlevel% neq 0 (
    echo.
    echo [AVISO] O servidor foi finalizado ou encontrou um erro.
    pause
)
