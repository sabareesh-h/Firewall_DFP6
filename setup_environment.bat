@echo off
setlocal
title Setup SOP Compliance Environment
cd /d "%~dp0"

echo ======================================================================
echo          SOP Compliance System - Initial Environment Setup
echo ======================================================================
echo.

:: 1. Check Python installation
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not added to PATH.
    echo Please install Python 3.11 from python.org and check "Add Python to PATH".
    pause
    exit /b 1
)

:: 2. Create virtual environment if it doesn't exist
if not exist "venv" (
    echo [1/3] Creating virtual environment (venv)...
    python -m venv venv
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [1/3] Virtual environment already exists.
)

:: 3. Upgrade pip and install PyTorch
echo.
echo [2/3] Installing PyTorch and dependencies...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip

echo.
echo Do you want to install PyTorch with NVIDIA GPU (CUDA 12.8) support?
echo [Y] Yes - Machine has an NVIDIA GPU (Recommended for shop floor / fast inference)
echo [N] No  - CPU only (Slower inference, for test laptops without dedicated GPU)
set /p gpu_choice="Select (Y/N, default Y): "

if /i "%gpu_choice%"=="N" (
    echo Installing PyTorch CPU version...
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
) else (
    echo Installing PyTorch with CUDA 12.8 support...
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
)

:: 4. Install remaining requirements
echo.
echo [3/3] Installing application dependencies from requirements.txt...
pip install -r requirements.txt

echo.
echo ======================================================================
echo  Setup Completed Successfully!
echo.
echo  IMPORTANT REMINDER:
echo  Make sure you copy the "SOP_Compliance\models\" folder into this
echo  installation directory, because .pt model weights are not in Git.
echo.
echo  You can now start the software anytime using "Run_App.bat"
echo ======================================================================
pause
