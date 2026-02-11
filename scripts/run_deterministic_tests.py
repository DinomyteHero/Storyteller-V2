#!/usr/bin/env python3
"""Single-command entry point for deterministic testing.

Runs the LangGraph pipeline harness (mocked agents, no LLMs) with fixed
ENCOUNTER_SEED and fixed campaign. Optional: run smoke test (real LLMs).

Usage:
  python scripts/run_deterministic_tests.py              # harness only (default)
  python scripts/run_deterministic_tests.py --smoke      # harness + smoke test
  python scripts/run_deterministic_tests.py --smoke-only # smoke test only

Exit: 0 on success, non-zero on failure. Failures point to responsible node/agent.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


def _python_executable() -> str:
    """Prefer project venv Python if it exists."""
    venv_py = _root / "venv" / "Scripts" / "python.exe"
    if venv_py.exists():
        return str(venv_py)
    venv_py_unix = _root / "venv" / "bin" / "python"
    if venv_py_unix.exists():
        return str(venv_py_unix)
    return sys.executable


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="Run deterministic tests (harness + optional smoke test)."
    )
    ap.add_argument(
        "--smoke",
        action="store_true",
        help="Also run smoke test after harness (requires LLMs)",
    )
    ap.add_argument(
        "--smoke-only",
        action="store_true",
        help="Run only smoke test (skip harness)",
    )
    ap.add_argument(
        "--smoke-turns",
        type=int,
        default=5,
        help="Number of smoke test turns (default 5)",
    )
    args = ap.parse_args()

    os.chdir(_root)

    # Harness: mocked agents, no LLMs, 10–20 turns, fixed seed
    if not args.smoke_only:
        print("Running deterministic harness (15 turns, ENCOUNTER_SEED=42)...")
        env = os.environ.copy()
        env.setdefault("ENCOUNTER_SEED", "42")
        r = subprocess.run(
            [
                _python_executable(),
                "-m",
                "pytest",
                "backend/tests/test_deterministic_harness.py",
                "-v",
            ],
            env=env,
            cwd=_root,
        )
        if r.returncode != 0:
            print("\nHarness FAILED. Check output above for node/agent hints.", file=sys.stderr)
            return r.returncode
        print("Harness OK.\n")

    # Smoke: real LLMs, creates campaign, runs N turns
    if args.smoke or args.smoke_only:
        print("Running smoke test...")
        r = subprocess.run(
            [
                _python_executable(),
                "scripts/smoke_test.py",
                "--turns",
                str(args.smoke_turns),
                "--use-temp-db",
            ],
            cwd=_root,
        )
        if r.returncode != 0:
            print("\nSmoke test FAILED.", file=sys.stderr)
            return r.returncode
        print("Smoke test OK.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
