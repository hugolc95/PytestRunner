@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
title Pytest Runner - Installation des dependances de base

if not exist ".venv\Scripts\python.exe" (
    echo ERREUR : .venv est introuvable. Lancez d'abord setup\01_create_venv.bat.
    pause
    exit /b 1
)

echo Installation depuis le dossier local wheels uniquement...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --no-index --find-links="%CD%\wheels" -r requirements.txt
if errorlevel 1 goto :install_error

".venv\Scripts\python.exe" -c "import sys,struct,PyQt5,pytest,yaml; assert sys.version_info[:2]==(3,13); assert struct.calcsize('P')==4; print('OK - Python',sys.version.split()[0],'- 32 bits - PyQt5 et pytest disponibles')"
if errorlevel 1 goto :install_error

echo.
echo Dependances de base installees.
exit /b 0

:install_error
echo.
echo ERREUR : installation hors ligne impossible.
echo Aucun acces Internet n'a ete tente.
pause
exit /b 1
