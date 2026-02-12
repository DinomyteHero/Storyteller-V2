"""Versioned prompt registry and hashing helpers."""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

_PROMPT_ROOT = Path(__file__).resolve().parents[3] / "prompts"
_DEFAULT_VERSION = "v1"


def _prompt_path(name: str, version: str = _DEFAULT_VERSION) -> Path:
    return _PROMPT_ROOT / version / f"{name}.txt"


@lru_cache(maxsize=64)
def load_prompt(name: str, version: str = _DEFAULT_VERSION) -> str:
    path = _prompt_path(name, version)
    return path.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=64)
def prompt_hash(name: str, version: str = _DEFAULT_VERSION) -> str:
    body = load_prompt(name, version)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return digest


def prompt_version_id(name: str, version: str = _DEFAULT_VERSION) -> str:
    return f"{version}:{prompt_hash(name, version)[:12]}"


def prompt_registry_snapshot() -> dict[str, str]:
    """Compact prompt version map attached to turn metadata."""
    return {
        "suggestion_refiner_system": prompt_version_id("suggestion_refiner_system"),
    }
