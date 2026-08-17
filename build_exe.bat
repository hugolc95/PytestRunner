@echo off
REM Construit Pytest Runner en application Windows autonome.
REM
REM   build_exe.bat            l'interface courante        -> dist\PytestRunner
REM   build_exe.bat classic    l'ancienne interface        -> dist\PytestRunnerClassic
REM   build_exe.bat both       les deux
REM   build_exe.bat help       ce message
REM
REM L'exe produit ne contient QUE l'interface : pytest et les dependances des
REM tests restent du cote de l'interpreteur configure dans l'application.
REM
REM Le Python utilise ici n'a donc aucun rapport avec celui des tests :
REM n'importe quel Python 3.9+ avec PyQt5 fait l'affaire, 32 ou 64 bits.

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


REM --------------------------------------------------------------------------
:verifier_dependances
python -c "import PyQt5" 2>nul
if errorlevel 1 (
    echo PyQt5 est introuvable pour ce Python.
    echo Installez les dependances de build avec :
    echo     python -m pip install PyQt5 PyYAML qtawesome pyinstaller
    exit /b 1
)

REM qtawesome ne sert qu'a l'interface courante, mais l'installer dans tous les
REM cas evite un build silencieusement sans icones si l'on change de cible.
python -c "import qtawesome" 2>nul
if errorlevel 1 (
    echo qtawesome est introuvable : sans lui, l'interface courante se lance
    echo mais toutes ses icones sont vides. Installation...
    python -m pip install qtawesome
    if errorlevel 1 exit /b 1
)

python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller est introuvable. Installation...
    python -m pip install pyinstaller
    if errorlevel 1 exit /b 1
)
exit /b 0


REM --------------------------------------------------------------------------
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


REM --------------------------------------------------------------------------
:bilan
echo.
echo === Termine : dist\%~1\%~1.exe ===
echo Distribuez le dossier dist\%~1 complet ^(zippe^), pas seulement l'exe.
exit /b 0


REM --------------------------------------------------------------------------
:usage
echo.
echo   build_exe.bat            construit l'interface courante
echo   build_exe.bat classic    construit l'ancienne interface
echo   build_exe.bat both       construit les deux
echo.
echo Les deux dossiers cohabitent dans dist\ : l'un n'ecrase pas l'autre.
echo.
exit /b 0
