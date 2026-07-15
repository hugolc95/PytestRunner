@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo === Installations Python detectees ===
py -0p 2>nul
echo.
echo === Verification Python 3.13 x86 ===
py -3.13-32 -c "import sys,struct; print(sys.executable); print(sys.version); print('Architecture:',struct.calcsize('P')*8,'bits')" 2>nul
if errorlevel 1 echo Python 3.13 32 bits non detecte par le launcher py.
echo.
echo === Roues principales ===
dir /b wheels\*win32.whl 2>nul
pause
