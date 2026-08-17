@echo off
REM Construit l'interface Pytest Runner en application Windows autonome.
REM
REM L'exe produit ne contient QUE l'interface : pytest et les dependances des
REM tests restent du cote de l'interpreteur configure dans l'application
REM (menu Configuration > Interpreteur Python des tests...).
REM
REM Le Python utilise ici n'a donc aucun rapport avec celui des tests : n'importe
REM quel Python 3.9+ avec PyQt5 fait l'affaire, 32 ou 64 bits.

cd /d "%~dp0"

python -c "import PyQt5" 2>nul
if errorlevel 1 (
    echo PyQt5 est introuvable pour ce Python.
    echo Installez les dependances de build avec :
    echo     python -m pip install PyQt5 PyYAML qtawesome pyinstaller
    exit /b 1
)

python -c "import qtawesome" 2>nul
if errorlevel 1 (
    echo qtawesome est introuvable : sans lui l'exe se lance mais toutes
    echo les icones sont vides. Installation...
    python -m pip install qtawesome
    if errorlevel 1 exit /b 1
)

python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller est introuvable. Installation...
    python -m pip install pyinstaller
    if errorlevel 1 exit /b 1
)

echo.
echo === Construction de PytestRunner.exe ===
python -m PyInstaller --clean --noconfirm PytestRunner.spec
if errorlevel 1 (
    echo.
    echo Echec du build.
    exit /b 1
)

echo.
echo === Termine ===
echo Application : dist\PytestRunner\PytestRunner.exe
echo Distribuez le dossier dist\PytestRunner complet ^(zippe^), pas seulement l'exe.
exit /b 0
