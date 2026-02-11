"""Shared configuration constants used by backend and ingestion."""
from __future__ import annotations

import os
from pathlib import Path


def _env_flag(name: str, default: bool = False) -> bool:
    """Read boolean env flag."""
    val = os.environ.get(name, "").strip().lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "on")


# RAG embedding: model name + expected vector dimension (LanceDB tables must match)
# Override: EMBEDDING_MODEL, EMBEDDING_DIMENSION. If you change model, run scripts/rebuild_lancedb.py
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2").strip()
_emb_dim = os.environ.get("EMBEDDING_DIMENSION", "").strip()
EMBEDDING_DIMENSION = int(_emb_dim) if _emb_dim else 384

# Project root: resolve relative to this file's location
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Data directories (shared) - use absolute paths to avoid CWD dependency
STYLE_DATA_DIR = os.environ.get("STYLE_DATA_DIR", str(_PROJECT_ROOT / "data" / "style"))
LORE_DATA_DIR = os.environ.get("LORE_DATA_DIR", str(_PROJECT_ROOT / "data" / "lore"))
MANIFESTS_DIR = os.environ.get("MANIFESTS_DIR", str(_PROJECT_ROOT / "data" / "manifests"))
ERA_PACK_DIR = os.environ.get("ERA_PACK_DIR", str(_PROJECT_ROOT / "data" / "static" / "era_packs"))

# Feature flags (shared)
ENABLE_CHARACTER_FACETS = _env_flag("ENABLE_CHARACTER_FACETS", default=False)

# Era pack validation: lenient mode logs warnings instead of failing on missing references
# Allows WIP era packs to load while data quality is being improved
ERA_PACK_LENIENT_VALIDATION = _env_flag("ERA_PACK_LENIENT_VALIDATION", default=True)
