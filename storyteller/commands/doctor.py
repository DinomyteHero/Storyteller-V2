"""``storyteller doctor`` — environment health check.

Checks: Python version, venv active, deps installed, .env present,
data dirs exist, Ollama reachable, required models pulled,
LanceDB writable, embedding model accessible.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

# ANSI helpers (no-op on dumb terminals)
_COLOR = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _ok(msg: str) -> str:
    return f"  [OK]   {msg}" if not _COLOR else f"  \033[32m[OK]\033[0m   {msg}"


def _warn(msg: str) -> str:
    return f"  [WARN] {msg}" if not _COLOR else f"  \033[33m[WARN]\033[0m {msg}"


def _fail(msg: str) -> str:
    return f"  [FAIL] {msg}" if not _COLOR else f"  \033[31m[FAIL]\033[0m {msg}"


def _section(title: str) -> str:
    return f"\n{'=' * 60}\n  {title}\n{'=' * 60}"


def register(subparsers) -> None:
    p = subparsers.add_parser("doctor", help="Check environment health")
    p.set_defaults(func=run)


def _check_python() -> bool:
    v = sys.version_info
    ok = v >= (3, 11)
    line = f"Python {v.major}.{v.minor}.{v.micro}"
    print(_ok(line) if ok else _fail(f"{line} — need 3.11+"))
    return ok


def _check_venv() -> bool:
    in_venv = sys.prefix != sys.base_prefix
    print(_ok("Virtual environment active") if in_venv else _warn("No virtual environment detected (recommended: create with python -m venv venv)"))
    return True  # warn only


def _check_deps() -> list[str]:
    required = [
        "fastapi", "uvicorn", "pydantic", "yaml", "lancedb",
        "sentence_transformers", "httpx", "pymupdf4llm", "pyarrow",
        "ebooklib", "bs4", "tiktoken", "langchain_core", "langgraph",
    ]
    missing = []
    for mod in required:
        try:
            if importlib.util.find_spec(mod) is None:
                missing.append(mod)
        except (ImportError, ValueError):
            missing.append(mod)
    if missing:
        print(_fail(f"Missing packages: {', '.join(missing)}"))
        print(f"         Run: pip install -e .")
    else:
        print(_ok(f"All {len(required)} required packages installed"))
    return missing


def _check_env_file() -> bool:
    root = Path.cwd()
    env = root / ".env"
    example = root / ".env.example"
    if env.exists():
        print(_ok(".env file present"))
        return True
    if example.exists():
        print(_fail(".env missing — copy from .env.example:"))
        print(f"         cp .env.example .env")
    else:
        print(_fail(".env missing (no .env.example found either)"))
    return False


def _check_data_dirs() -> bool:
    root = Path.cwd()
    dirs = ["data", "data/lancedb", "data/lore", "data/style", "data/manifests"]
    all_ok = True
    for d in dirs:
        p = root / d
        if p.is_dir():
            print(_ok(f"Directory: {d}/"))
        else:
            print(_warn(f"Missing directory: {d}/ — will be created by setup"))
            all_ok = False
    return all_ok


def _check_ollama() -> tuple[bool, str]:
    """Check Ollama binary and API reachability."""
    ollama_bin = shutil.which("ollama")
    if not ollama_bin:
        print(_fail("Ollama not found on PATH"))
        print("         Install from https://ollama.com/download")
        return False, ""

    # Check if Ollama is running
    try:
        import httpx
        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        resp = httpx.get(f"{base_url}/api/tags", timeout=5)
        if resp.status_code == 200:
            print(_ok(f"Ollama running at {base_url}"))
            return True, base_url
        print(_warn(f"Ollama installed but API returned {resp.status_code}"))
        print(f"         Start it: ollama serve")
        return False, base_url
    except Exception:
        print(_warn("Ollama installed but not reachable"))
        print(f"         Start it: ollama serve")
        return False, ""


def _check_models(base_url: str) -> bool:
    """Check that required Ollama models are pulled."""
    if not base_url:
        print(_warn("Skipping model check (Ollama not reachable)"))
        return False

    # Dynamically read required models from per-role config
    try:
        from backend.app.config import MODEL_CONFIG
        required_models = sorted(set(
            cfg.get("model", "")
            for cfg in MODEL_CONFIG.values()
            if cfg.get("provider") == "ollama" and cfg.get("model")
        ))
    except ImportError:
        required_models = ["qwen3:8b", "nomic-embed-text"]  # fallback
    try:
        import httpx
        resp = httpx.get(f"{base_url}/api/tags", timeout=5)
        data = resp.json()
        available = {m["name"] for m in data.get("models", [])}
        # Normalize: "qwen3:8b" matches "qwen3:8b" exactly
        # Also check without tag for partial matches
        all_ok = True
        for model in required_models:
            found = model in available
            if not found:
                # Try matching by base name (e.g. "qwen3:8b" in "qwen3:8b-q4_0")
                base = model.split(":")[0]
                found = any(base in a for a in available)
            if found:
                print(_ok(f"Model: {model}"))
            else:
                print(_fail(f"Model not pulled: {model}"))
                print(f"         Run: ollama pull {model}")
                all_ok = False
        return all_ok
    except Exception as e:
        print(_warn(f"Could not check models: {e}"))
        return False


def _check_lancedb_writable() -> bool:
    db_path = Path.cwd() / "data" / "lancedb"
    if not db_path.exists():
        print(_warn("data/lancedb/ does not exist yet (created on first ingest)"))
        return True
    # Test write
    test_file = db_path / ".doctor_test"
    try:
        test_file.write_text("ok")
        test_file.unlink()
        print(_ok("data/lancedb/ is writable"))
        return True
    except OSError as e:
        print(_fail(f"data/lancedb/ not writable: {e}"))
        return False


def run(args) -> int:
    print(_section("Storyteller Doctor"))
    errors = 0

    # Python
    if not _check_python():
        errors += 1

    # Venv
    _check_venv()

    # Deps
    missing = _check_deps()
    if missing:
        errors += 1

    # .env
    if not _check_env_file():
        errors += 1

    # Data dirs
    _check_data_dirs()

    # Ollama
    ollama_ok, base_url = _check_ollama()
    if not ollama_ok:
        errors += 1

    # Models
    if not _check_models(base_url):
        errors += 1

    # LanceDB
    _check_lancedb_writable()

    # Summary
    print()
    if errors == 0:
        print(_ok("All checks passed — ready to run!"))
        return 0
    else:
        print(_fail(f"{errors} issue(s) found — see above for fixes"))
        return 1
