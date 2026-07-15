@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
title Tests Pytest Runner - Python 3.13 x86

if not exist ".venv\Scripts\python.exe" (
    echo ERREUR : .venv est introuvable. Lancez d'abord setup\01_create_venv.bat.
    pause
    exit /b 1
)

call setup\04_set_smartcard_path.bat

set "QT_QPA_PLATFORM=offscreen"
".venv\Scripts\python.exe" -m pytest -q tests
if errorlevel 1 goto :error

echo.
echo Tous les tests sont passes.
pause
exit /b 0

:error
echo.
echo Un test a echoue.
pause
exit /b 1
