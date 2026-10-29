@echo off
setlocal
title Offline Setup - SOP Compliance System
cd /d "%~dp0"

echo ======================================================================
echo       SOP Compliance System - Offline Setup (No Internet Needed)
echo ======================================================================
echo.

:: 1. Verify Python is installed
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python 3.11 is not detected on this machine!
    echo.
    echo Please install Python 3.11 from the USB installer:
    echo   - Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: 2. Check if wheels folder exists
if not exist "wheels" (
    echo [ERROR] "wheels" folder not found!
    echo The offline dependency packages (.whl files) must be inside the "wheels" folder.
    pause
    exit /b 1
)

:: 3. Create virtual environment
if not exist "venv" (
    echo [1/2] Creating virtual environment (venv)...
    python -m venv venv
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [1/2] Virtual environment already exists.
)

:: 4. Install packages completely offline from wheels folder
echo.
echo [2/2] Installing dependencies offline from local wheels...
call venv\Scripts\activate.bat
pip install --no-index --find-links=wheels -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [WARNING] Some dependencies could not be installed from "wheels".
    echo Trying to install all .whl files found in wheels folder...
    pip install --no-index --find-links=wheels wheels\*.whl
)

echo.
echo ======================================================================
echo  Offline Setup Completed!
echo.
echo  You can now start the software anytime using "Run_App.bat".
echo ======================================================================
pause
