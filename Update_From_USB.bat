@echo off
setlocal
title Update SOP System from USB
cd /d "%~dp0"

echo ======================================================================
echo           Update SOP Compliance System from USB Drive
echo ======================================================================
echo.

set /p usb_drive="Enter your USB Drive letter (e.g. E: or F:): "
if "%usb_drive%"=="" (
    echo [ERROR] No drive letter entered.
    pause
    exit /b 1
)

set usb_drive=%usb_drive:~0,1%:
set "src_folder=%usb_drive%\Firewall_SOP_Offline"

if not exist "%src_folder%\SOP_Compliance" (
    echo [ERROR] Could not find "%src_folder%\SOP_Compliance" on drive %usb_drive%!
    echo Please make sure the USB is plugged in and contains the exported files.
    pause
    exit /b 1
)

echo.
echo [1/2] Updating application code and models from USB...
robocopy "%src_folder%\SOP_Compliance" "SOP_Compliance" /E /XD logs __pycache__
if %ERRORLEVEL% GTR 7 (
    echo [ERROR] Failed to copy updated files from USB.
    pause
    exit /b 1
)

robocopy "%src_folder%" "." requirements.txt Run_App.bat /XO

:: Check if new wheel packages were provided in the USB
if exist "%src_folder%\wheels" (
    if exist "venv\Scripts\python.exe" (
        echo.
        echo [2/2] Checking for offline package updates...
        venv\Scripts\pip install --no-index --find-links="%src_folder%\wheels" -r requirements.txt --quiet
    )
)

echo.
echo ======================================================================
echo  Update Complete!
echo  The offline machine is now updated to the latest version.
echo  You can now start the software with "Run_App.bat".
echo ======================================================================
pause
