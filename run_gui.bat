@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Pytest Runner GUI

if not exist ".venv\Scripts\python.exe" (
    echo L'environnement .venv est introuvable.
    echo Lance d'abord "start.bat" ou "install_offline.bat" une fois pour l'installer.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" main_qt.py
set "APP_CODE=%ERRORLEVEL%"
if not "%APP_CODE%"=="0" (
    echo.
    echo L'application s'est arretee avec le code %APP_CODE%.
    pause
)
exit /b %APP_CODE%
