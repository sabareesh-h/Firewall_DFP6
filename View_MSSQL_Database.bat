@echo off
title Firewall SOP - MSSQL Inspection Database Viewer
cd /d "%~dp0"

if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" "%~dp0view_database.py"
) else if exist "Software\python\python.exe" (
    "Software\python\python.exe" "%~dp0view_database.py"
) else (
    python "%~dp0view_database.py"
)
