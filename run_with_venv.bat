@echo off
REM Storyteller AI - Run Python scripts/commands with venv activation
REM
REM Usage: run_with_venv.bat <script or module> [args...]
REM
REM Examples:
REM   run_with_venv.bat scripts\ingest_style.py
REM   run_with_venv.bat -m storyteller dev
REM   run_with_venv.bat -m storyteller ingest --input ./data/lore
REM
REM NOTE: Do NOT include "python" - this script adds it automatically!
REM   WRONG: run_with_venv.bat python scripts\ingest_style.py
REM   RIGHT: run_with_venv.bat scripts\ingest_style.py

cd /d "%~dp0"

REM Find venv Python
if exist ".\venv\Scripts\python.exe" (
    set "VENV_PYTHON=.\venv\Scripts\python.exe"
    set "VENV_NAME=venv"
) else if exist ".\.venv\Scripts\python.exe" (
    set "VENV_PYTHON=.\.venv\Scripts\python.exe"
    set "VENV_NAME=.venv"
) else (
    echo.
    echo [ERROR] No virtual environment found!
    echo.
    echo Please create one first:
    echo   python -m venv venv
    echo   .\venv\Scripts\Activate.ps1
    echo   pip install -e .
    echo.
    echo Or run setup:
    echo   .\setup_dev.bat
    echo.
    pause
    exit /b 1
)

REM Check for common mistake
if "%~1"=="python" (
    echo.
    echo [ERROR] Do not include "python" in the command!
    echo.
    echo You ran: run_with_venv.bat python %2 %3 %4 ...
    echo Should be: run_with_venv.bat %2 %3 %4 ...
    echo.
    echo This script automatically uses the venv Python.
    echo.
    pause
    exit /b 1
)

echo [INFO] Using virtual environment: %VENV_NAME%
echo.

REM Run the command with venv Python
"%VENV_PYTHON%" %*
