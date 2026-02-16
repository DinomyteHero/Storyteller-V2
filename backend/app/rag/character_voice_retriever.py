"""Character voice snippet retrieval from LanceDB. Era-scoped with fallback widening."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.config import (
    CHARACTER_VOICE_TABLE_NAME,
    EMBEDDING_MODEL,
    resolve_vectordb_path,
)
from backend.app.rag._cache import get_encoder
from backend.app.rag.vector_store import create_vector_store, LanceDBStore
from backend.app.rag.utils import assert_vector_dim, esc, safe_filter_token
from backend.app.core.warnings import add_warning

logger = logging.getLogger(__name__)

# Backward-compat aliases
_assert_vector_dim = assert_vector_dim
_esc = esc
_safe_filter_token = safe_filter_token


@dataclass
class VoiceSnippet:
    """A single voice snippet for a character."""
    character_id: str
    era: str
    text: str
    chunk_id: str = ""


def get_voice_snippets(
    character_ids: list[str],
    era: str,
    k: int = 6,
    db_path: str | Path | None = None,
    table_name: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, list[VoiceSnippet]]:
    """
    Get top-k voice snippets per character, filtered by (character_id, era).

    Fallback logic:
    - First: filter by (character_id, era). If >= k/2 results per character, use those.
    - If < k/2: widen to (character_id, any era).
    - If still not enough: return what we have (do not guess).
    - If table does not exist: return {} (empty, no crash).

    Returns:
        dict mapping character_id -> list of VoiceSnippet (up to k per character).
    """
    if not character_ids:
        return {}
    if not era or not str(era).strip():
        return {str(cid).strip(): [] for cid in character_ids if cid}

    db_path = resolve_vectordb_path(db_path)
    table_name = table_name or CHARACTER_VOICE_TABLE_NAME

    if not db_path.exists():
        logger.debug("LanceDB path does not exist: %s. Voice snippets unavailable.", db_path)
        add_warning(warnings, "Voice retrieval failed: continuing without voice context.")
        return {str(cid).strip(): [] for cid in character_ids if cid}

    try:
        store = create_vector_store(db_path, table_name)
        schema_cols = store.get_schema_columns()
        if isinstance(store, LanceDBStore):
            _assert_vector_dim(store._get_table(), str(table_name))
    except Exception as e:
        logger.debug("Could not open character voice table %s: %s. Voice snippets unavailable.", table_name, e)
        add_warning(warnings, "Voice retrieval failed: continuing without voice context.")
        return {str(cid).strip(): [] for cid in character_ids if cid}
    if "character_id" not in schema_cols or "text" not in schema_cols:
        logger.debug("character_voice_chunks missing required columns. Voice snippets unavailable.")
        add_warning(warnings, "Voice retrieval failed: continuing without voice context.")
        return {str(cid).strip(): [] for cid in character_ids if cid}
    if "vector" not in schema_cols and "vec" not in schema_cols:
        logger.debug("character_voice_chunks missing vector column. Voice snippets unavailable.")
        add_warning(warnings, "Voice retrieval failed: continuing without voice context.")
        return {str(cid).strip(): [] for cid in character_ids if cid}

    has_era = "era" in schema_cols
    era_stripped = str(era).strip()
    cid_set = {str(c).strip() for c in character_ids if c}
    min_acceptable = max(1, k // 2)
    result: dict[str, list[VoiceSnippet]] = {cid: [] for cid in cid_set}

    try:
        encoder = get_encoder(EMBEDDING_MODEL)
    except Exception as ex:
        logger.debug("Could not load encoder for voice retrieval: %s", ex)
        add_warning(warnings, "Voice retrieval failed: continuing without voice context.")
        return result

    query_texts = [f"voice sample for {cid}" for cid in cid_set]
    try:
        vectors = encoder.encode(query_texts, show_progress_bar=False)
        if hasattr(vectors, "tolist"):
            vectors = vectors.tolist()
    except Exception as ex:
        logger.debug("Voice query embedding failed: %s", ex)
        add_warning(warnings, "Voice retrieval failed: continuing without voice context.")
        return result

    cid_to_vec = {cid: vec for cid, vec in zip(cid_set, vectors)}

    for cid in cid_set:
        vec = cid_to_vec.get(cid)
        if vec is None:
            result[cid] = []
            continue
        snippets = _search_snippets(
            store,
            vec,
            cid,
            era_stripped if has_era else "",
            k,
            warnings=warnings,
        )
        if has_era and len(snippets) < min_acceptable:
            widened = _search_snippets(
                store,
                vec,
                cid,
                "",
                k,
                warnings=warnings,
            )
            seen_texts = {s.text for s in snippets}
            for s in widened:
                if s.text not in seen_texts:
                    snippets.append(s)
                    seen_texts.add(s.text)
                if len(snippets) >= k:
                    break
        result[cid] = snippets[:k]

    return result


def _search_snippets(
    store: Any,
    vector: list[float],
    character_id: str,
    era: str,
    k: int,
    warnings: list[str] | None = None,
) -> list[VoiceSnippet]:
    """Vector search for snippets, optionally filtered by era."""
    safe_character_id = _safe_filter_token(character_id)
    safe_era = _safe_filter_token(era) if era else None
    if not safe_character_id:
        return []
    where_clauses = [f"character_id = '{_esc(safe_character_id)}'"]
    if safe_era:
        where_clauses.append(f"era = '{_esc(safe_era)}'")
    try:
        if isinstance(store, LanceDBStore):
            rows = store.search_multi_where(vector, top_k=k, where_clauses=where_clauses)
        else:
            rows = store.search(vector, top_k=k, where=" AND ".join(where_clauses))
    except Exception as ex:
        logger.debug("Voice search failed: %s", ex)
        add_warning(warnings, "Voice retrieval failed: continuing without voice context.")
        return []

    out: list[VoiceSnippet] = []
    for row in rows:
        text = (str(row.get("text", "") or "")).strip()
        if not text:
            continue
        row_era = (str(row.get("era", "") or "")).strip()
        chunk_id = str(row.get("chunk_id") or row.get("id") or "")
        out.append(VoiceSnippet(character_id=character_id, era=row_era, text=text, chunk_id=chunk_id))
    return out
