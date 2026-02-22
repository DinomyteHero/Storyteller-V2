#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "Starting Storyteller wrapper..."

if [[ -x "./venv/bin/python" ]]; then
  PY="./venv/bin/python"
elif [[ -x "./.venv/bin/python" ]]; then
  PY="./.venv/bin/python"
else
  PY="python3"
fi

echo "Using Python: $PY"
"$PY" run_app.py --dev "$@"
RC=$?
if [[ $RC -ne 0 ]]; then
  echo ""
  echo "Wrapper exited with code $RC."
fi
exit $RC
