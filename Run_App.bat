@echo off
setlocal
title SOP Compliance System
cd /d "%~dp0"

:: 0. Auto-install Visual C++ Runtime if missing on a fresh PC
if not exist "%SystemRoot%\System32\vcruntime140_1.dll" (
    if exist "%~dp0vc_redist.x64.exe" (
        echo ======================================================================
        echo  First-Time Setup: Installing Microsoft Visual C++ Runtime...
        echo ======================================================================
        start /wait "" "%~dp0vc_redist.x64.exe" /install /passive /norestart
        echo  Visual C++ Runtime installed successfully.
        echo ======================================================================
        echo.
    )
)

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
