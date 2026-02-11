@echo off
REM Quick wrapper to ingest style guides with venv detection

cd /d "%~dp0"

REM Find venv Python
if exist ".\venv\Scripts\python.exe" (
    set "VENV_PYTHON=.\venv\Scripts\python.exe"
) else if exist ".\.venv\Scripts\python.exe" (
    set "VENV_PYTHON=.\.venv\Scripts\python.exe"
) else (
    echo [WARNING] No venv found - using system Python
    set "VENV_PYTHON=python"
)

echo.
echo ============================================
echo   Style Guide Ingestion
echo ============================================
echo.
echo Using Python: %VENV_PYTHON%
echo Input directory: .\data\style
echo.

"%VENV_PYTHON%" scripts\ingest_style.py %*

echo.
pause
