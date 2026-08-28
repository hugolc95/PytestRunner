@echo off
REM Construit Pytest Runner en application Windows autonome.
REM
REM   build_exe.bat            interface courante -> dist\PytestRunner
REM   build_exe.bat run        construit puis lance la derniere version
REM   build_exe.bat classic    ancienne interface -> dist\PytestRunnerClassic
REM   build_exe.bat both       les deux
REM   build_exe.bat help       ce message
REM
REM L'exe produit ne contient QUE l'interface : pytest et les dependances des
REM tests restent du cote de l'interpreteur configure dans l'application.

setlocal
cd /d "%~dp0"

set "CIBLE=%~1"
if "%CIBLE%"=="" set "CIBLE=new"

if /i "%CIBLE%"=="help"    goto :usage
if /i "%CIBLE%"=="/?"      goto :usage
if /i "%CIBLE%"=="-h"      goto :usage
if /i "%CIBLE%"=="--help"  goto :usage

call :verifier_dependances
if errorlevel 1 exit /b 1

if /i "%CIBLE%"=="new"     goto :build_new
if /i "%CIBLE%"=="run"     goto :build_and_run
if /i "%CIBLE%"=="latest"  goto :build_and_run
if /i "%CIBLE%"=="classic" goto :build_classic
if /i "%CIBLE%"=="old"     goto :build_classic
if /i "%CIBLE%"=="v1"      goto :build_classic
if /i "%CIBLE%"=="both"    goto :build_both
if /i "%CIBLE%"=="all"     goto :build_both

echo Cible inconnue : %CIBLE%
echo.
goto :usage

:build_new
call :construire PytestRunner.spec "interface courante"
if errorlevel 1 exit /b 1
call :bilan PytestRunner
exit /b 0

:build_and_run
call :construire PytestRunner.spec "interface courante"
if errorlevel 1 exit /b 1
call :bilan PytestRunner
echo.
echo Lancement de la version qui vient d'etre construite...
start "Pytest Runner" "%CD%\dist\PytestRunner\PytestRunner.exe"
exit /b 0

:build_classic
call :construire PytestRunnerClassic.spec "ancienne interface"
if errorlevel 1 exit /b 1
call :bilan PytestRunnerClassic
exit /b 0

:build_both
call :construire PytestRunner.spec "interface courante"
if errorlevel 1 exit /b 1
call :construire PytestRunnerClassic.spec "ancienne interface"
if errorlevel 1 exit /b 1
call :bilan PytestRunner
call :bilan PytestRunnerClassic
exit /b 0

:verifier_dependances
python -c "import PyQt5" 2>nul
if errorlevel 1 (
    echo PyQt5 est introuvable pour ce Python.
    echo Installation des dependances de build...
    python -m pip install PyQt5 PyYAML qtawesome pyinstaller
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
echo Distribuez le dossier dist\%~1 complet ^(zippe^), pas seulement l'exe.
exit /b 0

:usage
echo.
echo   build_exe.bat            construit l'interface courante
echo   build_exe.bat run        construit puis lance l'interface courante
echo   build_exe.bat classic    construit l'ancienne interface
echo   build_exe.bat both       construit les deux
echo.
echo Les deux dossiers cohabitent dans dist\ : l'un n'ecrase pas l'autre.
echo.
exit /b 0
