param(
    [switch]$BackendOnly,
    [switch]$UiOnly,
    [switch]$NoOllama,
    [int]$BackendPort = 8000,
    [int]$UiPort = 8501,
    [string]$OllamaBaseUrl = "http://localhost:11434",
    [string]$VectorDbPath = "",
    [string]$DbPath = ""
)

$ErrorActionPreference = "Stop"

# ── Helpers ──────────────────────────────────────────────────────────

function Import-DotEnv {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return }
    Get-Content -LiteralPath $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line) { return }
        if ($line.StartsWith("#")) { return }
        $idx = $line.IndexOf("=")
        if ($idx -lt 1) { return }
        $key = $line.Substring(0, $idx).Trim()
        $val = $line.Substring($idx + 1).Trim()
        if ($key) { Set-Item -Path ("Env:" + $key) -Value $val }
    }
}

function Get-VenvPython {
    param([string]$Root)
    $candidates = @(
        (Join-Path $Root "venv\Scripts\python.exe"),
        (Join-Path $Root ".venv\Scripts\python.exe")
    )
    foreach ($p in $candidates) {
        if (Test-Path -LiteralPath $p) { return $p }
    }
    return $null
}

function Test-OllamaRunning {
    param([string]$BaseUrl)
    try {
        Invoke-RestMethod -Uri ($BaseUrl.TrimEnd("/") + "/api/tags") -Method Get -TimeoutSec 2 | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Test-PortInUse {
    param([int]$Port)
    try {
        $conn = [System.Net.Sockets.TcpClient]::new()
        $conn.Connect("127.0.0.1", $Port)
        $conn.Close()
        return $true
    } catch {
        return $false
    }
}

function Read-LastIngestVectorDbPath {
    param([string]$Root)
    $p = Join-Path $Root "data\last_ingest.json"
    if (-not (Test-Path -LiteralPath $p)) { return "" }
    try {
        $j = Get-Content -LiteralPath $p -Raw | ConvertFrom-Json
        if ($j -and $j.vectordb_path) { return [string]$j.vectordb_path }
    } catch {
        return ""
    }
    return ""
}

# ── Setup ────────────────────────────────────────────────────────────

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $root
Import-DotEnv -Path (Join-Path $root ".env")

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Storyteller AI — Dev Environment" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ── Python / venv check ──────────────────────────────────────────────

$python = Get-VenvPython -Root $root
if (-not $python) {
    Write-Host "[ERROR] No venv found (checked venv/ and .venv/)." -ForegroundColor Red
    Write-Host "  Run:  python -m venv venv" -ForegroundColor Yellow
    Write-Host "  Then: .\venv\Scripts\Activate.ps1" -ForegroundColor Yellow
    Write-Host "  Then: pip install -r requirements.txt" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Or run: .\setup_dev.bat  (does all of the above)" -ForegroundColor Green
    exit 1
}

# Check Python version
$pyVersion = & $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
if ($pyVersion) {
    $major, $minor = $pyVersion.Split(".")
    if ([int]$major -lt 3 -or ([int]$major -eq 3 -and [int]$minor -lt 11)) {
        Write-Host "[WARNING] Python $pyVersion detected. Python 3.11+ is required." -ForegroundColor Yellow
    } else {
        Write-Host "[OK] Python $pyVersion" -ForegroundColor Green
    }
} else {
    Write-Host "[WARNING] Could not determine Python version." -ForegroundColor Yellow
}

# Quick requirements check
$reqCheck = & $python -c "import streamlit, fastapi, lancedb" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARNING] Some required packages are missing. Run: pip install -r requirements.txt" -ForegroundColor Yellow
}

# ── Resolve paths ────────────────────────────────────────────────────

if (-not $DbPath) {
    $DbPath = $env:STORYTELLER_DB_PATH
}
if (-not $DbPath) {
    $DbPath = (Join-Path $root "data\storyteller.db")
}

if (-not $VectorDbPath) {
    $VectorDbPath = $env:VECTORDB_PATH
}
if (-not $VectorDbPath) {
    $VectorDbPath = Read-LastIngestVectorDbPath -Root $root
}
if (-not $VectorDbPath) {
    $preferred = (Join-Path $root "data\lancedb")
    $legacy = (Join-Path $root "lancedb")
    $VectorDbPath = (if ((Test-Path -LiteralPath $preferred) -or -not (Test-Path -LiteralPath $legacy)) { $preferred } else { $legacy })
}

# Ensure data directories exist
$dataDir = Join-Path $root "data"
if (-not (Test-Path -LiteralPath $dataDir)) {
    New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
    Write-Host "[OK] Created data/ directory" -ForegroundColor Green
}

$env:PYTHONPATH = $root
$env:STORYTELLER_DB_PATH = $DbPath
$env:VECTORDB_PATH = $VectorDbPath
$env:STORYTELLER_API_URL = ("http://localhost:{0}" -f $BackendPort)

# ── Port checks ──────────────────────────────────────────────────────

if (-not $UiOnly) {
    if (Test-PortInUse -Port $BackendPort) {
        Write-Host "[WARNING] Port $BackendPort is already in use. Backend may fail to start." -ForegroundColor Yellow
        Write-Host "  Fix: close the process using port $BackendPort, or use -BackendPort <other>" -ForegroundColor Yellow
    }
}
if (-not $BackendOnly) {
    if (Test-PortInUse -Port $UiPort) {
        Write-Host "[INFO] Port $UiPort is in use. The legacy Python UI may auto-pick the next available port." -ForegroundColor Cyan
    }
}

# ── Ollama check ─────────────────────────────────────────────────────

$startedOllama = $false
$ollamaProc = $null
$backendProc = $null
$uiProc = $null

try {
    if (-not $NoOllama) {
        if (-not (Test-OllamaRunning -BaseUrl $OllamaBaseUrl)) {
            $ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
            if ($ollamaCmd) {
                Write-Host "[INFO] Starting Ollama (will be stopped on exit)..." -ForegroundColor Cyan
                $ollamaProc = Start-Process -FilePath $ollamaCmd.Source -ArgumentList @("serve") -PassThru
                $startedOllama = $true
                for ($i = 0; $i -lt 40; $i++) {
                    Start-Sleep -Milliseconds 250
                    if (Test-OllamaRunning -BaseUrl $OllamaBaseUrl) { break }
                }
                if (Test-OllamaRunning -BaseUrl $OllamaBaseUrl) {
                    Write-Host "[OK] Ollama is running" -ForegroundColor Green
                } else {
                    Write-Host "[WARNING] Ollama started but not responding yet" -ForegroundColor Yellow
                }
            } else {
                Write-Host "[WARNING] Ollama not found on PATH." -ForegroundColor Yellow
                Write-Host "  Install from: https://ollama.com" -ForegroundColor Yellow
                Write-Host "  Then run: ollama pull qwen3:8b" -ForegroundColor Yellow
            }
        } else {
            Write-Host "[OK] Ollama is running" -ForegroundColor Green
        }
    }

    # ── Print environment summary ────────────────────────────────────

    Write-Host ""
    Write-Host "  STORYTELLER_DB_PATH  = $DbPath" -ForegroundColor DarkGray
    Write-Host "  VECTORDB_PATH        = $VectorDbPath" -ForegroundColor DarkGray
    Write-Host "  STORYTELLER_API_URL  = $($env:STORYTELLER_API_URL)" -ForegroundColor DarkGray
    Write-Host "  Backend port         = $BackendPort" -ForegroundColor DarkGray
    Write-Host ""

    # ── Start backend ────────────────────────────────────────────────

    if (-not $UiOnly) {
        Write-Host "[INFO] Starting backend..." -ForegroundColor Cyan
        $backendArgs = @(
            "-m", "uvicorn",
            "backend.main:app",
            "--reload",
            "--host", "0.0.0.0",
            "--port", "$BackendPort"
        )
        $backendProc = Start-Process -FilePath $python -ArgumentList $backendArgs -PassThru
        Write-Host "[OK] Backend PID: $($backendProc.Id) -> http://localhost:$BackendPort" -ForegroundColor Green
    }

    # ── Start UI ─────────────────────────────────────────────────────

    if (-not $BackendOnly) {
        Write-Host "[INFO] Starting legacy Python UI..." -ForegroundColor Cyan
        $uiArgs = @("-m", "streamlit", "run", "streamlit_app.py", "--server.port", "$UiPort")
        $uiProc = Start-Process -FilePath $python -ArgumentList $uiArgs -PassThru
        Write-Host "[OK] UI PID: $($uiProc.Id) -> http://localhost:$UiPort" -ForegroundColor Green
    }

    Write-Host ""
    Write-Host "Press Ctrl+C to stop everything." -ForegroundColor Yellow
    Write-Host ""

    while ($true) {
        if ($backendProc -and $backendProc.HasExited) { break }
        if ($uiProc -and $uiProc.HasExited) { break }
        Start-Sleep -Seconds 1
    }
}
finally {
    Write-Host ""
    Write-Host "Shutting down..." -ForegroundColor Cyan
    if ($uiProc -and -not $uiProc.HasExited) {
        Stop-Process -Id $uiProc.Id -ErrorAction SilentlyContinue
    }
    if ($backendProc -and -not $backendProc.HasExited) {
        Stop-Process -Id $backendProc.Id -ErrorAction SilentlyContinue
    }
    if ($startedOllama -and $ollamaProc -and -not $ollamaProc.HasExited) {
        Stop-Process -Id $ollamaProc.Id -ErrorAction SilentlyContinue
    }
    Write-Host "Done." -ForegroundColor Green
}
