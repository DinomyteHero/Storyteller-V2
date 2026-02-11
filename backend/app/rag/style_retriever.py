"""Style retrieval from LanceDB style table."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, List

from backend.app.config import EMBEDDING_MODEL, STYLE_TABLE_NAME, resolve_vectordb_path
from backend.app.rag._cache import get_encoder, get_lancedb_table
from backend.app.rag.utils import assert_vector_dim, safe_filter_token
from backend.app.core.warnings import add_warning

logger = logging.getLogger(__name__)

# Backward-compat aliases
_safe_filter_token = safe_filter_token
_assert_vector_dim = assert_vector_dim


def retrieve_style(
    query: str,
    top_k: int = 5,
    db_path: str | Path | None = None,
    table_name: str | None = None,
    warnings: list[str] | None = None,
    style_tags: list[str] | None = None,
) -> List[dict[str, Any]]:
    """
    Retrieve top-k style chunks by semantic similarity.

    Args:
        query: Search text.
        top_k: Number of results (default 5).
        db_path: LanceDB path (default: VECTORDB_PATH env or 'lancedb').
        table_name: Style table name (default: STYLE_TABLE_NAME from config).
        style_tags: Optional tag filter. When provided, results whose tags
            overlap with *style_tags* are boosted (sorted first), then
            remaining results follow sorted by score.

    Returns:
        List of dicts with: text, source_title, tags (list[str]), score (if available).
    """
    db_path = resolve_vectordb_path(db_path)
    table_name = table_name or STYLE_TABLE_NAME

    if not db_path.exists():
        logger.warning("LanceDB path does not exist: %s. Run style ingestion first.", db_path)
        add_warning(warnings, "Style retrieval failed: continuing without style context.")
        return []

    try:
        table = get_lancedb_table(db_path, table_name)
    except Exception as e:
        logger.warning("Could not open style table %s: %s", table_name, e)
        add_warning(warnings, "Style retrieval failed: continuing without style context.")
        return []

    _assert_vector_dim(table, str(table_name))
    encoder = get_encoder(EMBEDDING_MODEL)
    query_vector = encoder.encode([query], show_progress_bar=False)[0]
    if hasattr(query_vector, "tolist"):
        query_vector = query_vector.tolist()

    try:
        results = table.search(query_vector).limit(top_k)
        tbl = results.to_arrow()
    except Exception as e:
        logger.warning("Style search failed: %s", e)
        add_warning(warnings, "Style retrieval failed: continuing without style context.")
        return []

    if tbl.num_rows == 0:
        return []

    d = tbl.to_pydict()
    out: List[dict[str, Any]] = []
    for i in range(tbl.num_rows):
        def _v(name: str, default: Any = ""):
            col = d.get(name)
            if col is None:
                return default
            return col[i] if i < len(col) else default

        dist = _v("_distance", 0.0)
        score = float(1.0 - (dist if dist is not None else 0.0))
        tags_json = _v("tags_json", "[]")
        try:
            tags = json.loads(tags_json) if isinstance(tags_json, str) else list(tags_json or [])
        except Exception as e:
            logger.debug("Failed to parse style tags_json: %s", e)
            tags = []
        out.append({
            "text": _v("text") or "",
            "source_title": _v("source_title") or "",
            "tags": tags,
            "score": score,
        })

    # Optional style_tags boost: prefer chunks whose tags overlap with requested tags
    if style_tags and out:
        requested = {t.lower() for t in style_tags if t}
        if requested:
            def _tag_overlap(chunk: dict) -> int:
                chunk_tags = {t.lower() for t in (chunk.get("tags") or []) if t}
                return len(chunk_tags & requested)
            out.sort(key=lambda c: (-_tag_overlap(c), -(c.get("score") or 0.0)))

    return out


def _parse_rows(tbl) -> List[dict[str, Any]]:
    """Parse Arrow table rows into style chunk dicts."""
    if tbl.num_rows == 0:
        return []
    d = tbl.to_pydict()
    out: List[dict[str, Any]] = []
    for i in range(tbl.num_rows):
        def _v(name: str, default: Any = ""):
            col = d.get(name)
            if col is None:
                return default
            return col[i] if i < len(col) else default

        dist = _v("_distance", 0.0)
        score = float(1.0 - (dist if dist is not None else 0.0))
        tags_json = _v("tags_json", "[]")
        try:
            tags = json.loads(tags_json) if isinstance(tags_json, str) else list(tags_json or [])
        except Exception:
            tags = []
        out.append({
            "text": _v("text") or "",
            "source_title": _v("source_title") or "",
            "tags": tags,
            "score": score,
            "id": _v("id") or "",
        })
    return out


def _apply_tag_boost(out: List[dict[str, Any]], style_tags: list[str] | None) -> None:
    """In-place sort to boost chunks whose tags overlap with requested style_tags."""
    if not style_tags or not out:
        return
    requested = {t.lower() for t in style_tags if t}
    if not requested:
        return

    def _tag_overlap(chunk: dict) -> int:
        chunk_tags = {t.lower() for t in (chunk.get("tags") or []) if t}
        return len(chunk_tags & requested)

    out.sort(key=lambda c: (-_tag_overlap(c), -(c.get("score") or 0.0)))


def retrieve_style_layered(
    query: str,
    era_id: str | None = None,
    genre: str | None = None,
    archetype: str | None = None,
    top_k: int = 5,
    db_path: str | Path | None = None,
    table_name: str | None = None,
    warnings: list[str] | None = None,
    style_tags: list[str] | None = None,
) -> List[dict[str, Any]]:
    """Retrieve style chunks with 4-lane layered retrieval.

    Lane 0 (ALWAYS): Star Wars base style — foundational prose directives.
    Lane 1 (when era set): Era-specific style (Rebellion grit, Legacy intrigue, etc.).
    Lane 2 (when genre set): Genre overlay (noir, samurai, etc.) — additive, never replaces base.
    Lane 3 (when archetype set): Narrative archetype (Hero's Journey, etc.).

    Star Wars is always the foundation. Genre and archetype modify but never replace it.

    Args:
        query: Search text.
        era_id: Canonical era key (e.g. ``"REBELLION"``).
        genre: Genre slug (e.g. ``"noir_detective"``).
        archetype: Archetype slug (e.g. ``"heros_journey"``).
        top_k: Total results to return after merge (default 5).
        db_path: LanceDB path override.
        table_name: Style table name override.
        warnings: Mutable list for degradation warnings.
        style_tags: Optional tag-boost list (applied after merge).

    Returns:
        List of style chunk dicts (text, source_title, tags, score).
    """
    from backend.app.rag.style_mappings import (
        BASE_SOURCE_TITLES,
        era_source_titles,
        genre_source_title,
        archetype_source_title,
    )

    db_path = resolve_vectordb_path(db_path)
    table_name = table_name or STYLE_TABLE_NAME

    if not db_path.exists():
        logger.warning("LanceDB path does not exist: %s. Run style ingestion first.", db_path)
        add_warning(warnings, "Style retrieval failed: continuing without style context.")
        return []

    try:
        table = get_lancedb_table(db_path, table_name)
    except Exception as e:
        logger.warning("Could not open style table %s: %s", table_name, e)
        add_warning(warnings, "Style retrieval failed: continuing without style context.")
        return []

    _assert_vector_dim(table, str(table_name))
    encoder = get_encoder(EMBEDDING_MODEL)
    query_vector = encoder.encode([query], show_progress_bar=False)[0]
    if hasattr(query_vector, "tolist"):
        query_vector = query_vector.tolist()

    merged: List[dict[str, Any]] = []
    seen_ids: set[str] = set()

    def _run_lane(source_filter: str, limit: int) -> None:
        try:
            tbl = table.search(query_vector).where(source_filter).limit(limit).to_arrow()
            for row in _parse_rows(tbl):
                rid = row.get("id") or row.get("text", "")[:60]
                if rid not in seen_ids:
                    seen_ids.add(rid)
                    merged.append(row)
        except Exception as e:
            logger.debug("Style lane search failed (%s): %s", source_filter, e)

    # Lane 0: Star Wars base style (ALWAYS active)
    safe_base_sources = [s for s in (_safe_filter_token(src) for src in BASE_SOURCE_TITLES) if s]
    if safe_base_sources:
        escaped = ", ".join(f"'{s.replace(chr(39), chr(39)+chr(39))}'" for s in safe_base_sources)
        _run_lane(f"source_title IN ({escaped})", 2)

    # Lane 1: era baseline
    era_sources = era_source_titles(era_id) if era_id else []
    safe_era_sources = [s for s in (_safe_filter_token(src) for src in era_sources) if s]
    if safe_era_sources:
        escaped = ", ".join(f"'{s.replace(chr(39), chr(39)+chr(39))}'" for s in safe_era_sources)
        _run_lane(f"source_title IN ({escaped})", top_k)

    # Lane 2: genre overlay
    genre_src = _safe_filter_token(genre_source_title(genre)) if genre else None
    if genre_src:
        safe = genre_src.replace("'", "''")
        _run_lane(f"source_title = '{safe}'", max(top_k // 2, 2))

    # Lane 3: narrative archetype overlay
    arch_src = _safe_filter_token(archetype_source_title(archetype)) if archetype else None
    if arch_src:
        safe = arch_src.replace("'", "''")
        _run_lane(f"source_title = '{safe}'", max(top_k // 2, 2))

    # If no lanes produced results, fall back to unfiltered search
    if not merged:
        return retrieve_style(
            query, top_k=top_k, db_path=db_path, table_name=table_name,
            warnings=warnings, style_tags=style_tags,
        )

    # Sort merged results by score descending, truncate to top_k
    merged.sort(key=lambda c: -(c.get("score") or 0.0))
    merged = merged[:top_k]

    _apply_tag_boost(merged, style_tags)
    return merged
