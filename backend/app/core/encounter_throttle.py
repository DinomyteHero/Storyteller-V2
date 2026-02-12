"""NPC introduction throttling: prevent overwhelming the player with too many named NPCs."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from backend.app.constants import get_scale_profile

# Early game: first 60 in-world minutes; cap new NPC introductions at 3
EARLY_GAME_WINDOW_MINUTES = 60
EARLY_GAME_NPC_CAP = 3


def get_effective_location(state: dict[str, Any]) -> str | None:
    """Use MOVE event destination if present, else current_location."""
    mechanic_result = state.get("mechanic_result") or {}
    events = mechanic_result.get("events") or []
    for e in events:
        if isinstance(e, dict):
            event_type = e.get("event_type", "")
            payload = e.get("payload") or e
            if event_type == "MOVE":
                to_loc = payload.get("to_location") if isinstance(payload, dict) else None
                if to_loc:
                    return to_loc
        elif hasattr(e, "event_type") and getattr(e, "event_type") == "MOVE":
            pl = getattr(e, "payload", None) or {}
            to_loc = pl.get("to_location") if isinstance(pl, dict) else None
            if to_loc:
                return to_loc
    return state.get("current_location")


def _get_world_time_minutes(state: dict[str, Any]) -> int:
    """Total play minutes: campaign.world_time_minutes + mechanic time_cost."""
    campaign = state.get("campaign") or {}
    base = int(campaign.get("world_time_minutes") or 0)
    mechanic_result = state.get("mechanic_result") or {}
    dt = int(mechanic_result.get("time_cost_minutes") or 0)
    return base + dt


def load_world_state(conn: sqlite3.Connection, campaign_id: str) -> dict[str, Any]:
    """Load world_state_json from campaigns."""
    cur = conn.execute(
        "SELECT world_state_json FROM campaigns WHERE id = ?",
        (campaign_id,),
    )
    row = cur.fetchone()
    if row is None:
        return {}
    raw = row[0]
    if not raw:
        return {}
    try:
        return json.loads(raw) if isinstance(raw, str) else (raw or {})
    except (TypeError, json.JSONDecodeError):
        return {}


def _save_world_state(conn: sqlite3.Connection, campaign_id: str, world_state: dict[str, Any]) -> None:
    """Persist world_state_json to campaigns."""
    conn.execute(
        "UPDATE campaigns SET world_state_json = ? WHERE id = ?",
        (json.dumps(world_state), campaign_id),
    )


def can_introduce_new_npc(
    conn: sqlite3.Connection,
    campaign_id: str,
    state: dict[str, Any],
) -> tuple[bool, str]:
    """
    Return (allowed, reason). New NPC introduction allowed only if:
    (a) location changed since last turn, OR
    (b) npc_introduction_triggers references this NPC, OR
    (c) not in early game, OR
    (d) in early game but under cap (3).
    """
    world_state = load_world_state(conn, campaign_id)
    introduced_npcs = world_state.get("introduced_npcs")
    if not isinstance(introduced_npcs, list):
        introduced_npcs = []
    introduction_log = world_state.get("introduction_log")
    if not isinstance(introduction_log, list):
        introduction_log = []
    last_location_id = world_state.get("last_location_id")
    npc_introduction_triggers = world_state.get("npc_introduction_triggers")
    if not isinstance(npc_introduction_triggers, list):
        npc_introduction_triggers = []

    # Use campaign-scale-aware NPC cap (falls back to EARLY_GAME_NPC_CAP default)
    campaign_scale = world_state.get("campaign_scale")
    scale_profile = get_scale_profile(campaign_scale)
    scaled_npc_cap = scale_profile.early_game_npc_cap

    effective_location = get_effective_location(state)
    world_time = _get_world_time_minutes(state)
    early_game = world_time < EARLY_GAME_WINDOW_MINUTES
    location_changed = effective_location != last_location_id
    has_trigger = len(npc_introduction_triggers) > 0
    at_cap = len(introduced_npcs) >= scaled_npc_cap

    if not early_game:
        return True, "past_early_game"
    if not at_cap:
        return True, "under_cap"
    if location_changed:
        return True, "location_changed"
    if has_trigger:
        return True, "rumor_quest_trigger"
    return False, "throttled_early_game_cap"


def record_npc_introduction(
    conn: sqlite3.Connection,
    campaign_id: str,
    npc_id: str,
    state: dict[str, Any],
    trigger: str = "spawn",
) -> None:
    """Add npc_id to introduced_npcs and append to introduction_log."""
    world_state = load_world_state(conn, campaign_id)
    introduced = list(world_state.get("introduced_npcs") or [])
    if npc_id not in introduced:
        introduced.append(npc_id)
    log = list(world_state.get("introduction_log") or [])
    world_time = _get_world_time_minutes(state)
    log.append({
        "npc_id": npc_id,
        "introduced_at_minutes": world_time,
        "trigger": trigger,
    })
    world_state["introduced_npcs"] = introduced
    world_state["introduction_log"] = log
    _save_world_state(conn, campaign_id, world_state)


def update_last_location(
    conn: sqlite3.Connection,
    campaign_id: str,
    effective_location: str | None,
) -> None:
    """Update last_location_id for next-turn comparison. Clear npc_introduction_triggers (single-use)."""
    world_state = load_world_state(conn, campaign_id)
    world_state["last_location_id"] = effective_location
    world_state.pop("npc_introduction_triggers", None)  # Single-use; WorldSim sets fresh each tick
    _save_world_state(conn, campaign_id, world_state)


def get_introduced_npc_names(conn: sqlite3.Connection, campaign_id: str) -> list[str]:
    """Return names of already-introduced NPCs for CastingAgent context."""
    world_state = load_world_state(conn, campaign_id)
    ids = world_state.get("introduced_npcs") or []
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    cur = conn.execute(
        f"SELECT name FROM characters WHERE campaign_id = ? AND id IN ({placeholders})",
        [campaign_id] + list(ids),
    )
    return [row[0] for row in cur.fetchall() if row and row[0]]


def get_anonymous_extras(location_id: str) -> list[dict[str, Any]]:
    """Return 1–2 anonymous NPCs (no persistence) when throttled."""
    return [
        {
            "id": "anon-1",
            "name": "a stranger",
            "role": "Stranger",
            "relationship_score": 0,
            "location_id": location_id,
            "has_secret_agenda": False,
        },
        {
            "id": "anon-2",
            "name": "a patron",
            "role": "Patron",
            "relationship_score": 0,
            "location_id": location_id,
            "has_secret_agenda": False,
        },
    ]


def apply_npc_introduction_from_event(
    conn: sqlite3.Connection,
    campaign_id: str,
    npc_id: str,
    world_time_minutes: int,
    trigger: str = "spawn",
) -> None:
    """
    Apply NPC introduction update to world_state_json (called from CommitNode).
    This is the event-driven version of record_npc_introduction().
    """
    world_state = load_world_state(conn, campaign_id)
    introduced = list(world_state.get("introduced_npcs") or [])
    if npc_id not in introduced:
        introduced.append(npc_id)
    log = list(world_state.get("introduction_log") or [])
    log.append({
        "npc_id": npc_id,
        "introduced_at_minutes": world_time_minutes,
        "trigger": trigger,
    })
    world_state["introduced_npcs"] = introduced
    world_state["introduction_log"] = log
    _save_world_state(conn, campaign_id, world_state)


def apply_last_location_update_from_event(
    conn: sqlite3.Connection,
    campaign_id: str,
    effective_location: str | None,
) -> None:
    """
    Apply last location update to world_state_json (called from CommitNode).
    This is the event-driven version of update_last_location().
    """
    world_state = load_world_state(conn, campaign_id)
    world_state["last_location_id"] = effective_location
    world_state.pop("npc_introduction_triggers", None)  # Single-use; WorldSim sets fresh each tick
    _save_world_state(conn, campaign_id, world_state)