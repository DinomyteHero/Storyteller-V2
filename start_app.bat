@echo off
setlocal
cd /d "%~dp0"

echo Starting Storyteller wrapper...

if exist ".\venv\Scripts\python.exe" (
  set "PY=.\venv\Scripts\python.exe"
) else if exist ".\.venv\Scripts\python.exe" (
  set "PY=.\.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

echo Using Python: %PY%
"%PY%" run_app.py --dev %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo Wrapper exited with code %RC%.
)

endlocal & exit /b %RC%
