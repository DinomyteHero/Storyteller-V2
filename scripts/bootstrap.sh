#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "== Storyteller bootstrap (Linux/macOS) =="
"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11+ is required")
print(f"Python OK: {sys.version.split()[0]}")
PY

if [[ ! -d ".venv" ]]; then
  "$PYTHON_BIN" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .

if [[ ! -f ".env" && -f ".env.production.example" ]]; then
  cp .env.production.example .env
fi

python run_app.py --check || true
python -m pytest backend/tests/test_v2_campaigns.py -q

echo "Bootstrap complete. Activate with: source .venv/bin/activate"
