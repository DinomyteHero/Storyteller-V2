"""``storyteller setup`` — first-time project setup.

Creates data dirs, copies .env.example -> .env, installs deps,
and runs ``storyteller doctor`` to verify.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from shared.ingest_paths import ensure_layout, standard_dirs, static_dirs


def register(subparsers) -> None:
    p = subparsers.add_parser("setup", help="First-time project setup")
    p.add_argument("--skip-deps", action="store_true", help="Skip pip install")
    p.set_defaults(func=run)


def _ensure_dirs() -> None:
    dirs = standard_dirs() + static_dirs()
    existed = {p: p.exists() for p in dirs}
    ensure_layout()
    for p in static_dirs():
        p.mkdir(parents=True, exist_ok=True)
    for p in dirs:
        status = "(exists)" if existed[p] else "(created)"
        print(f"  Directory: {p} {status}")


def _copy_env() -> None:
    root = Path.cwd()
    env = root / ".env"
    example = root / ".env.example"
    if env.exists():
        print("  .env already exists — skipping")
        return
    if example.exists():
        shutil.copy2(example, env)
        print("  Copied .env.example -> .env")
    else:
        print("  WARNING: .env.example not found, skipping")


def _install_deps() -> None:
    print("\n  Installing dependencies (pip install -e .) ...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", "."],
        cwd=str(Path.cwd()),
    )
    if result.returncode != 0:
        print("  ERROR: pip install failed")
        sys.exit(1)
    print("  Dependencies installed successfully")


def run(args) -> int:
    print("\n  Storyteller AI — Setup\n")

    # Data dirs
    _ensure_dirs()

    # .env
    _copy_env()

    # Deps
    if not args.skip_deps:
        _install_deps()
    else:
        print("\n  Skipping dependency install (--skip-deps)")

    # Run doctor
    print("\n  Running health check...\n")
    from storyteller.commands.doctor import run as doctor_run
    return doctor_run(args)
