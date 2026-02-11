#!/usr/bin/env python3
"""Unified Storyteller launcher for API/UI/runtime preflight checks."""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TextIO

try:
    import httpx
except Exception:  # pragma: no cover - surfaced by preflight
    httpx = None  # type: ignore

ROOT = Path(__file__).resolve().parent
DEFAULT_API_HOST = "0.0.0.0"
DEFAULT_API_PORT = 8000
DEFAULT_UI_PORT = 5173
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"


class AppRunnerError(RuntimeError):
    """Raised for wrapper failures."""


def load_dotenv(dotenv_path: Path) -> None:
    """Load simple KEY=VALUE pairs from .env into process env (non-destructive)."""
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def find_venv_python(root: Path) -> str | None:
    candidates = [
        root / "venv" / "Scripts" / "python.exe",
        root / ".venv" / "Scripts" / "python.exe",
        root / "venv" / "bin" / "python",
        root / ".venv" / "bin" / "python",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def is_port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def detect_ui_mode(root: Path) -> str | None:
    if (root / "frontend" / "package.json").exists() and shutil.which("npm"):
        return "svelte"
    if (root / "streamlit_app.py").exists():
        return "streamlit"
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Storyteller API/UI with preflight checks")
    parser.add_argument("--dev", action="store_true", help="Enable development mode/reload where supported")
    parser.add_argument("--api-only", action="store_true", help="Start only the API")
    parser.add_argument("--ui-only", action="store_true", help="Start only the UI")
    parser.add_argument("--no-ui", action="store_true", help="Do not start UI")
    parser.add_argument("--host", default=os.environ.get("STORYTELLER_HOST", DEFAULT_API_HOST), help="API host")
    parser.add_argument("--port", type=int, default=int(os.environ.get("STORYTELLER_PORT", DEFAULT_API_PORT)), help="API port")
    parser.add_argument("--ui-port", type=int, default=int(os.environ.get("STORYTELLER_UI_PORT", DEFAULT_UI_PORT)), help="UI port")
    parser.add_argument("--setting-id", default=os.environ.get("DEFAULT_SETTING_ID") or os.environ.get("SETTING_ID"), help="Default setting id")
    parser.add_argument("--period-id", default=os.environ.get("DEFAULT_PERIOD_ID") or os.environ.get("PERIOD_ID"), help="Default period id")
    parser.add_argument("--setting-pack-paths", default=os.environ.get("SETTING_PACK_PATHS"), help="Semicolon-delimited setting pack roots")
    parser.add_argument("--validate-packs", action="store_true", help="Run scripts/validate_setting_packs.py before launch")
    parser.add_argument("--check", action="store_true", help="Run preflight checks and exit")
    parser.add_argument("--ollama-base-url", default=os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL), help="LLM runtime base URL")
    parser.add_argument("--require-llm", action="store_true", help="Fail preflight if Ollama/LLM runtime is unreachable")
    parser.add_argument("--start-ollama", action="store_true", help="Attempt to start `ollama serve` when unreachable")
    parser.add_argument("--python", default=os.environ.get("STORYTELLER_PYTHON"), help="Python executable to use for child processes")
    args = parser.parse_args()

    if args.api_only and args.ui_only:
        parser.error("--api-only and --ui-only cannot be combined")
    if args.ui_only and args.no_ui:
        parser.error("--ui-only and --no-ui cannot be combined")
    return args


def sanitize_config(cfg: dict[str, str | int | bool | None]) -> dict[str, str | int | bool | None]:
    redacted: dict[str, str | int | bool | None] = {}
    for key, value in cfg.items():
        if any(token in key.upper() for token in ("TOKEN", "KEY", "SECRET", "PASSWORD")) and value:
            redacted[key] = "***"
        else:
            redacted[key] = value
    return redacted


def run_validate_packs(python_exe: str) -> None:
    cmd = [python_exe, "scripts/validate_setting_packs.py"]
    print(f"[CHECK] Running: {' '.join(cmd)}")
    rc = subprocess.call(cmd, cwd=str(ROOT), env=os.environ.copy())
    if rc != 0:
        raise AppRunnerError("Setting pack validation failed")


def poll_url(url: str, timeout_s: float, label: str) -> None:
    if httpx is None:
        raise AppRunnerError("httpx is required but not installed")

    started = time.time()
    while time.time() - started < timeout_s:
        try:
            res = httpx.get(url, timeout=2.0)
            if 200 <= res.status_code < 500:
                print(f"[READY] {label}: {url}")
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise AppRunnerError(f"Timed out waiting for {label}: {url}")


def check_ollama(base_url: str, require: bool) -> None:
    if httpx is None:
        print("[WARN] Skipping LLM runtime reachability check (httpx not installed)")
        return
    probe = f"{base_url.rstrip('/')}/api/tags"
    try:
        res = httpx.get(probe, timeout=2.0)
        if res.status_code == 200:
            print(f"[OK] LLM runtime reachable at {probe}")
            return
    except Exception:
        pass
    msg = f"LLM runtime not reachable at {probe}"
    if require:
        raise AppRunnerError(msg)
    print(f"[WARN] {msg}")


def maybe_start_ollama(base_url: str) -> subprocess.Popen[str] | None:
    ollama_bin = shutil.which("ollama")
    if not ollama_bin:
        print("[WARN] `ollama` not found on PATH; cannot auto-start")
        return None
    print("[INFO] Starting ollama serve ...")
    kwargs: dict[str, object] = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "cwd": str(ROOT),
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen([ollama_bin, "serve"], **kwargs)
    for _ in range(12):
        if httpx is not None:
            try:
                res = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=1.0)
                if res.status_code == 200:
                    print("[OK] ollama serve started")
                    return proc
            except Exception:
                pass
        time.sleep(0.5)
    print("[WARN] ollama process started but runtime still not reachable")
    return proc


def stream_output(prefix: str, stream: TextIO) -> None:
    for line in iter(stream.readline, ""):
        print(f"[{prefix}] {line.rstrip()}")


def spawn_process(cmd: list[str], env: dict[str, str], cwd: Path, prefix: str) -> tuple[subprocess.Popen[str], threading.Thread, threading.Thread]:
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    assert proc.stderr is not None
    t_out = threading.Thread(target=stream_output, args=(prefix, proc.stdout), daemon=True)
    t_err = threading.Thread(target=stream_output, args=(prefix, proc.stderr), daemon=True)
    t_out.start()
    t_err.start()
    return proc, t_out, t_err


def build_commands(args: argparse.Namespace, python_exe: str, ui_mode: str | None) -> tuple[list[str] | None, list[str] | None, Path | None]:
    api_cmd: list[str] | None = None
    ui_cmd: list[str] | None = None
    ui_cwd: Path | None = None

    if not args.ui_only:
        api_cmd = [
            python_exe,
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            args.host,
            "--port",
            str(args.port),
        ]
        if args.dev:
            api_cmd.append("--reload")

    start_ui = not args.api_only and not args.no_ui
    if start_ui:
        if ui_mode == "svelte":
            npm_bin = shutil.which("npm")
            if npm_bin is None:
                raise AppRunnerError("UI mode svelte detected but npm is not available")
            ui_cmd = [npm_bin, "run", "dev", "--", "--port", str(args.ui_port)]
            ui_cwd = ROOT / "frontend"
        elif ui_mode == "streamlit":
            ui_cmd = [python_exe, "-m", "streamlit", "run", "streamlit_app.py", "--server.port", str(args.ui_port)]
            ui_cwd = ROOT
        else:
            print("[WARN] No supported UI detected; continuing without UI")

    return api_cmd, ui_cmd, ui_cwd


def run_preflight(args: argparse.Namespace, python_exe: str, ui_mode: str | None) -> None:
    print("== Storyteller preflight ==")
    if sys.version_info < (3, 11):
        raise AppRunnerError("Python 3.11+ is required")
    print(f"[OK] Python {sys.version.split()[0]}")

    for module in ("fastapi", "uvicorn", "httpx"):
        try:
            __import__(module)
            print(f"[OK] import {module}")
        except Exception as exc:
            raise AppRunnerError(f"Missing dependency: {module} ({exc})") from exc

    if args.setting_pack_paths:
        missing = []
        sep = ";" if ";" in args.setting_pack_paths else os.pathsep
        for raw in args.setting_pack_paths.split(sep):
            p = raw.strip()
            if not p:
                continue
            resolved = (ROOT / p).resolve() if not Path(p).is_absolute() else Path(p)
            if not resolved.exists():
                missing.append(p)
        if missing:
            raise AppRunnerError(f"Missing setting pack paths: {missing}")
        print("[OK] setting pack paths exist")
    else:
        print("[WARN] SETTING_PACK_PATHS not set; defaults will be used by backend")

    if args.validate_packs:
        run_validate_packs(python_exe)

    if not args.ui_only and not is_port_available(args.host if args.host != "0.0.0.0" else "127.0.0.1", args.port):
        raise AppRunnerError(f"API port {args.port} is already in use. Use --port to override.")
    if not args.api_only and not args.no_ui and ui_mode and not is_port_available("127.0.0.1", args.ui_port):
        raise AppRunnerError(f"UI port {args.ui_port} is already in use. Use --ui-port to override.")

    check_ollama(args.ollama_base_url, args.require_llm)


def main() -> int:
    load_dotenv(ROOT / ".env")
    args = parse_args()

    python_exe = args.python or find_venv_python(ROOT) or sys.executable
    os.environ.setdefault("PYTHONPATH", str(ROOT))
    if args.setting_id:
        os.environ["DEFAULT_SETTING_ID"] = args.setting_id
    if args.period_id:
        os.environ["DEFAULT_PERIOD_ID"] = args.period_id
    if args.setting_pack_paths:
        os.environ["SETTING_PACK_PATHS"] = args.setting_pack_paths
    os.environ.setdefault("STORYTELLER_API_URL", f"http://127.0.0.1:{args.port}")

    ui_mode = detect_ui_mode(ROOT)

    config = sanitize_config(
        {
            "python_executable": python_exe,
            "dev": args.dev,
            "api_only": args.api_only,
            "ui_only": args.ui_only,
            "no_ui": args.no_ui,
            "api_host": args.host,
            "api_port": args.port,
            "ui_port": args.ui_port,
            "ui_mode": ui_mode,
            "setting_id": args.setting_id,
            "period_id": args.period_id,
            "setting_pack_paths": args.setting_pack_paths,
            "ollama_base_url": args.ollama_base_url,
        }
    )
    print("== Storyteller runtime config ==")
    for k, v in config.items():
        print(f"- {k}: {v}")

    try:
        run_preflight(args, python_exe, ui_mode)
        if args.check:
            print("[OK] Preflight passed (--check requested, exiting)")
            return 0

        started_children: list[subprocess.Popen[str]] = []
        started_threads: list[threading.Thread] = []
        started_ollama: subprocess.Popen[str] | None = None

        if args.start_ollama:
            started_ollama = maybe_start_ollama(args.ollama_base_url)

        api_cmd, ui_cmd, ui_cwd = build_commands(args, python_exe, ui_mode)
        env = os.environ.copy()

        if api_cmd:
            print(f"[INFO] Starting API: {' '.join(api_cmd)}")
            p, t1, t2 = spawn_process(api_cmd, env, ROOT, "API")
            started_children.append(p)
            started_threads.extend([t1, t2])
            poll_url(f"http://127.0.0.1:{args.port}/health", timeout_s=40, label="API health")

        if ui_cmd and ui_cwd:
            print(f"[INFO] Starting UI: {' '.join(ui_cmd)}")
            p, t1, t2 = spawn_process(ui_cmd, env, ui_cwd, "UI")
            started_children.append(p)
            started_threads.extend([t1, t2])
            poll_url(f"http://127.0.0.1:{args.ui_port}", timeout_s=50, label="UI")

        if not started_children:
            raise AppRunnerError("Nothing to start (combination of flags disabled both API and UI)")

        print("[INFO] Storyteller is running. Press Ctrl+C to stop.")

        stop = threading.Event()

        def _terminate(_signum: int, _frame) -> None:
            stop.set()

        signal.signal(signal.SIGINT, _terminate)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _terminate)

        while not stop.is_set():
            for p in started_children:
                rc = p.poll()
                if rc is not None:
                    raise AppRunnerError(f"Child process exited early (pid={p.pid}, code={rc})")
            time.sleep(0.4)

        print("[INFO] Shutting down children...")
        for p in started_children:
            if p.poll() is None:
                p.terminate()
        for p in started_children:
            if p.poll() is None:
                try:
                    p.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    p.kill()

        if started_ollama and started_ollama.poll() is None:
            started_ollama.terminate()

        return 0
    except AppRunnerError as exc:
        print(f"[ERROR] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
