@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   Pytest Runner - quick test of the current branch
echo ============================================================
echo.

where git >nul 2>nul
if not errorlevel 1 (
    for /f "delims=" %%B in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "BRANCH=%%B"
    if defined BRANCH (
        echo Branch: %BRANCH%
        echo Updating it with git pull --ff-only...
        git pull --ff-only
        if errorlevel 1 (
            echo.
            echo WARNING: git pull failed. Continuing with the local files.
        )
        echo.
    )
)

python --version >nul 2>nul
if errorlevel 1 (
    echo Python was not found on PATH.
    echo Install Python 3.9+ and relaunch this file.
    pause
    exit /b 1
)

python -c "import pytest" >nul 2>nul
if errorlevel 1 (
    echo Installing pytest for the demo workspace...
    python -m pip install pytest
    if errorlevel 1 (
        pause
        exit /b 1
    )
)

call build_exe.bat run
if errorlevel 1 (
    echo.
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo ------------------------------------------------------------
echo Demo workspace ready:
echo   %CD%\demo_workspace
echo.
echo In Pytest Runner, paste this path in the Workspace field,
echo click Load, select the tests and run them.
echo.
echo The demo intentionally contains PASS, FAIL, SKIP, XFAIL and
echo parametrized tests so the end-of-run behaviour is easy to check.
echo ------------------------------------------------------------
echo.
pause
