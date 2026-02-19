"""NPC State Store — normalized storage for NPC states.

Extracts ``npc_states`` from the world_state_json blob into the ``npc_states``
table for indexed lookups. Falls back to JSON blob if table is empty (migration
backward compatibility).
"""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)


def load_npc_states(
    conn: sqlite3.Connection,
    campaign_id: str,
) -> dict[str, Any]:
    """Load NPC states from the normalized table.

    Returns a dict of ``{npc_id: state_dict}``.
    """
    rows = conn.execute(
        "SELECT npc_id, npc_name, state_json FROM npc_states WHERE campaign_id = ? ORDER BY last_seen_turn DESC",
        (campaign_id,),
    ).fetchall()

    result: dict[str, Any] = {}
    for row in rows:
        npc_id = row["npc_id"] if isinstance(row, sqlite3.Row) else row[0]
        state_str = row["state_json"] if isinstance(row, sqlite3.Row) else row[2]
        try:
            state = json.loads(state_str) if isinstance(state_str, str) else state_str
        except (json.JSONDecodeError, TypeError):
            state = {}
        result[npc_id] = state

    return result


def save_npc_states(
    conn: sqlite3.Connection,
    campaign_id: str,
    npc_states: dict[str, Any],
    turn_number: int = 0,
) -> None:
    """Write NPC states to the normalized table (upsert).

    Args:
        conn: Active DB connection (caller manages transaction).
        campaign_id: Campaign ID.
        npc_states: Dict of ``{npc_id: state_dict}``.
        turn_number: Current turn number for ``last_seen_turn``.
    """
    for npc_id, state in npc_states.items():
        npc_name = ""
        if isinstance(state, dict):
            npc_name = state.get("name", "") or state.get("npc_name", "") or npc_id
        state_json = json.dumps(state) if not isinstance(state, str) else state

        conn.execute(
            """INSERT INTO npc_states (campaign_id, npc_id, npc_name, state_json, last_seen_turn, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT (campaign_id, npc_id)
               DO UPDATE SET state_json = excluded.state_json,
                             npc_name = excluded.npc_name,
                             last_seen_turn = excluded.last_seen_turn,
                             updated_at = excluded.updated_at""",
            (campaign_id, npc_id, npc_name, state_json, turn_number),
        )


def sync_from_world_state(
    conn: sqlite3.Connection,
    campaign_id: str,
    world_state: dict[str, Any],
    turn_number: int = 0,
) -> None:
    """Sync NPC states from world_state_json to the normalized table.

    Called during commit to keep the table in sync with the JSON blob.
    Also removes NPCs from world_state["npc_states"] after syncing,
    keeping only a reference marker.
    """
    npc_states = world_state.get("npc_states")
    if not isinstance(npc_states, dict) or not npc_states:
        return

    try:
        save_npc_states(conn, campaign_id, npc_states, turn_number)
    except Exception as exc:
        logger.warning("NPC state sync to table failed (non-fatal): %s", exc)


def load_into_world_state(
    conn: sqlite3.Connection,
    campaign_id: str,
    world_state: dict[str, Any],
) -> None:
    """Load NPC states from the normalized table back into world_state.

    Called during state loading to hydrate the world_state dict. If the
    table has data, it takes precedence over the JSON blob.
    """
    try:
        table_states = load_npc_states(conn, campaign_id)
        if table_states:
            # Merge: table data takes precedence
            existing = world_state.get("npc_states") or {}
            if isinstance(existing, dict):
                existing.update(table_states)
                world_state["npc_states"] = existing
            else:
                world_state["npc_states"] = table_states
    except sqlite3.OperationalError:
        pass  # Table doesn't exist yet (pre-migration)
    except Exception as exc:
        logger.warning("NPC state load from table failed (non-fatal): %s", exc)
