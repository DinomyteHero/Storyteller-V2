"""``storyteller dev`` — start backend + SvelteKit UI for development.

Launches uvicorn (backend) and the SvelteKit frontend (via npm/Vite)
as subprocesses with shared log output.  Ctrl-C shuts both down cleanly.

If a virtual environment (venv/ or .venv/) exists, it will be used automatically.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def register(subparsers) -> None:
    p = subparsers.add_parser("dev", help="Start backend + SvelteKit UI")
    p.add_argument("--backend-only", action="store_true", help="Only start the FastAPI backend")
    p.add_argument("--ui-only", action="store_true", help="Only start the SvelteKit UI")
    p.add_argument("--backend-port", type=int, default=8000, help="Backend port (default: 8000)")
    p.add_argument("--ui-port", type=int, default=5173, help="SvelteKit/Vite port (default: 5173)")
    p.add_argument("--no-ollama", action="store_true", help="Skip Ollama auto-start check")
    p.add_argument("--no-venv", action="store_true", help="Skip venv detection, use current Python")
    p.set_defaults(func=run)


def _find_venv_python() -> Path | None:
    """Find venv Python executable (venv/ or .venv/)."""
    root = Path.cwd()
    candidates = [
        root / "venv" / "Scripts" / "python.exe",  # Windows venv
        root / ".venv" / "Scripts" / "python.exe",  # Windows .venv
        root / "venv" / "bin" / "python",  # Unix venv
        root / ".venv" / "bin" / "python",  # Unix .venv
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _is_in_venv() -> bool:
    """Check if current Python is running in a virtual environment."""
    return hasattr(sys, 'real_prefix') or (
        hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix
    )


def _load_dotenv() -> None:
    """Load .env file into os.environ (simple key=value parser)."""
    env_file = Path.cwd() / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        os.environ.setdefault(key, value)


def _check_ollama_running() -> bool:
    """Return True if Ollama API is reachable."""
    try:
        import httpx
        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        resp = httpx.get(f"{base_url}/api/tags", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False


def _find_npm() -> str | None:
    """Find npm executable on PATH."""
    import shutil
    return shutil.which("npm")


def _try_start_ollama() -> None:
    """Attempt to start Ollama in the background."""
    import shutil
    ollama_bin = shutil.which("ollama")
    if not ollama_bin:
        print("  WARNING: Ollama not found on PATH — LLM calls will fail")
        print("           Install from https://ollama.com/download")
        return

    if _check_ollama_running():
        print("  Ollama is running")
        return

    print("  Starting Ollama ...")
    try:
        # Fire and forget — Ollama runs as a background daemon
        if sys.platform == "win32":
            subprocess.Popen(
                [ollama_bin, "serve"],
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                [ollama_bin, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        # Wait up to 10 seconds for Ollama to become reachable
        for _ in range(20):
            time.sleep(0.5)
            if _check_ollama_running():
                print("  Ollama started successfully")
                return
        print("  WARNING: Ollama started but not yet reachable — it may still be loading")
    except Exception as e:
        print(f"  WARNING: Could not start Ollama: {e}")


def run(args) -> int:
    root = Path.cwd()
    _load_dotenv()

    # Determine which Python to use
    python_exe = sys.executable
    
    if not args.no_venv:
        venv_python = _find_venv_python()
        if venv_python and not _is_in_venv():
            print(f"\n  Found virtual environment: {venv_python.parent.parent.name}/")
            print(f"  Using venv Python instead of system Python")
            python_exe = str(venv_python)
        elif venv_python and _is_in_venv():
            print(f"  Using virtual environment: {Path(sys.prefix).name}/")
        elif not venv_python:
            print("  WARNING: No virtual environment found (checked venv/ and .venv/)")
            print("           Consider creating one with: python -m venv venv")
            print("           Then install: .\\venv\\Scripts\\Activate.ps1 && pip install -e .")
            print()

    # Pre-flight checks
    env_file = root / ".env"
    if not env_file.exists():
        print("  WARNING: .env not found — using defaults. Run: storyteller setup")

    if not args.no_ollama and not args.ui_only:
        _try_start_ollama()

    procs: list[subprocess.Popen] = []

    try:
        # Backend
        if not args.ui_only:
            print(f"\n  Starting backend on port {args.backend_port} ...")
            backend_cmd = [
                python_exe, "-m", "uvicorn",
                "backend.main:app",
                "--reload",
                "--host", "0.0.0.0",
                "--port", str(args.backend_port),
            ]
            backend_proc = subprocess.Popen(
                backend_cmd,
                cwd=str(root),
            )
            procs.append(backend_proc)
            # Brief delay to let backend start binding
            time.sleep(1)

        # SvelteKit UI (via npm/Vite)
        if not args.backend_only:
            frontend_dir = root / "frontend"
            npm_bin = _find_npm()
            if not npm_bin:
                print("  WARNING: npm not found on PATH — cannot start SvelteKit UI")
                print("           Install Node.js from https://nodejs.org/")
            elif not frontend_dir.is_dir():
                print("  WARNING: frontend/ directory not found — cannot start SvelteKit UI")
            else:
                print(f"  Starting SvelteKit UI on port {args.ui_port} ...")
                ui_cmd = [
                    npm_bin, "run", "dev", "--",
                    "--port", str(args.ui_port),
                ]
                ui_proc = subprocess.Popen(
                    ui_cmd,
                    cwd=str(frontend_dir),
                )
                procs.append(ui_proc)

        if not procs:
            print("  Nothing to start (both --backend-only and --ui-only specified)")
            return 1

        print(f"\n  Storyteller dev server running!")
        if not args.ui_only:
            print(f"    Backend:  http://localhost:{args.backend_port}")
            print(f"    API docs: http://localhost:{args.backend_port}/docs")
        if not args.backend_only:
            print(f"    UI:       http://localhost:{args.ui_port}")
        print(f"\n  Press Ctrl+C to stop.\n")

        # Wait for any process to exit
        while True:
            for p in procs:
                rc = p.poll()
                if rc is not None:
                    print(f"\n  Process (PID {p.pid}) exited with code {rc}")
                    raise KeyboardInterrupt
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n  Shutting down ...")
        for p in procs:
            if p.poll() is None:
                p.terminate()
        # Give processes time to exit
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        print("  Stopped.")
        return 0
