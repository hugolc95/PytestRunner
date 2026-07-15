@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Installation Pytest Runner - Python 3.13 x86

echo ============================================================
echo  Installation hors ligne - Python 3.13 32 bits uniquement
echo ============================================================
echo.

call setup\01_create_venv.bat
if errorlevel 1 exit /b 1

call setup\02_install_core_deps.bat
if errorlevel 1 exit /b 1

echo.
echo Installation terminee avec succes.
exit /b 0
