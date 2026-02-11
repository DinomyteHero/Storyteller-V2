"""Director suggestion pre-generation cache.

SQLite-backed cache that stores pre-computed Director output so the
next turn can skip the Director LLM call entirely on cache hit.

Cache key: (campaign_id, location_id, arc_stage, turn_number)
TTL: implicitly 1 turn — key includes turn_number, so stale entries
are never matched.  Old entries are cleaned up periodically.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

from backend.app.config import DEFAULT_DB_PATH

logger = logging.getLogger(__name__)


class SuggestionCache:
    """SQLite-backed Director suggestion pre-generation cache."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or DEFAULT_DB_PATH

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table(self, conn: sqlite3.Connection) -> None:
        """Create the cache table if it doesn't exist."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS suggestion_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id TEXT NOT NULL,
                location_id TEXT NOT NULL,
                arc_stage TEXT NOT NULL,
                turn_number INTEGER NOT NULL,
                output_json TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(campaign_id, location_id, arc_stage, turn_number)
            )
        """)

    def get(
        self,
        campaign_id: str,
        location_id: str,
        arc_stage: str,
        turn_number: int,
    ) -> dict[str, Any] | None:
        """Return cached Director output dict or None on miss."""
        try:
            conn = self._get_conn()
            try:
                self._ensure_table(conn)
                row = conn.execute(
                    """SELECT output_json FROM suggestion_cache
                       WHERE campaign_id = ? AND location_id = ? AND arc_stage = ? AND turn_number = ?""",
                    (campaign_id, location_id, arc_stage, turn_number),
                ).fetchone()
                if row is None:
                    return None
                return json.loads(row["output_json"])
            finally:
                conn.close()
        except Exception as e:
            logger.debug("SuggestionCache.get failed (non-fatal): %s", e)
            return None

    def put(
        self,
        campaign_id: str,
        location_id: str,
        arc_stage: str,
        turn_number: int,
        output: dict[str, Any],
    ) -> None:
        """Store Director output for a future turn."""
        try:
            conn = self._get_conn()
            try:
                self._ensure_table(conn)
                conn.execute(
                    """INSERT OR REPLACE INTO suggestion_cache
                       (campaign_id, location_id, arc_stage, turn_number, output_json)
                       VALUES (?, ?, ?, ?, ?)""",
                    (campaign_id, location_id, arc_stage, turn_number, json.dumps(output)),
                )
                conn.commit()
                # Clean up old entries (keep only last 3 turns per campaign)
                conn.execute(
                    """DELETE FROM suggestion_cache
                       WHERE campaign_id = ? AND turn_number < ?""",
                    (campaign_id, turn_number - 2),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.debug("SuggestionCache.put failed (non-fatal): %s", e)

    def invalidate(self, campaign_id: str) -> None:
        """Clear all cached suggestions for a campaign."""
        try:
            conn = self._get_conn()
            try:
                self._ensure_table(conn)
                conn.execute(
                    "DELETE FROM suggestion_cache WHERE campaign_id = ?",
                    (campaign_id,),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.debug("SuggestionCache.invalidate failed (non-fatal): %s", e)
