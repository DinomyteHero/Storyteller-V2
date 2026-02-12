"""Runtime env parsing helpers used by API and launch entrypoints."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

DEFAULT_DEV_CORS_ALLOW_ORIGINS: tuple[str, ...] = (
    "http://localhost",
    "http://127.0.0.1",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8501",
    "http://127.0.0.1:8501",
)


@dataclass(frozen=True)
class SecuritySettings:
    """Auth/CORS runtime settings used by API and launcher safety checks."""

    dev_mode: bool
    api_token: str
    cors_allow_origins: list[str]


def env_flag(name: str, default: bool = False, environ: Mapping[str, str] | None = None) -> bool:
    """Read boolean env values from common truthy/falsey forms."""
    env = os.environ if environ is None else environ
    val = env.get(name, "").strip().lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "on")


def parse_cors_allowlist(raw: str, fallback: tuple[str, ...] = DEFAULT_DEV_CORS_ALLOW_ORIGINS) -> list[str]:
    origins = [o.strip() for o in raw.split(",") if o and o.strip()]
    if origins:
        return origins
    return list(fallback)


def load_security_settings(environ: Mapping[str, str] | None = None) -> SecuritySettings:
    env = os.environ if environ is None else environ
    return SecuritySettings(
        dev_mode=env_flag("STORYTELLER_DEV_MODE", default=True, environ=env),
        api_token=env.get("STORYTELLER_API_TOKEN", "").strip(),
        cors_allow_origins=parse_cors_allowlist(env.get("STORYTELLER_CORS_ALLOW_ORIGINS", "")),
    )
