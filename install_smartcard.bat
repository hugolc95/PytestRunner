@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Pytest Runner - Installation SmartcardFramework

if not exist ".venv\Scripts\python.exe" (
    echo L'environnement .venv est introuvable.
    echo Lance d'abord "install_offline.bat" une fois pour l'installer.
    pause
    exit /b 1
)

call setup\03_install_smartcard_deps.bat
exit /b %ERRORLEVEL%
