Param(
  [string]$PythonBin = "python"
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "== Storyteller bootstrap (Windows PowerShell) =="
& $PythonBin -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11+ is required'; print('Python OK:', sys.version.split()[0])"

if (!(Test-Path .venv)) {
  & $PythonBin -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e .

if (!(Test-Path .env) -and (Test-Path .env.production.example)) {
  Copy-Item .env.production.example .env
}

& .\.venv\Scripts\python.exe run_app.py --check
& .\.venv\Scripts\python.exe -m pytest backend/tests/test_v2_campaigns.py -q

Write-Host "Bootstrap complete. Activate with: .\.venv\Scripts\Activate.ps1"
