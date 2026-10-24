@echo off
rem Mesh Engine: double-click this file to open the Mesh launcher,
rem where you create a new game or open one, and edit it in Mesh Studio.
setlocal
set "PYTHONPATH=%~dp0;%PYTHONPATH%"

rem Mesh needs Python 3.13, started through the Python launcher (py / pyw).
py -3.13 -c "import arcade" >nul 2>nul
if errorlevel 1 goto missing

rem pyw runs it without a console window.
where pyw >nul 2>nul
if errorlevel 1 (
    start "Mesh Engine" py -3.13 -m engine.launcher
) else (
    start "" pyw -3.13 -m engine.launcher
)
exit /b 0

:missing
echo.
echo Mesh Engine needs Python 3.13 with its packages installed.
echo Install Python 3.13 from https://www.python.org/downloads/ (with the "py" launcher),
echo then run:  py -3.13 -m pip install "arcade>=3,<4" "jsonschema>=4,<5" "pillow>=10,<12"
echo.
pause
exit /b 1
