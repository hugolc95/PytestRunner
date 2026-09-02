@echo off
REM Construit Pytest Runner en application Windows x64 autonome (PySide6 / Qt 6).
REM
REM   build_exe.bat            interface courante -> dist\PytestRunner
REM   build_exe.bat run        construit puis lance la derniere version
REM   build_exe.bat help       ce message
REM
REM IMPORTANT : ce Python sert UNIQUEMENT a construire/lancer l'interface.
REM Les tests sont executes par l'interpreteur externe configure dans le Runner
REM (Python 3.13 x86 possible et recommande pour les DLL smart-card 32 bits).

setlocal
cd /d "%~dp0"

set "CIBLE=%~1"
if "%CIBLE%"=="" set "CIBLE=new"

if /i "%CIBLE%"=="help"    goto :usage
if /i "%CIBLE%"=="/?"      goto :usage
if /i "%CIBLE%"=="-h"      goto :usage
if /i "%CIBLE%"=="--help"  goto :usage

call :selectionner_python_x64
if errorlevel 1 exit /b 1
call :verifier_dependances
if errorlevel 1 exit /b 1

if /i "%CIBLE%"=="new"     goto :build_new
if /i "%CIBLE%"=="run"     goto :build_and_run
if /i "%CIBLE%"=="latest"  goto :build_and_run

echo Cible inconnue : %CIBLE%
echo.
goto :usage

:build_new
call :construire PytestRunner.spec "PySide6 x64"
if errorlevel 1 exit /b 1
call :bilan PytestRunner
exit /b 0

:build_and_run
call :construire PytestRunner.spec "PySide6 x64"
if errorlevel 1 exit /b 1
call :bilan PytestRunner
echo.
echo Lancement de la version qui vient d'etre construite...
start "Pytest Runner" "%CD%\dist\PytestRunner\PytestRunner.exe"
exit /b 0

:selectionner_python_x64
set "BUILD_PYTHON="
for /f "usebackq delims=" %%P in (`powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\select_x64_python.ps1"`) do if not defined BUILD_PYTHON set "BUILD_PYTHON=%%P"
if not defined BUILD_PYTHON (
    echo.
    echo ERREUR : aucun Python 64 bits n'a ete trouve.
    echo Le Python 32 bits reste uniquement l'interpreteur de lancement des tests.
    echo Vous pouvez definir PYTEST_RUNNER_BUILD_PYTHON avec le chemin du Python x64.
    echo.
    exit /b 1
)
echo Python x64 selectionne : %BUILD_PYTHON%
"%BUILD_PYTHON%" -c "import struct,sys; print('Architecture du build :', struct.calcsize('P') * 8, 'bits'); sys.exit(0 if struct.calcsize('P') * 8 == 64 else 1)"
if errorlevel 1 exit /b 1
exit /b 0

:verifier_dependances
"%BUILD_PYTHON%" -c "import PySide6" 2>nul
if errorlevel 1 (
    echo PySide6 est introuvable pour ce Python x64.
    echo Installation des dependances GUI...
    "%BUILD_PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 exit /b 1
)
"%BUILD_PYTHON%" -c "import qtawesome" 2>nul
if errorlevel 1 (
    "%BUILD_PYTHON%" -m pip install qtawesome
    if errorlevel 1 exit /b 1
)
"%BUILD_PYTHON%" -c "import PyInstaller" 2>nul
if errorlevel 1 (
    "%BUILD_PYTHON%" -m pip install pyinstaller
    if errorlevel 1 exit /b 1
)
exit /b 0

:construire
echo.
echo === Construction : %~2 ===
"%BUILD_PYTHON%" -m PyInstaller --clean --noconfirm %~1
if errorlevel 1 (
    echo.
    echo Echec du build de %~1.
    exit /b 1
)
exit /b 0

:bilan
echo.
echo === Termine : dist\%~1\%~1.exe ===
echo GUI : x64 / PySide6 / Qt 6
echo Tests : interpreteur externe configure dans l'application ^(x86 accepte^)
echo Distribuez le dossier dist\%~1 complet ^(zippe^), pas seulement l'exe.
exit /b 0

:usage
echo.
echo   build_exe.bat            construit l'interface PySide6 x64
echo   build_exe.bat run        construit puis lance l'interface PySide6 x64
echo.
echo Le runtime de tests 32 bits est independant de l'EXE x64.
echo.
exit /b 0
