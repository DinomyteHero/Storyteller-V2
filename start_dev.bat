@echo off
cd /d "%~dp0"

echo Starting Storyteller AI development stack (backend + SvelteKit UI)...

if exist ".\\venv\\Scripts\\python.exe" (
  set "PY=.\\venv\\Scripts\\python.exe"
) else if exist ".\\.venv\\Scripts\\python.exe" (
  set "PY=.\\.venv\\Scripts\\python.exe"
) else (
  set "PY=python"
)

"%PY%" -m storyteller dev %*
