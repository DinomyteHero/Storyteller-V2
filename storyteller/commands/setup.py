"""``storyteller setup`` — first-time project setup.

Creates data dirs, copies .env.example -> .env, installs deps,
and runs ``storyteller doctor`` to verify.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def register(subparsers) -> None:
    p = subparsers.add_parser("setup", help="First-time project setup")
    p.add_argument("--skip-deps", action="store_true", help="Skip pip install")
    p.set_defaults(func=run)


def _ensure_dirs() -> None:
    root = Path.cwd()
    dirs = ["data", "data/lancedb", "data/lore", "data/style", "data/manifests", "data/static", "data/static/era_packs"]
    for d in dirs:
        p = root / d
        existed = p.exists()
        p.mkdir(parents=True, exist_ok=True)
        print(f"  Directory: {d}/ {'(exists)' if existed else '(created)'}")


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
    root = Path.cwd()
    dirs = ["data", "data/lancedb", "data/lore", "data/style", "data/manifests", "data/static", "data/static/era_packs"]
    for d in dirs:
        p = root / d
        existed = p.exists()
        p.mkdir(parents=True, exist_ok=True)
        status = "(exists)" if existed else "(created)"
        print(f"  Directory: {d}/ {status}")

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
