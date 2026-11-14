@echo off
setlocal enabledelayedexpansion
title View MySQL Inspection Database
cd /d "%~dp0"

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

echo ======================================================================
echo          Firewall SOP - MySQL Inspection Logs Viewer
echo ======================================================================
echo.

"!MYSQL_EXE!" -u sop_user -pSop@1234 -e "USE firewall_sop; SELECT id, part_id, timestamp, compound_status, cycle_time, synced_to_it FROM inspection_logs ORDER BY id DESC LIMIT 20;"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [NOTE] Table might be empty or not yet created.
    echo Let's check available tables:
    "!MYSQL_EXE!" -u sop_user -pSop@1234 -e "SHOW DATABASES; USE firewall_sop; SHOW TABLES;"
)

echo.
echo ======================================================================
echo  compound_status: 1 = ALL GAUGES OK (PASS)  ^|  0 = INCOMPLETE / NG
echo ======================================================================
echo.
pause
