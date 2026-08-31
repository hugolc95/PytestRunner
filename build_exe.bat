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

call :verifier_python_x64
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

:verifier_python_x64
python -c "import struct,sys; sys.exit(0 if struct.calcsize('P')*8 == 64 else 1)" 2>nul
if errorlevel 1 (
    echo.
    echo ERREUR : le build PySide6 doit etre lance avec un Python 64 bits.
    echo Le Python 32 bits reste uniquement l'interpreteur de lancement des tests.
    echo.
    python -c "import struct; print('Python detecte :', struct.calcsize('P')*8, 'bits')"
    exit /b 1
)
exit /b 0

:verifier_dependances
python -c "import PySide6" 2>nul
if errorlevel 1 (
    echo PySide6 est introuvable pour ce Python x64.
    echo Installation des dependances GUI...
    python -m pip install -r requirements.txt
    if errorlevel 1 exit /b 1
)
python -c "import qtawesome" 2>nul
if errorlevel 1 (
    python -m pip install qtawesome
    if errorlevel 1 exit /b 1
)
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    python -m pip install pyinstaller
    if errorlevel 1 exit /b 1
)
exit /b 0

:construire
echo.
echo === Construction : %~2 ===
python -m PyInstaller --clean --noconfirm %~1
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
