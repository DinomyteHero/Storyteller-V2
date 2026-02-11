@echo off
cd /d "%~dp0"
echo Starting Storyteller AI UI (legacy Python UI, venv)...
echo.
if exist ".\\venv\\Scripts\\python.exe" (
  set "PY=.\\venv\\Scripts\\python.exe"
) else if exist ".\\.venv\\Scripts\\python.exe" (
  set "PY=.\\.venv\\Scripts\\python.exe"
) else (
  echo ERROR: No venv found. Create one with: python -m venv venv ^&^& .\\venv\\Scripts\\Activate.ps1 ^&^& pip install -r requirements.txt
  pause
  exit /b 1
)

set "PYTHONPATH=%cd%"
if not defined STORYTELLER_API_URL set "STORYTELLER_API_URL=http://localhost:8000"

echo Using %PY%
echo STORYTELLER_API_URL=%STORYTELLER_API_URL%
echo.
"%PY%" -c "import streamlit" >nul 2>&1
if errorlevel 1 (
  echo ERROR: Legacy UI dependency is not installed in this venv.
  echo Run: "%PY%" -m pip install streamlit
  echo.
  pause
  exit /b 1
)
"%PY%" -m streamlit run streamlit_app.py
pause
