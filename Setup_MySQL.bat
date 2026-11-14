@echo off
setlocal enabledelayedexpansion
title Setup MySQL for SOP Compliance System
cd /d "%~dp0"

echo ======================================================================
echo        MySQL One-Time Setup for SOP Compliance System
echo ======================================================================
echo.
echo This script sets up the MySQL database user for the SOP software.
echo Run this ONCE after installing MySQL on this machine.
echo.

:: 1. Auto-detect mysql.exe location if not in PATH
set "MYSQL_EXE=mysql"
where mysql >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    if exist "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe" (
        set "MYSQL_EXE=C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"
    ) else if exist "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" (
        set "MYSQL_EXE=C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe"
    ) else (
        for /d %%D in ("C:\Program Files\MySQL\MySQL Server*") do (
            if exist "%%D\bin\mysql.exe" set "MYSQL_EXE=%%D\bin\mysql.exe"
        )
    )
)

:: Verify MySQL is executable
"!MYSQL_EXE!" --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] MySQL is not found on this machine!
    echo.
    echo Please install MySQL first:
    if exist "mysql-installer.msi" (
        echo   - Double-click "mysql-installer.msi" in this folder.
    ) else (
        echo   - Use the mysql-installer.msi from the USB drive.
    )
    echo   - During setup, complete the installation and set a root password.
    echo   - After installation, run this script again.
    echo.
    pause
    exit /b 1
)

echo [OK] MySQL is installed: "!MYSQL_EXE!"
echo.
echo ======================================================================
echo  Creating SOP database user and granting permissions...
echo  You will be prompted for your MySQL ROOT password.
echo ======================================================================
echo.

:: Run MySQL commands to create the sop_user and database
"!MYSQL_EXE!" -u root -p -e "CREATE USER IF NOT EXISTS 'sop_user'@'localhost' IDENTIFIED BY 'Sop@1234'; CREATE DATABASE IF NOT EXISTS firewall_sop CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; GRANT ALL PRIVILEGES ON firewall_sop.* TO 'sop_user'@'localhost'; FLUSH PRIVILEGES;"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ======================================================================
    echo  [SUCCESS] MySQL setup complete!
    echo.
    echo  Database : firewall_sop
    echo  Username : sop_user
    echo  Password : Sop@1234
    echo.
    echo  The SOP software will automatically create the inspection_logs
    echo  table the first time it runs.
    echo.
    echo  You can now run: Run_App.bat
    echo ======================================================================
) else (
    echo.
    echo [ERROR] MySQL setup failed. Please check your root password and try again.
    echo.
    echo If you need to change the SOP user password, edit:
    echo   SOP_Compliance\config.py  -^>  DB_PASSWORD setting
)

echo.
pause
