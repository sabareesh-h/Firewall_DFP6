@echo off
setlocal
title SOP Compliance System
cd /d "%~dp0"

:: 1. Check virtual environment
if not exist "venv\Scripts\activate.bat" (
    echo ======================================================================
    echo [ERROR] Virtual environment not found!
    echo Please run "setup_environment.bat" first to install dependencies.
    echo ======================================================================
    pause
    exit /b 1
)

:: 2. Check model weights
if not exist "SOP_Compliance\models\best_v2.pt" (
    echo ======================================================================
    echo [WARNING] Model file "SOP_Compliance\models\best_v2.pt" was not found!
    echo AI models are not stored in Git. Please copy the "models" folder
    echo from the source computer into "SOP_Compliance\models".
    echo ======================================================================
    echo.
    echo Press any key to try running anyway, or close this window...
    pause >nul
)

:: 3. Launch browser in background after 3 seconds
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:8000"

:: 4. Start the application
echo ======================================================================
echo Starting SOP Compliance System...
echo Web UI will be available at: http://localhost:8000
echo Stop the server anytime by closing this window or pressing Ctrl+C.
echo ======================================================================
echo.

call venv\Scripts\activate.bat
cd SOP_Compliance
python app.py

pause
