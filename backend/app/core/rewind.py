"""Rewind/Undo — restore a campaign to a previous turn.

Uses the snapshot-based approach: ``turn_snapshots`` stores ``world_state_json``
at each turn. On rewind, we:
  1. Restore ``world_state_json`` from the snapshot at the target turn.
  2. Delete all turn-related data for turns > target.
  3. Reset the ``campaigns.next_turn_number`` counter.

All operations run in a single ``BEGIN IMMEDIATE`` transaction.
"""
from __future__ import annotations

import json
import logging
import sqlite3

logger = logging.getLogger(__name__)

# Tables with (campaign_id, turn_number) that need cleanup on rewind.
_TURN_TABLES: list[tuple[str, str]] = [
    ("turn_events", "turn_number"),
    ("rendered_turns", "turn_number"),
    ("episodic_memories", "turn_number"),
    ("npc_memory", "turn_number"),
    ("suggestion_cache", "turn_number"),
    ("canon_events", "triggered_at_turn"),
    ("pending_world_state_patches", "turn_number"),
    ("turn_snapshots", "turn_number"),
]

# Optional tables that may not exist in all DB versions.
_OPTIONAL_TURN_TABLES: list[tuple[str, str]] = [
    ("crystallized_memories", "turn_number"),
    ("npc_states", "last_seen_turn"),
    ("quest_entries", "updated_turn"),
]


def rewind_campaign_to_turn(
    conn: sqlite3.Connection,
    campaign_id: str,
    target_turn: int,
) -> dict:
    """Rewind a campaign to ``target_turn`` (inclusive).

    All data for turns > ``target_turn`` is deleted. The campaign's
    ``world_state_json`` is restored from the snapshot at ``target_turn``.

    Args:
        conn: Active DB connection (transaction managed by this function).
        campaign_id: Campaign to rewind.
        target_turn: Turn number to rewind to (must be >= 1).

    Returns:
        Dict with rewind summary: ``{"rewound_to": int, "turns_deleted": int}``.

    Raises:
        ValueError: If target_turn is invalid or no snapshot exists.
    """
    if target_turn < 1:
        raise ValueError("Cannot rewind to turn < 1")

    # Check current turn
    row = conn.execute(
        "SELECT next_turn_number FROM campaigns WHERE id = ?",
        (campaign_id,),
    ).fetchone()
    if not row:
        raise ValueError(f"Campaign {campaign_id} not found")

    current_next = row["next_turn_number"] if isinstance(row, sqlite3.Row) else row[0]
    current_turn = current_next - 1  # next_turn_number is 1-based (next to allocate)

    if target_turn >= current_turn:
        raise ValueError(
            f"Target turn {target_turn} >= current turn {current_turn}. Nothing to rewind."
        )

    # Load snapshot for target turn
    snap_row = conn.execute(
        "SELECT world_state_json FROM turn_snapshots WHERE campaign_id = ? AND turn_number = ?",
        (campaign_id, target_turn),
    ).fetchone()
    if not snap_row:
        raise ValueError(
            f"No snapshot found for turn {target_turn}. "
            f"Rewind is only available to turns with saved snapshots."
        )

    snapshot_json = snap_row["world_state_json"] if isinstance(snap_row, sqlite3.Row) else snap_row[0]

    # Begin atomic rewind
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Delete turn data for turns > target
        for table_name, turn_col in _TURN_TABLES:
            conn.execute(
                f"DELETE FROM {table_name} WHERE campaign_id = ? AND {turn_col} > ?",
                (campaign_id, target_turn),
            )

        # Optional tables (may not exist in older DBs)
        for table_name, turn_col in _OPTIONAL_TURN_TABLES:
            try:
                conn.execute(
                    f"DELETE FROM {table_name} WHERE campaign_id = ? AND {turn_col} > ?",
                    (campaign_id, target_turn),
                )
            except sqlite3.OperationalError:
                pass  # Table doesn't exist

        # Delete non-immutable truth facts from turns after target
        try:
            conn.execute(
                """DELETE FROM truth_facts
                   WHERE campaign_id = ? AND is_immutable = 0
                   AND source_turn_id > ?""",
                (campaign_id, f"{campaign_id}_t{target_turn}"),
            )
        except sqlite3.OperationalError:
            pass  # truth_facts table may not exist or lack is_immutable

        # Restore world_state from snapshot
        conn.execute(
            "UPDATE campaigns SET world_state_json = ?, next_turn_number = ?, version = version + 1, updated_at = datetime('now') WHERE id = ?",
            (snapshot_json, target_turn + 1, campaign_id),
        )

        conn.commit()
    except Exception:
        conn.rollback()
        raise

    turns_deleted = current_turn - target_turn
    logger.info(
        "Rewound campaign %s from turn %d to turn %d (%d turns deleted)",
        campaign_id, current_turn, target_turn, turns_deleted,
    )

    return {
        "rewound_to": target_turn,
        "turns_deleted": turns_deleted,
        "previous_turn": current_turn,
    }
