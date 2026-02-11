"""SQLite-backed knowledge graph store.

Provides CRUD for entities, triples, summaries, and extraction checkpoints.
All writes use upsert semantics for idempotent extraction runs.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from backend.app.kg.predicates import VALID_PREDICATES, ENTITY_TYPES

logger = logging.getLogger(__name__)

_MIGRATION_FILE = Path(__file__).resolve().parent.parent / "db" / "migrations" / "0005_knowledge_graph.sql"


class KGStore:
    """SQLite-backed knowledge graph store."""

    def __init__(self, db_path: str | Path = ":memory:"):
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Apply the KG migration if tables don't exist."""
        cursor = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='kg_entities'"
        )
        if cursor.fetchone() is not None:
            return
        if _MIGRATION_FILE.exists():
            sql = _MIGRATION_FILE.read_text(encoding="utf-8")
        else:
            logger.warning("KG migration file not found at %s, using inline schema", _MIGRATION_FILE)
            sql = _INLINE_SCHEMA
        self.conn.executescript(sql)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ── Entities ──────────────────────────────────────────────────────

    def upsert_entity(
        self,
        entity_id: str,
        entity_type: str,
        canonical_name: str,
        era: str,
        properties: dict | None = None,
        source_book: str | None = None,
        confidence: float = 1.0,
    ) -> None:
        """Insert or update an entity. Merges source_books list and properties."""
        entity_type = entity_type.upper()
        if entity_type not in ENTITY_TYPES:
            logger.warning("Unknown entity_type %r for %r, storing anyway", entity_type, entity_id)

        properties = properties or {}
        now = datetime.now(timezone.utc).isoformat()

        existing = self.get_entity(entity_id)
        if existing is None:
            source_books = [source_book] if source_book else []
            self.conn.execute(
                "INSERT INTO kg_entities (id, entity_type, canonical_name, era, properties_json, "
                "source_books_json, confidence, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entity_id, entity_type, canonical_name, era,
                    json.dumps(properties), json.dumps(source_books),
                    confidence, now, now,
                ),
            )
        else:
            # Merge source_books
            existing_books = json.loads(existing["source_books_json"] or "[]")
            if source_book and source_book not in existing_books:
                existing_books.append(source_book)

            # Merge properties: union lists, keep most specific scalars
            existing_props = json.loads(existing["properties_json"] or "{}")
            merged_props = _merge_properties(existing_props, properties)

            # Keep highest confidence
            new_confidence = max(confidence, existing["confidence"])

            self.conn.execute(
                "UPDATE kg_entities SET properties_json=?, source_books_json=?, "
                "confidence=?, updated_at=? WHERE id=?",
                (
                    json.dumps(merged_props), json.dumps(existing_books),
                    new_confidence, now, entity_id,
                ),
            )
        self.conn.commit()

    def get_entity(self, entity_id: str) -> dict | None:
        """Get a single entity by ID."""
        row = self.conn.execute(
            "SELECT * FROM kg_entities WHERE id=?", (entity_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_entities_by_type(self, entity_type: str, era: str | None = None) -> list[dict]:
        """Get all entities of a given type, optionally filtered by era."""
        if era:
            rows = self.conn.execute(
                "SELECT * FROM kg_entities WHERE entity_type=? AND era=? ORDER BY canonical_name",
                (entity_type.upper(), era),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM kg_entities WHERE entity_type=? ORDER BY canonical_name",
                (entity_type.upper(),),
            ).fetchall()
        return [dict(r) for r in rows]

    def entity_count(self, era: str | None = None) -> int:
        if era:
            row = self.conn.execute("SELECT COUNT(*) FROM kg_entities WHERE era=?", (era,)).fetchone()
        else:
            row = self.conn.execute("SELECT COUNT(*) FROM kg_entities").fetchone()
        return row[0]

    # ── Triples ───────────────────────────────────────────────────────

    def upsert_triple(
        self,
        subject_id: str,
        predicate: str,
        object_id: str,
        era: str,
        source_book: str | None = None,
        source_chunk_id: str | None = None,
        confidence: float = 1.0,
        properties: dict | None = None,
    ) -> None:
        """Insert or increment weight on duplicate triple."""
        predicate = predicate.upper()
        if predicate not in VALID_PREDICATES:
            logger.warning("Unknown predicate %r, storing anyway", predicate)

        properties = properties or {}
        now = datetime.now(timezone.utc).isoformat()

        existing = self.conn.execute(
            "SELECT id, weight, confidence FROM kg_triples "
            "WHERE subject_id=? AND predicate=? AND object_id=?",
            (subject_id, predicate, object_id),
        ).fetchone()

        if existing is None:
            self.conn.execute(
                "INSERT INTO kg_triples (subject_id, predicate, object_id, era, source_book, "
                "source_chunk_id, confidence, weight, properties_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    subject_id, predicate, object_id, era, source_book,
                    source_chunk_id, confidence, 1.0, json.dumps(properties), now,
                ),
            )
        else:
            new_weight = existing["weight"] + 1.0
            new_confidence = max(confidence, existing["confidence"])
            self.conn.execute(
                "UPDATE kg_triples SET weight=?, confidence=?, source_book=?, "
                "source_chunk_id=? WHERE id=?",
                (new_weight, new_confidence, source_book, source_chunk_id, existing["id"]),
            )
        self.conn.commit()

    def get_triples_for_entity(
        self,
        entity_id: str,
        direction: str = "both",
        era: str | None = None,
    ) -> list[dict]:
        """Get triples where entity is subject, object, or both.

        Args:
            entity_id: The entity to query.
            direction: 'outgoing' (subject), 'incoming' (object), or 'both'.
            era: Optional era filter.
        """
        results = []
        if direction in ("outgoing", "both"):
            if era:
                rows = self.conn.execute(
                    "SELECT t.*, e.canonical_name AS object_name FROM kg_triples t "
                    "JOIN kg_entities e ON t.object_id = e.id "
                    "WHERE t.subject_id=? AND t.era=? ORDER BY t.weight DESC",
                    (entity_id, era),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT t.*, e.canonical_name AS object_name FROM kg_triples t "
                    "JOIN kg_entities e ON t.object_id = e.id "
                    "WHERE t.subject_id=? ORDER BY t.weight DESC",
                    (entity_id,),
                ).fetchall()
            results.extend(dict(r) for r in rows)
        if direction in ("incoming", "both"):
            if era:
                rows = self.conn.execute(
                    "SELECT t.*, e.canonical_name AS subject_name FROM kg_triples t "
                    "JOIN kg_entities e ON t.subject_id = e.id "
                    "WHERE t.object_id=? AND t.era=? ORDER BY t.weight DESC",
                    (entity_id, era),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT t.*, e.canonical_name AS subject_name FROM kg_triples t "
                    "JOIN kg_entities e ON t.subject_id = e.id "
                    "WHERE t.object_id=? ORDER BY t.weight DESC",
                    (entity_id,),
                ).fetchall()
            results.extend(dict(r) for r in rows)
        return results

    def get_triples_by_predicate(
        self, predicate: str, era: str | None = None
    ) -> list[dict]:
        """Get all triples with a given predicate."""
        predicate = predicate.upper()
        if era:
            rows = self.conn.execute(
                "SELECT t.*, s.canonical_name AS subject_name, o.canonical_name AS object_name "
                "FROM kg_triples t "
                "JOIN kg_entities s ON t.subject_id = s.id "
                "JOIN kg_entities o ON t.object_id = o.id "
                "WHERE t.predicate=? AND t.era=? ORDER BY t.weight DESC",
                (predicate, era),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT t.*, s.canonical_name AS subject_name, o.canonical_name AS object_name "
                "FROM kg_triples t "
                "JOIN kg_entities s ON t.subject_id = s.id "
                "JOIN kg_entities o ON t.object_id = o.id "
                "WHERE t.predicate=? ORDER BY t.weight DESC",
                (predicate,),
            ).fetchall()
        return [dict(r) for r in rows]

    def triple_count(self, era: str | None = None) -> int:
        if era:
            row = self.conn.execute("SELECT COUNT(*) FROM kg_triples WHERE era=?", (era,)).fetchone()
        else:
            row = self.conn.execute("SELECT COUNT(*) FROM kg_triples").fetchone()
        return row[0]

    # ── Summaries ─────────────────────────────────────────────────────

    def add_summary(
        self,
        summary_type: str,
        summary_text: str,
        era: str,
        entity_id: str | None = None,
        book_title: str | None = None,
        chapter_title: str | None = None,
        chapter_index: int | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Insert a summary record."""
        self.conn.execute(
            "INSERT INTO kg_summaries (summary_type, entity_id, book_title, chapter_title, "
            "chapter_index, era, summary_text, metadata_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                summary_type, entity_id, book_title, chapter_title,
                chapter_index, era, summary_text,
                json.dumps(metadata or {}),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()

    def get_summaries(
        self,
        summary_type: str | None = None,
        entity_id: str | None = None,
        book_title: str | None = None,
        era: str | None = None,
    ) -> list[dict]:
        """Query summaries with optional filters."""
        conditions = []
        params: list = []
        if summary_type:
            conditions.append("summary_type=?")
            params.append(summary_type)
        if entity_id:
            conditions.append("entity_id=?")
            params.append(entity_id)
        if book_title:
            conditions.append("book_title=?")
            params.append(book_title)
        if era:
            conditions.append("era=?")
            params.append(era)
        where = " AND ".join(conditions) if conditions else "1=1"
        rows = self.conn.execute(
            f"SELECT * FROM kg_summaries WHERE {where} ORDER BY chapter_index, id",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Checkpoints ───────────────────────────────────────────────────

    def get_checkpoint_status(
        self, book_title: str, chapter_title: str | None = None, phase: str = "extraction"
    ) -> str:
        """Get checkpoint status: pending, in_progress, completed, failed."""
        if chapter_title:
            row = self.conn.execute(
                "SELECT status FROM kg_extraction_checkpoints "
                "WHERE book_title=? AND chapter_title=? AND phase=?",
                (book_title, chapter_title, phase),
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT status FROM kg_extraction_checkpoints "
                "WHERE book_title=? AND chapter_title IS NULL AND phase=?",
                (book_title, phase),
            ).fetchone()
        return row["status"] if row else "pending"

    def set_checkpoint(
        self,
        book_title: str,
        status: str,
        chapter_title: str | None = None,
        phase: str = "extraction",
        chunk_id: str | None = None,
        error: str | None = None,
    ) -> None:
        """Update extraction checkpoint for resume support."""
        now = datetime.now(timezone.utc).isoformat()
        started = now if status == "in_progress" else None
        completed = now if status in ("completed", "failed") else None

        self.conn.execute(
            "INSERT INTO kg_extraction_checkpoints "
            "(book_title, chapter_title, chunk_id, phase, status, error_message, started_at, completed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(book_title, chapter_title, phase) DO UPDATE SET "
            "status=excluded.status, chunk_id=excluded.chunk_id, "
            "error_message=excluded.error_message, "
            "started_at=COALESCE(excluded.started_at, started_at), "
            "completed_at=excluded.completed_at",
            (book_title, chapter_title, chunk_id, phase, status, error, started, completed),
        )
        self.conn.commit()


def _merge_properties(existing: dict, new: dict) -> dict:
    """Merge entity properties: union lists, keep most specific scalars."""
    merged = dict(existing)
    for key, value in new.items():
        if key not in merged:
            merged[key] = value
            continue
        old = merged[key]
        if isinstance(old, list) and isinstance(value, list):
            merged[key] = list(dict.fromkeys(old + value))  # union preserving order
        elif value and not old:
            merged[key] = value
        # Keep existing non-empty scalar if new is also non-empty (first-seen wins)
    return merged


# Inline schema fallback if migration file is missing
_INLINE_SCHEMA = """
CREATE TABLE IF NOT EXISTS kg_entities (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    era TEXT NOT NULL DEFAULT 'rebellion',
    properties_json TEXT NOT NULL DEFAULT '{}',
    source_books_json TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_kg_entities_type ON kg_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_kg_entities_era ON kg_entities(era);
CREATE TABLE IF NOT EXISTS kg_triples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object_id TEXT NOT NULL,
    era TEXT NOT NULL DEFAULT 'rebellion',
    source_book TEXT,
    source_chunk_id TEXT,
    confidence REAL NOT NULL DEFAULT 1.0,
    weight REAL NOT NULL DEFAULT 1.0,
    properties_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_kg_triples_subject ON kg_triples(subject_id);
CREATE INDEX IF NOT EXISTS idx_kg_triples_object ON kg_triples(object_id);
CREATE INDEX IF NOT EXISTS idx_kg_triples_predicate ON kg_triples(predicate);
CREATE UNIQUE INDEX IF NOT EXISTS idx_kg_triples_unique ON kg_triples(subject_id, predicate, object_id);
CREATE TABLE IF NOT EXISTS kg_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    summary_type TEXT NOT NULL,
    entity_id TEXT,
    book_title TEXT,
    chapter_title TEXT,
    chapter_index INTEGER,
    era TEXT NOT NULL DEFAULT 'rebellion',
    summary_text TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_kg_summaries_type ON kg_summaries(summary_type);
CREATE INDEX IF NOT EXISTS idx_kg_summaries_entity ON kg_summaries(entity_id);
CREATE TABLE IF NOT EXISTS kg_extraction_checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_title TEXT NOT NULL,
    chapter_title TEXT,
    chunk_id TEXT,
    phase TEXT NOT NULL DEFAULT 'extraction',
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    started_at TEXT,
    completed_at TEXT,
    UNIQUE(book_title, chapter_title, phase)
);
"""
