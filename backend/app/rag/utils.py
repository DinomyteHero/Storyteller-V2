"""Shared RAG utility functions (filter tokens, vector dim checks, SQL escaping)."""
from __future__ import annotations

import re
from typing import Any

from backend.app.config import EMBEDDING_DIMENSION, EMBEDDING_MODEL

_FILTER_TOKEN_RE = re.compile(r"^[A-Za-z0-9 _:/.\-]{1,120}$")


def safe_filter_token(value: Any) -> str | None:
    """Sanitise a single filter value for LanceDB where clauses."""
    token = str(value or "").strip()
    if not token:
        return None
    if not _FILTER_TOKEN_RE.fullmatch(token):
        return None
    return token


def safe_filter_tokens(values: list[Any] | None) -> list[str]:
    """Sanitise a list of filter values, dropping invalid entries."""
    if not values:
        return []
    out: list[str] = []
    for value in values:
        token = safe_filter_token(value)
        if token:
            out.append(token)
    return out


def esc(token: str) -> str:
    """Escape single quotes for LanceDB SQL-style filters."""
    return str(token).replace("'", "''")


def assert_vector_dim(table, table_name: str) -> None:
    """Fail fast if table vector dimension does not match expected."""
    for f in table.schema:
        if f.name in ("vector", "vec"):
            vt = f.type
            if hasattr(vt, "list_size") and vt.list_size >= 0:
                if vt.list_size != EMBEDDING_DIMENSION:
                    raise ValueError(
                        f"Vector dimension mismatch: table '{table_name}' has {vt.list_size}d vectors, "
                        f"but EMBEDDING_DIMENSION={EMBEDDING_DIMENSION} (model {EMBEDDING_MODEL}). "
                        "Run scripts/rebuild_lancedb.py after changing embeddings."
                    )
            break
