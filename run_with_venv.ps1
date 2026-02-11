# Storyteller AI - Run Python scripts/commands with venv activation
#
# Usage: .\run_with_venv.ps1 <script or module> [args...]
#
# Examples:
#   .\run_with_venv.ps1 scripts\ingest_style.py
#   .\run_with_venv.ps1 -m storyteller dev
#   .\run_with_venv.ps1 -m storyteller ingest --input ./data/lore
#
# NOTE: Do NOT include "python" - this script adds it automatically!
#   WRONG: .\run_with_venv.ps1 python scripts\ingest_style.py
#   RIGHT: .\run_with_venv.ps1 scripts\ingest_style.py

$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
Set-Location -LiteralPath $root

# Find venv Python
$venvPython = $null
$venvName = $null

$candidates = @(
    @{ Path = (Join-Path $root "venv\Scripts\python.exe"); Name = "venv" },
    @{ Path = (Join-Path $root ".venv\Scripts\python.exe"); Name = ".venv" }
)

foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate.Path) {
        $venvPython = $candidate.Path
        $venvName = $candidate.Name
        break
    }
}

if (-not $venvPython) {
    Write-Host ""
    Write-Host "[ERROR] No virtual environment found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please create one first:" -ForegroundColor Yellow
    Write-Host "  python -m venv venv" -ForegroundColor White
    Write-Host "  .\venv\Scripts\Activate.ps1" -ForegroundColor White
    Write-Host "  pip install -e ." -ForegroundColor White
    Write-Host ""
    Write-Host "Or run setup:" -ForegroundColor Yellow
    Write-Host "  .\setup_dev.bat" -ForegroundColor White
    Write-Host ""
    exit 1
}

# Check for common mistake
if ($args.Count -gt 0 -and $args[0] -eq "python") {
    Write-Host ""
    Write-Host "[ERROR] Do not include 'python' in the command!" -ForegroundColor Red
    Write-Host ""
    Write-Host "You ran: .\run_with_venv.ps1 python $($args[1..$args.Count] -join ' ')" -ForegroundColor Yellow
    Write-Host "Should be: .\run_with_venv.ps1 $($args[1..$args.Count] -join ' ')" -ForegroundColor Green
    Write-Host ""
    Write-Host "This script automatically uses the venv Python." -ForegroundColor Cyan
    Write-Host ""
    exit 1
}

Write-Host "[INFO] Using virtual environment: $venvName" -ForegroundColor Green
Write-Host ""

# Run the command with venv Python
& $venvPython $args

exit $LASTEXITCODE
