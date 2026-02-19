"""Historical Timeline Scheduler — canon event injection for Historical mode.

Loads static canon event definitions from era packs and triggers them
at the appropriate arc stage / turn number. Triggered events are:
  1. Recorded in the canon_events DB table (at most once per event per campaign).
  2. Persisted as immutable facts in the truth_ledger.
  3. Surfaced to Director/Narrator via arc_guidance context.

Only active when campaign_mode == "historical".
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from backend.app.constants import (
    CANON_EVENT_LOOKAHEAD_TURNS,
    CANON_EVENT_MAX_PER_TURN,
    SANDBOX_ARC_STAGE_ORDER,
)

logger = logging.getLogger(__name__)

# Cache loaded canon event definitions per era_id (process-lifetime).
_ERA_CANON_CACHE: dict[str, list[dict[str, Any]]] = {}

ERA_PACKS_DIR = Path(__file__).resolve().parents[3] / "data" / "static" / "era_packs"


def _load_canon_events(era_id: str) -> list[dict[str, Any]]:
    """Load canon event definitions from ``data/static/era_packs/{era_id}/canon_events.json``."""
    if era_id in _ERA_CANON_CACHE:
        return _ERA_CANON_CACHE[era_id]

    path = ERA_PACKS_DIR / era_id.lower() / "canon_events.json"
    if not path.exists():
        _ERA_CANON_CACHE[era_id] = []
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        events = data.get("events") or []
        _ERA_CANON_CACHE[era_id] = events
        logger.info("Loaded %d canon events for era %s", len(events), era_id)
        return events
    except Exception as exc:
        logger.warning("Failed to load canon events for era %s: %s", era_id, exc)
        _ERA_CANON_CACHE[era_id] = []
        return []


def _already_triggered(conn: sqlite3.Connection, campaign_id: str) -> set[str]:
    """Return set of event_ids already triggered for this campaign."""
    rows = conn.execute(
        "SELECT event_id FROM canon_events WHERE campaign_id = ?",
        (campaign_id,),
    ).fetchall()
    return {r["event_id"] if isinstance(r, sqlite3.Row) else r[0] for r in rows}


def check_canon_events(
    conn: sqlite3.Connection,
    campaign_id: str,
    era_id: str,
    campaign_mode: str,
    arc_stage: str,
    turn_number: int,
) -> list[dict[str, Any]]:
    """Check for canon events that should trigger this turn.

    Returns a list of event dicts that matched. Each event is recorded
    in the ``canon_events`` table and its immutable facts are written
    to the truth ledger.

    Args:
        conn: Active DB connection (caller manages transaction).
        campaign_id: Current campaign ID.
        era_id: Era identifier (e.g. "REBELLION").
        campaign_mode: "historical" or "sandbox". Only fires for "historical".
        arc_stage: Current arc stage (SETUP/RISING/CLIMAX/RESOLUTION).
        turn_number: Current turn number.

    Returns:
        List of triggered event dicts (may be empty).
    """
    if campaign_mode != "historical":
        return []

    all_events = _load_canon_events(era_id)
    if not all_events:
        return []

    triggered_ids = _already_triggered(conn, campaign_id)
    stage_order = SANDBOX_ARC_STAGE_ORDER
    current_stage_idx = stage_order.get(arc_stage.upper(), 0)

    triggered: list[dict[str, Any]] = []

    for event in all_events:
        event_id = event.get("id", "")
        if event_id in triggered_ids:
            continue

        # Check arc stage match
        event_stage = event.get("arc_stage", "").upper()
        event_stage_idx = stage_order.get(event_stage, 99)
        if event_stage_idx > current_stage_idx:
            # Event is for a later stage
            continue

        # Check turn window
        turn_min = event.get("trigger_turn_min", 0)
        turn_max = event.get("trigger_turn_max", 9999)
        if turn_number < turn_min or turn_number > turn_max:
            continue

        # This event should trigger
        triggered.append(event)
        if len(triggered) >= CANON_EVENT_MAX_PER_TURN:
            break

    # Record triggered events
    for event in triggered:
        _record_triggered_event(conn, campaign_id, era_id, event, arc_stage, turn_number)

    return triggered


def _record_triggered_event(
    conn: sqlite3.Connection,
    campaign_id: str,
    era_id: str,
    event: dict[str, Any],
    arc_stage: str,
    turn_number: int,
) -> None:
    """Persist a triggered canon event to DB and write immutable facts."""
    event_id = event.get("id", "")
    event_text = event.get("event_text", "")

    # Record in canon_events table
    try:
        conn.execute(
            """INSERT OR IGNORE INTO canon_events
               (campaign_id, era_id, event_id, triggered_at_turn, arc_stage, event_text, is_immutable)
               VALUES (?, ?, ?, ?, ?, ?, 1)""",
            (campaign_id, era_id, event_id, turn_number, arc_stage, event_text),
        )
    except Exception as exc:
        logger.warning("Failed to record canon event %s: %s", event_id, exc)

    # Write immutable facts to truth ledger
    immutable_facts = event.get("immutable_facts") or []
    if immutable_facts:
        try:
            from backend.app.core.truth_ledger import upsert_facts
            from backend.app.models.turn_contract import Fact

            facts = [
                Fact(fact_key=f"canon_{event_id}_{i}", fact_value=fact_text)
                for i, fact_text in enumerate(immutable_facts)
            ]
            turn_id = f"{campaign_id}_t{turn_number}"
            upsert_facts(conn, campaign_id, turn_id, facts, is_immutable=True)
        except Exception as exc:
            logger.warning("Failed to write immutable facts for canon event %s: %s", event_id, exc)

    logger.info(
        "Canon event triggered: %s (era=%s, campaign=%s, turn=%d, stage=%s)",
        event_id, era_id, campaign_id, turn_number, arc_stage,
    )


def get_upcoming_events(
    conn: sqlite3.Connection,
    campaign_id: str,
    era_id: str,
    campaign_mode: str,
    arc_stage: str,
    turn_number: int,
) -> list[dict[str, str]]:
    """Return upcoming canon events for Director context (lookahead hints).

    These are events that haven't triggered yet but are within
    CANON_EVENT_LOOKAHEAD_TURNS of their trigger window. This lets
    the Director foreshadow approaching galactic events.

    Returns list of ``{"title": ..., "director_hint": ...}`` dicts.
    """
    if campaign_mode != "historical":
        return []

    all_events = _load_canon_events(era_id)
    if not all_events:
        return []

    triggered_ids = _already_triggered(conn, campaign_id)
    stage_order = SANDBOX_ARC_STAGE_ORDER
    current_stage_idx = stage_order.get(arc_stage.upper(), 0)
    lookahead = CANON_EVENT_LOOKAHEAD_TURNS

    upcoming: list[dict[str, str]] = []
    for event in all_events:
        event_id = event.get("id", "")
        if event_id in triggered_ids:
            continue

        event_stage = event.get("arc_stage", "").upper()
        event_stage_idx = stage_order.get(event_stage, 99)

        # Must be current or next stage
        if event_stage_idx > current_stage_idx + 1:
            continue

        turn_min = event.get("trigger_turn_min", 0)
        # Is it within lookahead window?
        if turn_number + lookahead >= turn_min:
            upcoming.append({
                "title": event.get("title", event_id),
                "director_hint": event.get("director_hint", ""),
            })

    return upcoming[:3]  # Cap at 3 upcoming hints


def get_recently_triggered(
    conn: sqlite3.Connection,
    campaign_id: str,
    turn_number: int,
    lookback: int = 2,
) -> list[dict[str, Any]]:
    """Return canon events triggered in the last ``lookback`` turns.

    Useful for Narrator context — recently triggered events should be
    woven into the narrative.
    """
    rows = conn.execute(
        """SELECT event_id, event_text, arc_stage, triggered_at_turn
           FROM canon_events
           WHERE campaign_id = ? AND triggered_at_turn >= ?
           ORDER BY triggered_at_turn DESC""",
        (campaign_id, max(1, turn_number - lookback)),
    ).fetchall()

    return [
        {
            "event_id": r["event_id"] if isinstance(r, sqlite3.Row) else r[0],
            "event_text": r["event_text"] if isinstance(r, sqlite3.Row) else r[1],
            "arc_stage": r["arc_stage"] if isinstance(r, sqlite3.Row) else r[2],
            "triggered_at_turn": r["triggered_at_turn"] if isinstance(r, sqlite3.Row) else r[3],
        }
        for r in rows
    ]
