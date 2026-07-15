@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
title Pytest Runner - Installation des dependances SmartcardFramework

if not exist ".venv\Scripts\python.exe" (
    echo ERREUR : .venv est introuvable. Lancez d'abord setup\01_create_venv.bat.
    pause
    exit /b 1
)

if not exist "requirements-smartcard.txt" (
    echo ERREUR : requirements-smartcard.txt est introuvable.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --no-index --find-links="%CD%\wheels" -r requirements-smartcard.txt
if errorlevel 1 (
    echo.
    echo ERREUR : installation des dependances SmartcardFramework impossible.
    pause
    exit /b 1
)

echo.
echo Dependances SmartcardFramework installees.
echo Rappel : cryptography est fige a la version 48.0.1 ^(derniere version avec wheel 32 bits^).
exit /b 0
