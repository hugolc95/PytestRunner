@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Tests Pytest Runner - Python 3.13 x86

if not exist ".venv\Scripts\python.exe" (
    call install_offline.bat
    if errorlevel 1 exit /b 1
)

".venv\Scripts\python.exe" -c "import sys,struct; assert sys.version_info[:2]==(3,13) and struct.calcsize('P')==4" >nul 2>&1
if errorlevel 1 (
    echo ERREUR : .venv n'est pas en Python 3.13 32 bits.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --no-index --find-links="%CD%\wheels" -r requirements-dev.txt
if errorlevel 1 goto :error

set "QT_QPA_PLATFORM=offscreen"
".venv\Scripts\python.exe" -m pytest -q tests
if errorlevel 1 goto :error

echo.
echo Tous les tests sont passes.
pause
exit /b 0

:error
echo.
echo Un test ou une installation locale a echoue.
pause
exit /b 1
