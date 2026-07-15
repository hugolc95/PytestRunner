@echo off
cd /d "%~dp0.."

if not defined SMARTCARD_FRAMEWORK_PATH set "SMARTCARD_FRAMEWORK_PATH=C:\Dev\zz-id-smartcardframework-2026\zz-id-smartcardframework-2026"

if not exist "%SMARTCARD_FRAMEWORK_PATH%" (
    echo ATTENTION : SmartcardFramework introuvable a "%SMARTCARD_FRAMEWORK_PATH%".
    echo Definissez la variable d'environnement SMARTCARD_FRAMEWORK_PATH pour pointer vers le bon dossier.
    exit /b 0
)

if defined PYTHONPATH (
    set "PYTHONPATH=%SMARTCARD_FRAMEWORK_PATH%;%PYTHONPATH%"
) else (
    set "PYTHONPATH=%SMARTCARD_FRAMEWORK_PATH%"
)

echo SmartcardFramework ajoute au PYTHONPATH : %SMARTCARD_FRAMEWORK_PATH%
echo ^(rappel : les modules qui chargent les DLL natives 64 bits de SmartcardFramework
echo  ne fonctionneront pas sous ce Python 32 bits^)
exit /b 0
