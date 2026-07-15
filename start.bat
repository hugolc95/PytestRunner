@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Pytest Runner GUI

if not exist ".venv\Scripts\python.exe" (
    call install_offline.bat
    if errorlevel 1 exit /b 1
)

".venv\Scripts\python.exe" -c "import sys,struct; assert sys.version_info[:2]==(3,13) and struct.calcsize('P')==4" >nul 2>&1
if errorlevel 1 (
    echo L'environnement .venv n'est pas en Python 3.13 32 bits.
    echo Il va etre recree.
    rmdir /s /q ".venv"
    call install_offline.bat
    if errorlevel 1 exit /b 1
)

call setup\05_run_app.bat
exit /b %ERRORLEVEL%
