@echo off
setlocal
title Painel de Requisicoes - Sincronizacao

rem Garante comandos basicos do Windows no PATH
set "PATH=%SystemRoot%\System32;%SystemRoot%;%SystemRoot%\System32\Wbem;%SystemRoot%\System32\WindowsPowerShell\v1.0;C:\Python314\Scripts;C:\Python314;C:\Users\GuilhermeAlvesMarucc\AppData\Local\Programs\Python\Python314;C:\Users\GuilhermeAlvesMarucc\AppData\Local\Programs\Python\Python314\Scripts;%PATH%"

cd /d "%~dp0"

echo ===================================================
echo   Painel de Requisicoes - Inicializacao do Servico
echo ===================================================
echo.

set "PY_EXEC="

if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY_EXEC=%~dp0.venv\Scripts\python.exe"
    echo [INFO] Utilizando ambiente virtual local: .venv
    goto python_ok
)

if exist "C:\Python314\python.exe" (
    set "PY_EXEC=C:\Python314\python.exe"
    echo [INFO] Utilizando Python instalado em C:\Python314
    goto python_ok
)

if exist "%LocalAppData%\Programs\Python\Python314\python.exe" (
    set "PY_EXEC=%LocalAppData%\Programs\Python\Python314\python.exe"
    echo [INFO] Utilizando Python do usuario
    goto python_ok
)

where python >nul 2>&1
if not errorlevel 1 (
    set "PY_EXEC=python"
    echo [INFO] Utilizando interpretador Python do PATH
    goto python_ok
)

where py >nul 2>&1
if not errorlevel 1 (
    set "PY_EXEC=py"
    echo [INFO] Utilizando Python Launcher: py
    goto python_ok
)

echo.
echo [ERRO CRITICO] O Python nao foi encontrado no sistema!
echo Instale o Python 3 e certifique-se de que esta no PATH.
echo.
pause
exit /b 1

:python_ok

rem Inicia o servidor web Flask em segundo plano se a porta 5000 nao estiver em uso
netstat -ano 2>nul | findstr /C:":5000 " >nul 2>&1
if errorlevel 1 (
    echo [INFO] Iniciando servidor web Flask na porta 5000...
    start "API - Painel de Requisicoes" /d "%~dp0" cmd /k ""%PY_EXEC%" app.py"
) else (
    echo [INFO] Servidor web Flask ja esta ativo na porta 5000.
)

echo [INFO] Servico de coleta iniciado. Pressione Ctrl+C para encerrar.
echo.

:loop
echo ===================================================
echo  COLETA / SINCRONIZACAO ERP: %DATE% %TIME%
echo ===================================================
"%PY_EXEC%" "%~dp0sincronizar.py" --fonte erp --alvo tv
echo.
echo [INFO] Aguardando 60 segundos para proxima sincronizacao...
timeout /t 60 /nobreak >nul 2>&1 || ping 127.0.0.1 -n 61 >nul
goto loop
