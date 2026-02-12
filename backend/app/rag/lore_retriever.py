"""Lore retrieval from LanceDB. LoreRetriever.query(text, filters={planet,faction,time_period,doc_type,section_kind,characters,related_npcs}, k=6)."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, List

from backend.app.config import LORE_TABLE_NAME, resolve_vectordb_path, EMBEDDING_MODEL
from backend.app.rag._cache import get_encoder, get_lancedb_table
from backend.app.rag.utils import assert_vector_dim, esc, safe_filter_token, safe_filter_tokens
from backend.app.core.warnings import add_warning

logger = logging.getLogger(__name__)

# Backward-compat aliases for any external consumers
_safe_filter_token = safe_filter_token
_safe_filter_tokens = safe_filter_tokens
_esc = esc
_assert_vector_dim = assert_vector_dim


def _parse_list_json(val: Any) -> List[str]:
    """Parse list from column (json string or list). Return [] on error or missing."""
    if val is None or val == "":
        return []
    if isinstance(val, list):
        return [str(x) for x in val]
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            return [str(x) for x in parsed] if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError) as e:
            logger.debug("Failed to parse list json: %s", e)
            return []
    return []


def retrieve_lore(
    query: str,
    top_k: int = 6,
    era: str | None = None,
    source_type: str | None = None,
    time_period: str | None = None,
    planet: str | None = None,
    faction: str | None = None,
    doc_type: str | None = None,
    section_kind: str | None = None,
    doc_types: List[str] | None = None,
    section_kinds: List[str] | None = None,
    characters: str | List[str] | None = None,
    related_npcs: str | List[str] | None = None,
    setting_id: str | None = None,
    period_id: str | None = None,
    universe: str | None = None,
    source_title: str | None = None,
    source_titles: List[str] | None = None,
    chapter_index_min: int | None = None,
    chapter_index_max: int | None = None,
    db_path: str | Path | None = None,
    table_name: str | None = None,
    warnings: list[str] | None = None,
) -> List[dict[str, Any]]:
    """
    Retrieve top-k lore chunks. Filters: era, source_type, time_period, planet, faction, doc_type, section_kind,
    doc_types (OR list), section_kinds (OR list), characters.
    Old DBs missing new columns are handled gracefully (filters skipped, no crash).
    """
    db_path = resolve_vectordb_path(db_path)
    table_name = table_name or LORE_TABLE_NAME

    if not db_path.exists():
        logger.warning("LanceDB path does not exist: %s. Run lore ingestion first.", db_path)
        add_warning(warnings, "Lore retrieval failed: continuing without lore context.")
        return []

    try:
        table = get_lancedb_table(db_path, table_name)
    except Exception as e:
        logger.warning("Could not open lore table %s: %s", table_name, e)
        add_warning(warnings, "Lore retrieval failed: continuing without lore context.")
        return []

    _assert_vector_dim(table, str(table_name))
    encoder = get_encoder(EMBEDDING_MODEL)
    query_vector = encoder.encode([query], show_progress_bar=False)[0]
    if hasattr(query_vector, "tolist"):
        query_vector = query_vector.tolist()

    schema_cols = {f.name for f in table.schema}
    char_filter = characters
    if isinstance(char_filter, str):
        char_filter = [char_filter] if char_filter.strip() else None
    elif isinstance(char_filter, list):
        char_filter = [c for c in char_filter if c and str(c).strip()] or None
    npc_filter = related_npcs
    if isinstance(npc_filter, str):
        npc_filter = [npc_filter] if npc_filter.strip() else None
    elif isinstance(npc_filter, list):
        npc_filter = [n for n in npc_filter if n and str(n).strip()] or None

    try:
        q = table.search(query_vector).limit(top_k)
        era = _safe_filter_token(era)
        time_period = _safe_filter_token(time_period)
        planet = _safe_filter_token(planet)
        faction = _safe_filter_token(faction)
        source_type = _safe_filter_token(source_type)
        doc_type = _safe_filter_token(doc_type)
        section_kind = _safe_filter_token(section_kind)
        setting_id = _safe_filter_token(setting_id)
        period_id = _safe_filter_token(period_id)
        universe = _safe_filter_token(universe)
        source_title = _safe_filter_token(source_title)
        safe_doc_types = _safe_filter_tokens(doc_types)
        safe_section_kinds = _safe_filter_tokens(section_kinds)
        safe_char_filter = _safe_filter_tokens(char_filter)
        safe_npc_filter = _safe_filter_tokens(npc_filter)
        safe_source_titles = _safe_filter_tokens(source_titles)

        if setting_id and "setting_id" in schema_cols:
            q = q.where(f"setting_id = '{_esc(setting_id)}'")
        if period_id and "period_id" in schema_cols:
            q = q.where(f"period_id = '{_esc(period_id)}'")
        if universe and "universe" in schema_cols:
            q = q.where(f"universe = '{_esc(universe)}'")
        if "source" in schema_cols:
            if safe_source_titles:
                parts = [f"source = '{_esc(s)}'" for s in safe_source_titles]
                if parts:
                    q = q.where(f"({' OR '.join(parts)})")
            elif source_title:
                q = q.where(f"source = '{_esc(source_title)}'")
        elif "book_title" in schema_cols:
            if safe_source_titles:
                parts = [f"book_title = '{_esc(s)}'" for s in safe_source_titles]
                if parts:
                    q = q.where(f"({' OR '.join(parts)})")
            elif source_title:
                q = q.where(f"book_title = '{_esc(source_title)}'")
        if chapter_index_min is not None and "chapter_index" in schema_cols:
            q = q.where(f"chapter_index >= {int(chapter_index_min)}")
        if chapter_index_max is not None and "chapter_index" in schema_cols:
            q = q.where(f"chapter_index <= {int(chapter_index_max)}")
        if era and "era" in schema_cols:
            q = q.where(f"era = '{_esc(era)}'")
        if time_period and "time_period" in schema_cols:
            q = q.where(f"time_period = '{_esc(time_period)}'")
        if planet and "planet" in schema_cols:
            q = q.where(f"planet = '{_esc(planet)}'")
        if faction and "faction" in schema_cols:
            q = q.where(f"faction = '{_esc(faction)}'")
        if source_type and "source_type" in schema_cols:
            q = q.where(f"source_type = '{_esc(source_type)}'")
        if "doc_type" in schema_cols:
            if safe_doc_types:
                parts = [f"doc_type = '{_esc(d)}'" for d in safe_doc_types]
                if parts:
                    q = q.where(f"({' OR '.join(parts)})")
            elif doc_type:
                q = q.where(f"doc_type = '{_esc(doc_type)}'")
        if "section_kind" in schema_cols:
            if safe_section_kinds:
                parts = [f"section_kind = '{_esc(s)}'" for s in safe_section_kinds]
                if parts:
                    q = q.where(f"({' OR '.join(parts)})")
            elif section_kind:
                q = q.where(f"section_kind = '{_esc(section_kind)}'")
        if safe_char_filter:
            if "characters_json" in schema_cols:
                parts = [f"characters_json LIKE '%\"{_esc(c)}\"%'" for c in safe_char_filter]
                q = q.where(f"({' OR '.join(parts)})")
            elif "characters" in schema_cols:
                parts = [f"list_contains(characters, '{_esc(c)}')" for c in safe_char_filter]
                q = q.where(f"({' OR '.join(parts)})")
        if safe_npc_filter:
            if "related_npcs_json" in schema_cols:
                parts = [f"related_npcs_json LIKE '%\"{_esc(n)}\"%'" for n in safe_npc_filter]
                q = q.where(f"({' OR '.join(parts)})")
            elif "related_npcs" in schema_cols:
                parts = [f"list_contains(related_npcs, '{_esc(n)}')" for n in safe_npc_filter]
                q = q.where(f"({' OR '.join(parts)})")
        tbl = q.to_arrow()
    except Exception as e:
        logger.warning("Lore search failed: %s", e)
        add_warning(warnings, "Lore retrieval failed: continuing without lore context.")
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
        book_title = _v("book_title") or _v("source") or ""
        chapter_title = _v("chapter_title") or _v("chapter") or ""
        chunk_id = _v("chunk_id") or _v("id") or ""
        chars = _parse_list_json(_v("characters_json", None) or _v("characters", None))
        related = _parse_list_json(_v("related_npcs_json", None) or _v("related_npcs", None))
        metadata = {
            "era": _v("era") or "",
            "time_period": _v("time_period") or "",
            "setting_id": _v("setting_id") or "",
            "period_id": _v("period_id") or "",
            "planet": _v("planet") or "",
            "faction": _v("faction") or "",
            "source_type": _v("source_type") or "",
            "doc_type": _v("doc_type") or "",
            "section_kind": _v("section_kind") or "",
            "characters": chars,
            "related_npcs": related,
            "book_title": book_title,
            "chapter_title": chapter_title or None,
            "chunk_id": chunk_id,
            "universe": _v("universe") or "",
        }
        out.append({
            "text": _v("text") or "",
            "source_title": book_title,
            "chapter_title": chapter_title or None,
            "chunk_id": chunk_id,
            "metadata": metadata,
            "score": score,
        })
    return out


class LoreRetriever:
    """RAG lore retriever with metadata filters."""

    def __init__(self, db_path: str | Path | None = None, table_name: str | None = None):
        self.db_path = resolve_vectordb_path(db_path)
        self.table_name = table_name or LORE_TABLE_NAME

    def query(
        self,
        text: str,
        filters: dict[str, Any] | None = None,
        k: int = 6,
        warnings: list[str] | None = None,
    ) -> List[dict[str, Any]]:
        """Query lore. filters: {planet, faction, time_period, era, doc_type, section_kind,
        doc_types (list), section_kinds (list), characters, related_npcs,
        source_title, source_titles, chapter_index_min, chapter_index_max} (optional).
        characters/related_npcs can be a string or list of strings for contains-match."""
        filters = filters or {}
        chars = filters.get("characters")
        related = filters.get("related_npcs")
        return retrieve_lore(
            text,
            top_k=k,
            time_period=filters.get("time_period"),
            planet=filters.get("planet"),
            faction=filters.get("faction"),
            era=filters.get("era"),
            source_type=filters.get("source_type"),
            doc_type=filters.get("doc_type"),
            section_kind=filters.get("section_kind"),
            doc_types=filters.get("doc_types"),
            section_kinds=filters.get("section_kinds"),
            characters=chars,
            related_npcs=related,
            setting_id=filters.get("setting_id"),
            period_id=filters.get("period_id"),
            universe=filters.get("universe"),
            source_title=filters.get("source_title"),
            source_titles=filters.get("source_titles"),
            chapter_index_min=filters.get("chapter_index_min"),
            chapter_index_max=filters.get("chapter_index_max"),
            db_path=self.db_path,
            table_name=self.table_name,
            warnings=warnings,
        )
