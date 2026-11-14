@echo off
setlocal enabledelayedexpansion
title Export SOP System to USB Drive
cd /d "%~dp0"

echo ======================================================================
echo            Export SOP System / Updates to USB Drive
echo ======================================================================
echo.

set /p usb_drive="Enter your USB Drive letter (e.g. E: or F:): "
if "%usb_drive%"=="" (
    echo [ERROR] No drive letter entered.
    pause
    exit /b 1
)

:: Ensure drive letter format (e.g. E:)
set usb_drive=%usb_drive:~0,1%:
if not exist "%usb_drive%\" (
    echo [ERROR] Drive %usb_drive% was not found! Please check the drive letter.
    pause
    exit /b 1
)

set "dest_folder=%usb_drive%\Firewall_SOP_Offline"
echo.
echo Target folder on USB: %dest_folder%
echo.

:: Ask what to export
echo Select export type:
echo [1] FULL EXPORT (First-time setup: Copies code, models, batch files, and downloads wheels)
echo [2] CODE UPDATE ONLY (Fast: Copies updated code/models only, without redownloading wheels)
set /p mode="Choose option (1 or 2, default 2): "

if "%mode%"=="1" goto full_export
goto code_only

:full_export
echo.
echo ----------------------------------------------------------------------
echo [1/3] Copying application and models to USB...
echo ----------------------------------------------------------------------
robocopy "." "%dest_folder%" /E /XD venv .git __pycache__ .pytest_cache frames frames_2 Hand_frames r_files "Part with Hand Anno" /XF *.mp4 *.wmv *.zip *.xlsx *.pdf
if %ERRORLEVEL% GTR 7 (
    echo [ERROR] Failed copying project files to USB.
    pause
    exit /b 1
)

echo.
echo ----------------------------------------------------------------------
echo [2/3] Downloading offline Python wheel packages into USB\wheels...
echo (This may take a few minutes for PyTorch and YOLO packages)
echo ----------------------------------------------------------------------
if not exist "%dest_folder%\wheels" mkdir "%dest_folder%\wheels"
pip download -r requirements.txt -d "%dest_folder%\wheels"
pip download torch torchvision --index-url https://download.pytorch.org/whl/cu128 -d "%dest_folder%\wheels"

echo.
echo ----------------------------------------------------------------------
echo [2b/3] Copying MySQL Installer for offline IPC setup...
echo (Download mysql-installer-community from mysql.com and place it in
echo  this folder as "mysql-installer.msi" before running this export)
echo ----------------------------------------------------------------------
if exist "mysql-installer.msi" (
    copy "mysql-installer.msi" "%dest_folder%\mysql-installer.msi"
    echo   MySQL installer copied to USB.
) else (
    echo   [WARNING] mysql-installer.msi NOT found in this folder.
    echo   Download MySQL Installer from: https://dev.mysql.com/downloads/installer/
    echo   Save it as "mysql-installer.msi" next to Export_To_USB.bat, then re-run.
    echo   The SOP software will still work without MySQL - DB logging will be disabled.
)

echo.
echo ----------------------------------------------------------------------
echo [3/3] Full export completed successfully!
echo ----------------------------------------------------------------------
goto finish

:code_only
echo.
echo ----------------------------------------------------------------------
echo Copying updated code and models to USB...
echo ----------------------------------------------------------------------
robocopy "SOP_Compliance" "%dest_folder%\SOP_Compliance" /E /XD __pycache__ .pytest_cache logs
robocopy "." "%dest_folder%" requirements.txt Run_App.bat Setup_Offline.bat Update_From_USB.bat Setup_MySQL.bat
if %ERRORLEVEL% GTR 7 (
    echo [ERROR] Failed copying update files to USB.
    pause
    exit /b 1
)
echo Update files synced to USB!

:finish
echo.
echo ======================================================================
echo  USB is ready! 
echo  Safely eject the USB drive and plug it into the offline machine.
echo.
echo  On the IPC (one-time setup):
echo    1. Run mysql-installer.msi  (if not already installed)
echo    2. Run Setup_Offline.bat    (installs Python packages incl. pymysql)
echo    3. Run Run_App.bat          (app creates the DB table automatically)
echo ======================================================================
pause
