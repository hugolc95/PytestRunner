@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
title Pytest Runner - Creation environnement Python 3.13 x86

echo ============================================================
echo  Etape 1/2 : creation de l'environnement (Python 3.13 32 bits)
echo ============================================================
echo.

call :find_python
if errorlevel 1 goto :python_error

if not exist "wheels\PyQt5-5.15.11-cp38-abi3-win32.whl" goto :wheels_error
if not exist "wheels\pyqt5_sip-12.18.0-cp313-cp313-win32.whl" goto :wheels_error
if not exist "wheels\pyyaml-6.0.3-cp313-cp313-win32.whl" goto :wheels_error

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys,struct; assert sys.version_info[:2]==(3,13) and struct.calcsize('P')==4" >nul 2>&1
    if errorlevel 1 (
        echo Suppression d'un ancien environnement incompatible...
        rmdir /s /q ".venv"
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo Creation de l'environnement Python 3.13 x86...
    %PYTHON_CMD% -m venv ".venv"
    if errorlevel 1 goto :venv_error
)

echo.
echo Environnement pret dans .venv\
exit /b 0

:find_python
set "PYTHON_CMD="
where py >nul 2>&1
if not errorlevel 1 (
    py -3.13-32 -c "import sys,struct; assert sys.version_info[:2]==(3,13) and struct.calcsize('P')==4" >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=py -3.13-32"
)
if defined PYTHON_CMD exit /b 0

where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys,struct; assert sys.version_info[:2]==(3,13) and struct.calcsize('P')==4" >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=python"
)
if defined PYTHON_CMD exit /b 0
exit /b 1

:python_error
echo ERREUR : Python 3.13 32 bits ^(x86^) est introuvable.
echo.
echo Verifiez les installations avec :
echo     py -0p
echo.
echo La ligne attendue doit contenir : -3.13-32
echo Un Python 3.13 64 bits ne convient pas a cette archive.
pause
exit /b 1

:wheels_error
echo ERREUR : le dossier wheels est absent ou incomplet.
echo Reextrayez toute l'archive avant de relancer.
pause
exit /b 1

:venv_error
echo ERREUR : la creation de l'environnement virtuel a echoue.
pause
exit /b 1
