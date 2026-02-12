"""Shared helpers for run_app launcher behavior.

This module exists to keep `run_app.py` as a thin orchestration entrypoint
while preserving command-line behavior.
"""
from __future__ import annotations

import os
import shutil
import socket
from pathlib import Path
from typing import Mapping

from shared.runtime_settings import load_security_settings, parse_cors_allowlist


class AppRunnerError(RuntimeError):
    """Raised for launcher/preflight failures."""


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


def sanitize_config(cfg: Mapping[str, str | int | bool | None]) -> dict[str, str | int | bool | None]:
    redacted: dict[str, str | int | bool | None] = {}
    for key, value in cfg.items():
        if any(token in key.upper() for token in ("TOKEN", "KEY", "SECRET", "PASSWORD")) and value:
            redacted[key] = "***"
        else:
            redacted[key] = value
    return redacted


def ensure_prod_env_safety(environ: Mapping[str, str] | None = None) -> None:
    """Validate production auth/cors env when STORYTELLER_DEV_MODE=0."""
    env = os.environ if environ is None else environ
    settings = load_security_settings(environ=env)
    if settings.dev_mode:
        return

    if not settings.api_token:
        raise AppRunnerError("Production mode requires STORYTELLER_API_TOKEN")

    raw_allowlist = env.get("STORYTELLER_CORS_ALLOW_ORIGINS", "").strip()
    if not raw_allowlist:
        raise AppRunnerError("Production mode requires explicit STORYTELLER_CORS_ALLOW_ORIGINS")

    origins = parse_cors_allowlist(raw_allowlist, fallback=())
    if not origins or "*" in origins:
        raise AppRunnerError("Production mode forbids wildcard CORS; set explicit STORYTELLER_CORS_ALLOW_ORIGINS")
