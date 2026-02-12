"""Canonical ingestion path resolution for portable data bundles.

A single env var (``STORYTELLER_INGEST_ROOT``) can relocate lore/style/manifests
and LanceDB data to any folder, making ingestion assets plug-and-play across
repos/machines.
"""
from __future__ import annotations

import os
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_INGEST_ROOT = _PROJECT_ROOT / "data"


def ingest_root() -> Path:
    """Return the root folder that holds ingestion inputs + vector DB."""
    raw = os.environ.get("STORYTELLER_INGEST_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return _DEFAULT_INGEST_ROOT.resolve()


def lore_dir() -> Path:
    return ingest_root() / "lore"


def style_dir() -> Path:
    return ingest_root() / "style"


def manifests_dir() -> Path:
    return ingest_root() / "manifests"


def lancedb_dir() -> Path:
    return ingest_root() / "lancedb"



def standard_dirs() -> list[Path]:
    """Return standard ingestion directories in creation order."""
    return [ingest_root(), lore_dir(), style_dir(), manifests_dir(), lancedb_dir()]

def ensure_layout() -> list[Path]:
    """Create standard ingestion layout. Returns created/existing dirs."""
    dirs = standard_dirs()
    for p in dirs:
        p.mkdir(parents=True, exist_ok=True)
    return dirs



def static_dirs(project_root: Path | None = None) -> list[Path]:
    """Project static content directories (not part of portable ingest bundle)."""
    root = project_root or _PROJECT_ROOT
    return [root / "data" / "static", root / "data" / "static" / "era_packs"]
