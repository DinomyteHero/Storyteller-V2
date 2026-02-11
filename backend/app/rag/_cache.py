"""Module-level caches for SentenceTransformer and LanceDB connections.

Single-user local app: simple dict singletons are sufficient.
Thread-safety is not required (single-worker Ollama-only).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from shared.cache import get_cache_value, clear_cache

logger = logging.getLogger(__name__)

# --- Cache keys (shared registry) ---
_ENCODER_CACHE_KEY = "rag_encoder_cache"
_DB_CACHE_KEY = "rag_db_cache"
_TABLE_CACHE_KEY = "rag_table_cache"


def _encoder_cache() -> dict[str, Any]:
    return get_cache_value(_ENCODER_CACHE_KEY, dict)


def get_encoder(model_name: str) -> Any:
    """Return a cached SentenceTransformer instance for the given model name."""
    cache = _encoder_cache()
    if model_name in cache:
        return cache[model_name]
    if os.environ.get("STORYTELLER_DUMMY_EMBEDDINGS", "").strip().lower() in ("1", "true", "yes"):
        from backend.app.config import EMBEDDING_DIMENSION
        class _DummyEncoder:
            def encode(self, texts, show_progress_bar: bool = False):
                return [[0.0] * EMBEDDING_DIMENSION for _ in texts]
        enc = _DummyEncoder()
        cache[model_name] = enc
        logger.info("Using dummy encoder for model: %s", model_name)
        return enc
    try:
        from sentence_transformers import SentenceTransformer
        enc = SentenceTransformer(model_name)
        cache[model_name] = enc
        logger.info("Cached SentenceTransformer for model: %s", model_name)
        return enc
    except ImportError as e:
        raise RuntimeError(
            "sentence-transformers required for retrieval. pip install sentence-transformers"
        ) from e


def _db_cache() -> dict[str, Any]:
    return get_cache_value(_DB_CACHE_KEY, dict)


def get_lancedb_connection(db_path: str | Path) -> Any:
    """Return a cached lancedb connection for the given path."""
    key = str(db_path)
    cache = _db_cache()
    if key in cache:
        return cache[key]
    import lancedb
    conn = lancedb.connect(key)
    cache[key] = conn
    logger.info("Cached LanceDB connection for: %s", key)
    return conn


def _table_cache() -> dict[tuple[str, str], Any]:
    return get_cache_value(_TABLE_CACHE_KEY, dict)


def get_lancedb_table(db_path: str | Path, table_name: str) -> Any:
    """Return a cached table handle. Raises if table doesn't exist."""
    key = (str(db_path), table_name)
    cache = _table_cache()
    if key in cache:
        return cache[key]
    conn = get_lancedb_connection(db_path)
    table = conn.open_table(table_name)
    cache[key] = table
    logger.info("Cached LanceDB table: %s/%s", db_path, table_name)
    return table


def clear_caches() -> None:
    """Clear all caches (useful for testing)."""
    for key in (_ENCODER_CACHE_KEY, _DB_CACHE_KEY, _TABLE_CACHE_KEY):
        cache = get_cache_value(key, dict)
        cache.clear()
        clear_cache(key)
