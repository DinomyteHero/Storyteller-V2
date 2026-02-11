#!/usr/bin/env python3
"""Standalone preflight runner for Storyteller wrapper."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import run_app


if __name__ == "__main__":
    sys.argv = ["run_app.py", "--check", *sys.argv[1:]]
    raise SystemExit(run_app.main())
