@echo off
setlocal

rem Garante comandos basicos do Windows no PATH
set "PATH=%SystemRoot%\System32;%SystemRoot%;%SystemRoot%\System32\Wbem;%SystemRoot%\System32\WindowsPowerShell\v1.0;C:\Python314\Scripts;C:\Python314;C:\Users\GuilhermeAlvesMarucc\AppData\Local\Programs\Python\Python314;C:\Users\GuilhermeAlvesMarucc\AppData\Local\Programs\Python\Python314\Scripts;%PATH%"

cd /d "%~dp0"

set "PROJETO=%~dp0requisicoes\atualizar-requisicoes.bat"

if exist "%PROJETO%" (
    cd /d "%~dp0requisicoes"
    call "atualizar-requisicoes.bat"
) else (
    echo [ERRO] Arquivo de inicializacao nao encontrado em:
    echo   %PROJETO%
    echo.
)
pause
