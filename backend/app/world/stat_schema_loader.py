"""Loader for configurable stat schemas.

Each stat schema is a YAML file in data/static/stat_schemas/ that defines
the stats available in a given rule system (e.g. storyteller_core, dnd_5e_simplified).
The schema_id is resolved from SettingRules.rule_system_id or provided directly.

Usage::

    schema = load_stat_schema("storyteller_core")
    stat_ids = [s["id"] for s in schema["stats"]]
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _schemas_dir() -> Path:
    raw = os.environ.get("STAT_SCHEMA_DIR", "").strip()
    if raw:
        p = Path(raw)
        return p if p.is_absolute() else _repo_root() / p
    return _repo_root() / "data" / "static" / "stat_schemas"


@lru_cache(maxsize=16)
def load_stat_schema(schema_id: str) -> dict[str, Any]:
    """Load a stat schema by ID.

    Looks for ``<schema_id>.yaml`` (or ``.yml``) in the stat schemas directory.
    Returns the parsed YAML as a dict.  Raises ``FileNotFoundError`` if the
    schema file cannot be found.

    Results are cached so repeated calls within the same process are free.
    """
    schemas_dir = _schemas_dir()
    for ext in (".yaml", ".yml"):
        fp = schemas_dir / f"{schema_id}{ext}"
        if fp.exists() and fp.is_file():
            data = yaml.safe_load(fp.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError(f"Stat schema '{schema_id}' is not a YAML mapping")
            return data
    raise FileNotFoundError(
        f"Stat schema '{schema_id}' not found in {schemas_dir}. "
        f"Available schemas: {list_stat_schema_ids()}"
    )


def list_stat_schema_ids() -> list[str]:
    """Return the IDs of all available stat schemas."""
    schemas_dir = _schemas_dir()
    if not schemas_dir.exists():
        return []
    ids: list[str] = []
    for fp in sorted(schemas_dir.glob("*.yaml")) + sorted(schemas_dir.glob("*.yml")):
        ids.append(fp.stem)
    return ids


def get_stat_ids(schema_id: str) -> list[str]:
    """Return just the stat IDs defined in a schema (convenience helper)."""
    schema = load_stat_schema(schema_id)
    return [s["id"] for s in schema.get("stats", []) if isinstance(s, dict) and s.get("id")]


def get_stat_defaults(schema_id: str) -> dict[str, int]:
    """Return a mapping of stat_id -> default_value for the given schema."""
    schema = load_stat_schema(schema_id)
    return {
        s["id"]: s.get("default", 1)
        for s in schema.get("stats", [])
        if isinstance(s, dict) and s.get("id")
    }


def clear_stat_schema_cache() -> None:
    """Invalidate the in-process schema cache (useful in tests)."""
    load_stat_schema.cache_clear()
