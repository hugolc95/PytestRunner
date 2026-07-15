@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
title Pytest Runner - Installation des dependances de dev

if not exist ".venv\Scripts\python.exe" (
    echo ERREUR : .venv est introuvable. Lancez d'abord setup\01_create_venv.bat.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --no-index --find-links="%CD%\wheels" -r requirements-dev.txt
if errorlevel 1 (
    echo.
    echo ERREUR : installation des dependances de dev impossible.
    pause
    exit /b 1
)

echo.
echo Dependances de dev installees.
exit /b 0
