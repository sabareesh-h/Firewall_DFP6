@echo off
setlocal
title Update SOP Compliance System
cd /d "%~dp0"

echo ======================================================================
echo          SOP Compliance System - Updating to Latest Version
echo ======================================================================
echo.

:: Check Git installation
git --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Git is not installed or not in PATH!
    pause
    exit /b 1
)

:: Discard local changes to settings.json or auto-generated cache so pull succeeds cleanly
echo [1/3] Preparing workspace for update...
git checkout -- SOP_Compliance/settings.json 2>nul

:: Pull latest code from GitHub repository
echo.
echo [2/3] Fetching and pulling latest updates from GitHub...
git pull origin main
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ======================================================================
    echo [ERROR] Update failed!
    echo Please check your internet connection and Git permissions.
    echo ======================================================================
    pause
    exit /b %ERRORLEVEL%
)

:: Update dependencies if requirements.txt changed
if exist "venv\Scripts\python.exe" (
    echo.
    echo [3/3] Checking and updating Python dependencies...
    venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
)

echo.
echo ======================================================================
echo  Update Successful! The software is now on the latest version.
echo  You can now start the application with "Run_App.bat".
echo ======================================================================
echo.
pause
