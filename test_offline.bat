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

call setup\02b_install_dev_deps.bat
if errorlevel 1 exit /b 1

call setup\06_run_internal_tests.bat
exit /b %ERRORLEVEL%
