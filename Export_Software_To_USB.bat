@echo off
setlocal enabledelayedexpansion
title Sync and Export Software to USB
cd /d "%~dp0"

echo ======================================================================
echo           Export Standalone Software Package to USB Drive
echo ======================================================================
echo.

set /p usb_drive="Enter your USB Drive letter (e.g. E: or F:): "
if "%usb_drive%"=="" (
    echo [ERROR] No drive letter entered.
    pause
    exit /b 1
)

set usb_drive=%usb_drive:~0,1%:
if not exist "%usb_drive%\" (
    echo [ERROR] Drive %usb_drive% was not found! Please check the drive letter.
    pause
    exit /b 1
)

set "dest_folder=%usb_drive%\Firewall_SOP_Software"
echo.
echo Target folder on USB: %dest_folder%
echo.

echo ----------------------------------------------------------------------
echo Copying Software folder to USB...
echo ----------------------------------------------------------------------
robocopy "Software" "%dest_folder%" /E /XD __pycache__ .pytest_cache logs

if %ERRORLEVEL% GTR 7 (
    echo [ERROR] Failed copying files to USB.
    pause
    exit /b 1
)

echo.
echo ======================================================================
echo  USB Export Complete!
echo.
echo  When you plug this USB into the offline IPC:
echo    1. Open folder: Firewall_SOP_Software
echo    2. (One-time) Double-click: mysql-installer.msi  (Set root password)
echo    3. (One-time) Double-click: Setup_MySQL.bat      (Creates sop_user)
echo    4. Double-click: Run_Software.bat (or Firewall_SOP.exe)
echo    5. View database anytime with: View_Database.bat
echo ======================================================================
echo.
pause
