"""LanceDB store for ingestion: (id, vector, text, metadata fields).

Unified schema supports both novel ingestion (ingest.py) and enriched lore
ingestion (ingest_lore.py) in one table. Safe table creation: never overwrites
unless allow_overwrite=True (for rebuild scripts).

Idempotency: chunks with duplicate IDs are skipped on add_chunks.
Chunk IDs should be stable content hashes (see stable_chunk_id).
"""
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import List, Optional

import lancedb
import pyarrow as pa

from shared.config import EMBEDDING_DIMENSION
from ingestion.embedding import encode as embed_texts
from shared.lore_metadata import default_doc_type, default_section_kind, default_characters

logger = logging.getLogger(__name__)

TABLE_NAME = "lore_chunks"

# Chunk ID scheme version — stored in manifests so we can detect mismatches.
# v1: doc_id omitted (empty string)  — pre-hardening.
# v2: doc_id = file_doc_id(path)     — SHA-256 of resolved absolute path.
# v3: doc_id = file_doc_id(path, input_dir) — SHA-256 of POSIX relative
#     path + file size.  Portable across machines and folder moves as long
#     as the relative layout under input_dir stays the same.
CHUNK_ID_SCHEME = "v3"

# Embedding batch size for large ingestion runs (configurable via env var)
_EMBED_BATCH_SIZE = int(os.environ.get("EMBED_BATCH_SIZE", "128"))


def file_doc_id(file_path: Path | str, input_dir: Path | str | None = None) -> str:
    """Derive a stable, portable doc_id from a file path.

    Scheme (v3):
      1. Compute a *relative* POSIX path from *input_dir* (the ingestion
         root).  Using forward slashes and relative paths makes the ID
         identical on Windows, macOS, and Linux and survives folder moves
         as long as the layout under *input_dir* is preserved.
      2. Append the file size in bytes as a lightweight content fingerprint
         so that replacing a file with different content invalidates the
         old doc_id (without reading the full file).
      3. SHA-256 the ``"{rel_posix_path}|{size}"`` payload, truncated to
         16 hex chars.

    Falls back to the resolved absolute path when *input_dir* is ``None``
    or the file is not under *input_dir*.
    """
    fp = Path(file_path).resolve()
    if input_dir is not None:
        root = Path(input_dir).resolve()
        try:
            rel = fp.relative_to(root).as_posix()
        except ValueError:
            # file_path not under input_dir — fall back to absolute
            rel = str(fp)
    else:
        rel = str(fp)
    try:
        size = fp.stat().st_size
    except OSError:
        size = 0
    payload = f"{rel}|{size}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def stable_chunk_id(
    text: str,
    source: str = "",
    chunk_index: int = 0,
    doc_id: str = "",
) -> str:
    """Generate a stable, content-based chunk ID.

    Uses SHA-256 of (doc_id + source + chunk_index + content_hash) truncated
    to 16 hex chars.  Including *doc_id* prevents collisions when different
    documents contain identical boilerplate (e.g. copyright pages).  The
    content hash is computed separately so position and identity are both
    encoded.

    Args:
        text: Chunk text (used for content hash).
        source: Filename / title of the source document.
        chunk_index: Position of the chunk within the document.
        doc_id: Stable document identifier — use :func:`file_doc_id` for
                file-based ingestion.
    """
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    payload = f"{doc_id}|{source}|{chunk_index}|{content_hash}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

# Message shown when open_table fails for non-missing-table reasons
_REBUILD_HINT = (
    "If the table schema changed (e.g. embedding dimension), "
    "run: python scripts/rebuild_lancedb.py --db <db_path>"
)


def _characters_to_json(chars: list) -> str:
    """Serialize characters list to JSON string for storage (max compatibility)."""
    if not chars:
        return "[]"
    return json.dumps([str(c) for c in chars])


def _related_npcs_to_json(npcs: list) -> str:
    """Serialize related_npcs list to JSON string for storage (max compatibility)."""
    if not npcs:
        return "[]"
    return json.dumps([str(n) for n in npcs])


def _entities_to_json(entities: dict | None) -> str:
    """Serialize entities dict to JSON string for storage (max compatibility)."""
    if not entities:
        return "{}"
    return json.dumps(entities)


def _chunk_to_row(chunk: dict, embedding: List[float]) -> dict:
    """Build a LanceDB row from chunk dict and its embedding.

    Supports both canonical {text, metadata} and legacy flat chunks.
    New unified fields: collection, level, parent_id, source, chapter, planet, faction.
    """
    m = chunk.get("metadata") or {}
    era = m.get("era", "")
    time_period = m.get("time_period", era)  # canonical: store both for backward compat
    chars = m.get("characters", default_characters())
    related_npcs = m.get("related_npcs") or []

    # source: filename/title; fallback to book_title for novel chunks
    source = m.get("source", "")
    if not source:
        source = m.get("book_title", "") or chunk.get("source", "")

    # chapter: can map from chapter_title
    chapter = m.get("chapter", "")
    if not chapter:
        chapter = m.get("chapter_title", "") or ""

    chunk_id_val = m.get("chunk_id", chunk.get("chunk_id", chunk.get("id", "")))
    entities_json = m.get("entities_json") or _entities_to_json(m.get("entities"))
    return {
        "id": str(chunk_id_val) if chunk_id_val else "",
        "vector": embedding,
        "text": chunk["text"],
        "era": era,
        "time_period": time_period,
        "source_type": m.get("source_type", ""),
        "book_title": m.get("book_title", ""),
        "chapter_title": m.get("chapter_title") or "",
        "chapter_index": m.get("chapter_index") if m.get("chapter_index") is not None else -1,
        "chunk_id": str(chunk_id_val) if chunk_id_val else "",
        "chunk_index": m.get("chunk_index", chunk.get("chunk_index", 0)),
        "doc_type": m.get("doc_type", default_doc_type()),
        "section_kind": m.get("section_kind", default_section_kind()),
        "characters_json": _characters_to_json(chars),
        "related_npcs_json": _related_npcs_to_json(related_npcs),
        # Unified superset fields for lore ingestion
        "collection": m.get("collection", ""),
        "level": m.get("level", ""),
        "parent_id": str(m.get("parent_id", chunk.get("parent_id", "")) or ""),
        "source": source,
        "chapter": chapter,
        "planet": m.get("planet", ""),
        "faction": m.get("faction", ""),
        "entities_json": entities_json,
        "summary_1s": m.get("summary_1s", ""),
        "injection_risk": m.get("injection_risk", ""),
        "timeline_start": m.get("timeline_start", ""),
        "timeline_end": m.get("timeline_end", ""),
        "timeline_confidence": m.get("timeline_confidence"),
    }


class LanceStore:
    """LanceDB-backed store: unified schema for novels + lore chunks."""

    def __init__(self, db_path: str, allow_overwrite: bool = False):
        self.db_path = Path(db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)
        self.db = lancedb.connect(str(self.db_path))
        self._allow_overwrite = allow_overwrite
        self._ensure_table()

    def _schema(self) -> pa.Schema:
        return pa.schema([
            pa.field("id", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), EMBEDDING_DIMENSION)),
            pa.field("text", pa.string()),
            pa.field("era", pa.string()),
            pa.field("time_period", pa.string()),
            pa.field("source_type", pa.string()),
            pa.field("book_title", pa.string()),
            pa.field("chapter_title", pa.string()),
            pa.field("chapter_index", pa.int32()),
            pa.field("chunk_id", pa.string()),
            pa.field("chunk_index", pa.int32()),
            pa.field("doc_type", pa.string()),
            pa.field("section_kind", pa.string()),
            pa.field("characters_json", pa.string()),
            pa.field("related_npcs_json", pa.string()),
            pa.field("collection", pa.string()),
            pa.field("level", pa.string()),
            pa.field("parent_id", pa.string()),
            pa.field("source", pa.string()),
            pa.field("chapter", pa.string()),
            pa.field("planet", pa.string()),
            pa.field("faction", pa.string()),
            pa.field("entities_json", pa.string()),
            pa.field("summary_1s", pa.string()),
            pa.field("injection_risk", pa.string()),
            pa.field("timeline_start", pa.string()),
            pa.field("timeline_end", pa.string()),
            pa.field("timeline_confidence", pa.float32()),
        ])

    def _ensure_table(self) -> None:
        resp = self.db.list_tables()
        # lancedb >=0.6 returns a plain list of strings; older versions returned
        # an object with a .tables attribute.  Handle both.
        tables = resp.tables if hasattr(resp, "tables") else list(resp)
        table_exists = TABLE_NAME in tables
        if table_exists:
            try:
                self.table = self.db.open_table(TABLE_NAME)
                logger.info("Opened existing table %s", TABLE_NAME)
                return
            except Exception as e:
                if self._allow_overwrite:
                    logger.warning("Could not open table %s, dropping for rebuild: %s", TABLE_NAME, e)
                    self.db.drop_table(TABLE_NAME)
                    logger.info("Dropped table %s for rebuild", TABLE_NAME)
                else:
                    logger.exception("Could not open table %s", TABLE_NAME)
                    raise RuntimeError(
                        f"Could not open table {TABLE_NAME}: {e}. {_REBUILD_HINT}"
                    ) from e
        # Table doesn't exist, or we dropped it for rebuild: create with mode="create"
        self.table = self.db.create_table(
            TABLE_NAME, schema=self._schema(), mode="create"
        )
        logger.info("Created table %s", TABLE_NAME)

    # Local membership cache — avoids full-table scans.  Populated once on
    # first dedup call, then kept in sync as new chunks are added.
    _id_cache: set[str] | None = None

    def _load_id_cache(self) -> set[str]:
        """Lazily load all existing IDs into a local set (one-time cost)."""
        if self._id_cache is not None:
            return self._id_cache
        try:
            df = self.table.to_pandas(columns=["id"])
            if df.empty:
                self._id_cache = set()
            else:
                self._id_cache = set(df["id"].dropna().astype(str))
        except Exception as e:
            logger.debug("Failed to build ID cache; falling back to empty set: %s", e)
            self._id_cache = set()
        return self._id_cache

    def _existing_ids_for(self, candidate_ids: set[str]) -> set[str]:
        """Return the subset of *candidate_ids* already in the table.

        Uses the local membership cache instead of scanning the full table
        each time.  For very large tables this is O(len(candidate_ids))
        lookups against a Python set rather than O(table_rows).
        """
        cache = self._load_id_cache()
        return candidate_ids & cache

    def add_chunks(self, chunks: List[dict], *, dedupe: bool = True) -> dict:
        """Store chunks with embeddings. Returns {added: int, skipped: int}.

        Each chunk: {text, metadata} or {text, metadata, chunk_id}.
        If dedupe=True (default), chunks with IDs already in the table are skipped.
        Embeddings are computed in batches of _EMBED_BATCH_SIZE for memory safety.
        """
        if not chunks:
            return {"added": 0, "skipped": 0}

        # Collect candidate IDs for the incoming batch
        def _cid(c: dict) -> str:
            m = c.get("metadata") or {}
            return str(m.get("chunk_id", c.get("chunk_id", c.get("id", ""))))

        # Dedup: check only incoming IDs against the cache
        existing_ids: set[str] = set()
        if dedupe:
            candidate_ids = {_cid(c) for c in chunks} - {""}
            existing_ids = self._existing_ids_for(candidate_ids)

        # Filter out already-present chunks
        new_chunks = []
        skipped = 0
        for c in chunks:
            cid = _cid(c)
            if dedupe and cid and cid in existing_ids:
                skipped += 1
                continue
            new_chunks.append(c)

        if not new_chunks:
            logger.info("All %d chunks already exist (skipped)", skipped)
            return {"added": 0, "skipped": skipped}

        # Batch embedding + insertion
        schema_cols = {f.name for f in self.table.schema}
        total_added = 0

        for batch_start in range(0, len(new_chunks), _EMBED_BATCH_SIZE):
            batch = new_chunks[batch_start:batch_start + _EMBED_BATCH_SIZE]
            texts = [c["text"] for c in batch]
            embeddings = embed_texts(texts)
            full_rows = [_chunk_to_row(c, emb) for c, emb in zip(batch, embeddings)]
            rows = [{k: v for k, v in r.items() if k in schema_cols} for r in full_rows]
            self.table.add(rows)
            total_added += len(rows)
            # Keep local cache in sync
            if self._id_cache is not None:
                self._id_cache.update(r["id"] for r in rows if r.get("id"))

        logger.info(
            "Added %d chunks to %s (skipped %d duplicates)",
            total_added, self.db_path, skipped,
        )
        return {"added": total_added, "skipped": skipped}

    def search(
        self,
        query: str,
        k: int = 5,
        era: Optional[str] = None,
        source_type: Optional[str] = None,
    ) -> List[dict]:
        """Search by query text; optional filters era, source_type. Returns list of {text, metadata, score}."""
        query_vector = embed_texts(query)[0]
        try:
            r = self.table.search(query_vector).limit(k)
            if era:
                r = r.where(f"era = '{era}'")
            if source_type:
                r = r.where(f"source_type = '{source_type}'")
            df = r.to_pandas()
        except Exception as e:
            logger.warning("Search failed: %s", e)
            return []

        if df.empty:
            return []

        out = []
        for row in df.itertuples():
            score = 1.0 - getattr(row, "_distance", 0.0)
            metadata = {
                "era": getattr(row, "era", ""),
                "source_type": getattr(row, "source_type", ""),
                "book_title": getattr(row, "book_title", ""),
                "chapter_title": getattr(row, "chapter_title", ""),
                "chapter_index": getattr(row, "chapter_index", -1),
                "chunk_id": getattr(row, "chunk_id", ""),
                "chunk_index": getattr(row, "chunk_index", 0),
            }
            out.append({
                "text": getattr(row, "text", ""),
                "metadata": metadata,
                "score": score,
            })
        return out

    def delete_by_filter(
        self,
        *,
        era: Optional[str] = None,
        source: Optional[str] = None,
        doc_type: Optional[str] = None,
        collection: Optional[str] = None,
    ) -> int:
        """Delete rows matching filter criteria. Returns count of deleted rows.

        At least one filter must be specified. Uses LanceDB filter expressions.
        """
        conditions: list[str] = []
        if era:
            safe_era = era.replace("'", "''")
            conditions.append(f"era = '{safe_era}'")
        if source:
            safe_source = source.replace("'", "''")
            conditions.append(f"source = '{safe_source}'")
        if doc_type:
            safe_dt = doc_type.replace("'", "''")
            conditions.append(f"doc_type = '{safe_dt}'")
        if collection:
            safe_col = collection.replace("'", "''")
            conditions.append(f"collection = '{safe_col}'")
        if not conditions:
            raise ValueError("At least one filter (era, source, doc_type, collection) must be specified")
        where_clause = " AND ".join(conditions)
        # Count before delete
        try:
            df_before = self.table.to_pandas(columns=["id"])
            count_before = len(df_before)
        except Exception:
            count_before = 0
        self.table.delete(where_clause)
        # Count after delete
        try:
            df_after = self.table.to_pandas(columns=["id"])
            count_after = len(df_after)
        except Exception:
            count_after = 0
        deleted = max(0, count_before - count_after)
        # Invalidate ID cache
        self._id_cache = None
        logger.info("Deleted %d rows matching filter: %s", deleted, where_clause)
        return deleted
