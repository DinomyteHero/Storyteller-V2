@echo off
cd /d "%~dp0"
echo Starting Storyteller AI Backend (venv)...
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
if not defined VECTORDB_PATH set "VECTORDB_PATH=.\data\lancedb"
if not defined STORYTELLER_DB_PATH set "STORYTELLER_DB_PATH=.\data\storyteller.db"

echo Using %PY%
echo VECTORDB_PATH=%VECTORDB_PATH%
echo STORYTELLER_DB_PATH=%STORYTELLER_DB_PATH%
echo.
echo Note: Ollama must be running on http://localhost:11434 (or override via STORYTELLER_*_BASE_URL).
echo.
"%PY%" -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
pause
