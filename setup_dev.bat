@echo off
cd /d "%~dp0"
echo.
echo ============================================
echo   Storyteller AI — First-Time Setup
echo ============================================
echo.

:: ── Check Python ──────────────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found on PATH. Install Python 3.11+ from https://python.org
    pause
    exit /b 1
)

:: Check Python version
for /f "tokens=*" %%v in ('python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do set PY_VER=%%v
echo [INFO] Python version: %PY_VER%

:: ── Create venv if needed ─────────────────────────────────────────
if exist ".\venv\Scripts\python.exe" (
    echo [OK] Virtual environment exists (venv/)
) else if exist ".\.venv\Scripts\python.exe" (
    echo [OK] Virtual environment exists (.venv/)
) else (
    echo [INFO] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create venv.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
)

:: ── Find venv python ──────────────────────────────────────────────
if exist ".\venv\Scripts\python.exe" (
    set "PY=.\venv\Scripts\python.exe"
) else if exist ".\.venv\Scripts\python.exe" (
    set "PY=.\\.venv\\Scripts\\python.exe"
) else (
    echo [ERROR] venv not found after creation.
    pause
    exit /b 1
)

:: ── Install requirements ──────────────────────────────────────────
echo.
echo [INFO] Installing Python requirements...
"%PY%" -m pip install --upgrade pip >nul 2>&1
"%PY%" -m pip install -e ".[dev]"
if errorlevel 1 (
    echo [WARNING] Some packages may have failed to install.
) else (
    echo [OK] Requirements installed.
)

:: ── Create data directories ───────────────────────────────────────
echo.
if not exist ".\data" mkdir ".\data"
if not exist ".\data\lancedb" mkdir ".\data\lancedb"
if not exist ".\data\lore" mkdir ".\data\lore"
if not exist ".\data\style" mkdir ".\data\style"
if not exist ".\data\manifests" mkdir ".\data\manifests"
echo [OK] Data directories ready.

:: ── Create .env if missing ────────────────────────────────────────
if not exist ".\.env" (
    if exist ".\.env.example" (
        copy ".\.env.example" ".\.env" >nul
        echo [OK] Created .env from .env.example (edit as needed)
    ) else (
        echo [INFO] No .env.example found; skipping .env creation.
    )
) else (
    echo [OK] .env file exists.
)

:: ── Check Ollama ──────────────────────────────────────────────────
echo.
where ollama >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Ollama not found on PATH.
    echo   Install from: https://ollama.com
    echo   Then run: ollama pull qwen3:8b
) else (
    echo [OK] Ollama found on PATH.
    echo.
    echo   Suggested models to pull (based on config defaults):
    echo     ollama pull qwen3:8b        (all agent roles)
    echo     ollama pull nomic-embed-text (embeddings, optional)
    echo.
    echo   Embedding model (sentence-transformers/all-MiniLM-L6-v2) downloads
    echo   automatically on first ingestion/retrieval (~80MB).
)

:: ── Summary ───────────────────────────────────────────────────────
echo.
echo ============================================
echo   Setup complete.
echo ============================================
echo.
echo   Next steps:
echo     1. Pull Ollama models:  ollama pull qwen3:8b
echo     2. (Optional) Ingest lore:
echo        %PY% -m ingestion.ingest_lore --input ./data/lore --db ./data/lancedb
echo     3. Start everything:    .\start_dev.bat
echo.
pause
