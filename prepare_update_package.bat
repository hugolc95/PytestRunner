@echo off
setlocal
cd /d "%~dp0"

if not exist "dist\PytestRunner\PytestRunner.exe" (
    echo PytestRunner has not been built yet. Building it now...
    call build_exe.bat
    if errorlevel 1 exit /b 1
)

python tools\prepare_update_package.py
if errorlevel 1 exit /b 1

echo.
echo Copy the ZIP and latest.json from release\ to the corporate update share.
exit /b 0
