"""Quest Store — normalized storage for quest log entries.

Extracts quest data from ``world_state_json["quest_log"]`` into the
``quest_entries`` table for indexed lookups. Falls back to JSON blob
if table is empty (migration backward compatibility).
"""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)


def load_quest_entries(
    conn: sqlite3.Connection,
    campaign_id: str,
    status: str | None = None,
) -> dict[str, Any]:
    """Load quest entries from the normalized table.

    Args:
        conn: Active DB connection.
        campaign_id: Campaign ID.
        status: Optional filter (e.g. "active", "completed").

    Returns:
        Dict of ``{quest_id: quest_dict}``.
    """
    if status:
        rows = conn.execute(
            "SELECT quest_id, quest_title, status, quest_json FROM quest_entries WHERE campaign_id = ? AND status = ?",
            (campaign_id, status),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT quest_id, quest_title, status, quest_json FROM quest_entries WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchall()

    result: dict[str, Any] = {}
    for row in rows:
        quest_id = row["quest_id"] if isinstance(row, sqlite3.Row) else row[0]
        quest_str = row["quest_json"] if isinstance(row, sqlite3.Row) else row[3]
        try:
            quest = json.loads(quest_str) if isinstance(quest_str, str) else quest_str
        except (json.JSONDecodeError, TypeError):
            quest = {}
        result[quest_id] = quest

    return result


def save_quest_entries(
    conn: sqlite3.Connection,
    campaign_id: str,
    quest_log: dict[str, Any],
    turn_number: int = 0,
) -> None:
    """Write quest entries to the normalized table (upsert).

    Args:
        conn: Active DB connection (caller manages transaction).
        campaign_id: Campaign ID.
        quest_log: Dict of ``{quest_id: quest_dict}``.
        turn_number: Current turn number.
    """
    for quest_id, quest_data in quest_log.items():
        if not isinstance(quest_data, dict):
            continue

        quest_title = quest_data.get("title", "") or quest_data.get("name", "") or quest_id
        status = quest_data.get("status", "active") or "active"
        quest_json = json.dumps(quest_data)

        conn.execute(
            """INSERT INTO quest_entries
               (campaign_id, quest_id, quest_title, status, quest_json, created_turn, updated_turn, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT (campaign_id, quest_id)
               DO UPDATE SET quest_title = excluded.quest_title,
                             status = excluded.status,
                             quest_json = excluded.quest_json,
                             updated_turn = excluded.updated_turn,
                             updated_at = excluded.updated_at""",
            (campaign_id, quest_id, quest_title, status, quest_json, turn_number, turn_number),
        )


def sync_from_world_state(
    conn: sqlite3.Connection,
    campaign_id: str,
    world_state: dict[str, Any],
    turn_number: int = 0,
) -> None:
    """Sync quest log from world_state to the normalized table."""
    quest_log = world_state.get("quest_log")
    if not isinstance(quest_log, dict) or not quest_log:
        return

    try:
        save_quest_entries(conn, campaign_id, quest_log, turn_number)
    except Exception as exc:
        logger.warning("Quest entry sync to table failed (non-fatal): %s", exc)


def load_into_world_state(
    conn: sqlite3.Connection,
    campaign_id: str,
    world_state: dict[str, Any],
) -> None:
    """Load quest entries from the normalized table back into world_state.

    If the table has data, it takes precedence over the JSON blob.
    """
    try:
        table_quests = load_quest_entries(conn, campaign_id)
        if table_quests:
            existing = world_state.get("quest_log") or {}
            if isinstance(existing, dict):
                existing.update(table_quests)
                world_state["quest_log"] = existing
            else:
                world_state["quest_log"] = table_quests
    except sqlite3.OperationalError:
        pass  # Table doesn't exist yet
    except Exception as exc:
        logger.warning("Quest entry load from table failed (non-fatal): %s", exc)
