"""Load current hot state from DB for LangGraph pipeline."""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

from backend.app.models.state import CharacterSheet, GameState
from backend.app.core.event_store import get_current_turn_number, get_events
from backend.app.core.transcript_store import get_rendered_turns
from backend.app.core.truth_ledger import load_canonical_facts

logger = logging.getLogger(__name__)


def _row_to_dict(row: Any) -> dict:
    """Convert sqlite3.Row or tuple-with-description to dict."""
    if hasattr(row, "keys"):
        return dict(zip(row.keys(), row))
    return dict(row)


def _default_companion_state() -> dict:
    """Default companion/alignment state when missing from world_state_json."""
    return {
        "campaign_start_world_time_minutes": 0,
        "party": [],
        "party_affinity": {},
        "party_traits": {},
        "loyalty_progress": {},
        "alignment": {"light_dark": 0, "paragon_renegade": 0},
        "faction_reputation": {},
        "news_feed": [],
        "banter_queue": [],
        "faction_memory": {},
        "npc_states": {},
        "companion_triggers_fired": [],
    }


def load_campaign(conn: sqlite3.Connection, campaign_id: str) -> dict | None:
    """Load campaign row; world_state_json parsed as dict; world_time_minutes for clock-tick.
    Companion/alignment state flattened from world_state_json to top-level campaign keys."""
    cur = conn.execute(
        """SELECT id, title, time_period, world_state_json,
                  COALESCE(world_time_minutes, 0) AS world_time_minutes
           FROM campaigns WHERE id = ?""",
        (campaign_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    d = _row_to_dict(row)
    ws: dict = {}
    if d.get("world_state_json"):
        try:
            ws = json.loads(d["world_state_json"]) if isinstance(d["world_state_json"], str) else (d["world_state_json"] or {})
        except (TypeError, json.JSONDecodeError):
            ws = {}
    if not isinstance(ws, dict):
        ws = {}
    d["world_state_json"] = ws
    d["world_time_minutes"] = int(d.get("world_time_minutes") or 0)
    # Flatten companion/alignment state to top-level campaign keys
    defaults = _default_companion_state()
    d["campaign_start_world_time_minutes"] = ws.get("campaign_start_world_time_minutes", defaults["campaign_start_world_time_minutes"])
    d["party"] = ws.get("party", defaults["party"])
    d["party_affinity"] = ws.get("party_affinity", defaults["party_affinity"])
    d["party_traits"] = ws.get("party_traits", defaults["party_traits"])
    d["loyalty_progress"] = ws.get("loyalty_progress", defaults["loyalty_progress"])
    d["alignment"] = ws.get("alignment", defaults["alignment"])
    d["faction_reputation"] = ws.get("faction_reputation", defaults["faction_reputation"])
    d["news_feed"] = ws.get("news_feed", defaults["news_feed"])
    d["banter_queue"] = ws.get("banter_queue", defaults["banter_queue"])
    d["faction_memory"] = ws.get("faction_memory", defaults["faction_memory"])
    d["npc_states"] = ws.get("npc_states", defaults["npc_states"])
    d["companion_triggers_fired"] = ws.get("companion_triggers_fired", defaults["companion_triggers_fired"])
    d["genre"] = ws.get("genre") or None
    try:
        ws["canonical_facts"] = load_canonical_facts(conn, campaign_id)
    except Exception:
        ws["canonical_facts"] = {}
    return d


def load_player(conn: sqlite3.Connection, campaign_id: str) -> dict | None:
    """Load player character row (role='Player'). Returns None if not found."""
    cur = conn.execute(
        "SELECT id, name, role, location_id, stats_json, hp_current, relationship_score, COALESCE(credits, 0) AS credits, planet_id "
        "FROM characters WHERE campaign_id = ? AND role = 'Player' LIMIT 1",
        (campaign_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    d = _row_to_dict(row)
    if d.get("stats_json"):
        try:
            d["stats_json"] = json.loads(d["stats_json"]) if isinstance(d["stats_json"], str) else d["stats_json"]
        except (TypeError, json.JSONDecodeError):
            d["stats_json"] = {}
    return d


def load_player_by_id(
    conn: sqlite3.Connection, campaign_id: str, player_id: str
) -> dict | None:
    """Load character row by campaign_id and character id. Returns None if not found."""
    cur = conn.execute(
        """SELECT id, name, role, location_id, stats_json, hp_current, relationship_score,
                  COALESCE(credits, 0) AS credits, COALESCE(psych_profile, '{}') AS psych_profile,
                  planet_id, background, cyoa_answers_json, gender
           FROM characters WHERE campaign_id = ? AND id = ? LIMIT 1""",
        (campaign_id, player_id),
    )
    row = cur.fetchone()
    if row is None:
        return None
    d = _row_to_dict(row)
    if d.get("stats_json"):
        try:
            d["stats_json"] = json.loads(d["stats_json"]) if isinstance(d["stats_json"], str) else d["stats_json"]
        except (TypeError, json.JSONDecodeError):
            d["stats_json"] = {}
    if d.get("psych_profile"):
        try:
            d["psych_profile"] = json.loads(d["psych_profile"]) if isinstance(d["psych_profile"], str) else d["psych_profile"]
        except (TypeError, json.JSONDecodeError):
            d["psych_profile"] = {}
    else:
        d["psych_profile"] = {}
    # Parse CYOA answers if present
    if d.get("cyoa_answers_json"):
        try:
            d["cyoa_answers"] = json.loads(d["cyoa_answers_json"]) if isinstance(d["cyoa_answers_json"], str) else d["cyoa_answers_json"]
        except (TypeError, json.JSONDecodeError):
            d["cyoa_answers"] = None
    else:
        d["cyoa_answers"] = None
    return d


def load_inventory(conn: sqlite3.Connection, owner_id: str) -> list[dict]:
    """Load inventory rows for owner; attributes_json parsed. Returns list of dicts."""
    cur = conn.execute(
        "SELECT id, owner_id, item_name, quantity, attributes_json FROM inventory WHERE owner_id = ?",
        (owner_id,),
    )
    out = []
    for row in cur.fetchall():
        d = _row_to_dict(row)
        if d.get("attributes_json"):
            try:
                d["attributes_json"] = (
                    json.loads(d["attributes_json"])
                    if isinstance(d["attributes_json"], str)
                    else d["attributes_json"]
                )
            except (TypeError, json.JSONDecodeError):
                d["attributes_json"] = {}
        out.append(d)
    return out


def load_turn_history(
    conn: sqlite3.Connection, campaign_id: str, limit: int = 10
) -> list[str]:
    """Last `limit` turn event summaries, e.g. 'T3 MOVE to Tatooine', 'T4 DAMAGE -5'. Hidden events are excluded."""
    current = get_current_turn_number(conn, campaign_id)
    since_turn = max(0, current - limit)
    events = get_events(conn, campaign_id, since_turn=since_turn, include_hidden=False)
    lines: list[str] = []
    for e in events:
        turn_number = e["turn_number"]
        event_type = e["event_type"]
        payload = e.get("payload") or {}
        if event_type == "MOVE":
            to_loc = payload.get("to_location", "?")
            lines.append(f"T{turn_number} MOVE to {to_loc}")
        elif event_type == "DAMAGE":
            amount = payload.get("amount", 0)
            lines.append(f"T{turn_number} DAMAGE -{amount}")
        elif event_type == "HEAL":
            amount = payload.get("amount", 0)
            lines.append(f"T{turn_number} HEAL +{amount}")
        elif event_type == "DIALOGUE":
            lines.append(f"T{turn_number} DIALOGUE")
        elif event_type in ("ITEM_GET", "ITEM_LOSE"):
            item = payload.get("item_name", "?")
            delta = payload.get("quantity_delta", 0)
            lines.append(f"T{turn_number} {event_type} {item} {delta:+d}")
        elif event_type == "RELATIONSHIP":
            delta = payload.get("delta", 0)
            lines.append(f"T{turn_number} RELATIONSHIP {delta:+d}")
        elif event_type == "FLAG_SET":
            key = payload.get("key", "?")
            lines.append(f"T{turn_number} FLAG_SET {key}")
        else:
            lines.append(f"T{turn_number} {event_type}")
    return lines[-limit:] if limit else lines


def build_initial_gamestate(
    conn: sqlite3.Connection, campaign_id: str, player_id: str
) -> GameState:
    """Build GameState from DB: turn_number, player CharacterSheet, current_location, campaign (world_time_minutes), history."""
    turn_number = get_current_turn_number(conn, campaign_id)
    campaign = load_campaign(conn, campaign_id)
    player_row = load_player_by_id(conn, campaign_id, player_id)
    ws = (campaign or {}).get("world_state_json") if isinstance(campaign, dict) else {}
    ws = ws if isinstance(ws, dict) else {}
    _era_sums = list(ws.get("era_summaries") or [])
    if player_row is None:
        return GameState(
            campaign_id=campaign_id,
            player_id=player_id,
            turn_number=turn_number,
            current_location=None,
            player=None,
            campaign=campaign,
            history=load_turn_history(conn, campaign_id, limit=10),
            era_summaries=_era_sums,
        )
    inv = load_inventory(conn, player_id)
    inventory_summary = [
        {"item_name": r["item_name"], "quantity": r["quantity"], **r.get("attributes_json", {})}
        for r in inv
    ]
    player = CharacterSheet(
        character_id=player_row["id"],
        name=player_row["name"],
        stats=player_row.get("stats_json") or {},
        hp_current=player_row.get("hp_current") or 0,
        location_id=player_row.get("location_id"),
        planet_id=player_row.get("planet_id"),
        credits=player_row.get("credits"),
        inventory=inventory_summary,
        psych_profile=player_row.get("psych_profile") or {},
        background=player_row.get("background") or None,
        cyoa_answers=player_row.get("cyoa_answers") or None,
        gender=player_row.get("gender") or None,
    )
    history = load_turn_history(conn, campaign_id, limit=10)

    # Load recent narrative text (last 3 turns) for narrative continuity
    recent_narrative: list[str] = []
    try:
        rendered = get_rendered_turns(conn, campaign_id, limit=3)
        for turn in reversed(rendered):  # oldest first
            text = (turn.get("text") or "").strip()
            if text:
                tn = turn.get("turn_number", "?")
                # Truncate to ~200 words to keep prompt budget manageable
                words = text.split()
                if len(words) > 200:
                    text = " ".join(words[:200]) + "..."
                recent_narrative.append(f"[Turn {tn}] {text}")
    except Exception:
        logger.warning("Failed to load recent narrative (non-fatal)", exc_info=True)

    # V2.10: Load starship ownership from world_state_json
    _player_starship: dict | None = None
    if ws.get("has_starship") and ws.get("active_starship"):
        _player_starship = {
            "ship_type": ws["active_starship"],
            "has_starship": True,
        }

    # V2.12: Load known NPCs from world_state_json
    _known_npcs = list(ws.get("known_npcs") or [])

    return GameState(
        campaign_id=campaign_id,
        player_id=player_id,
        turn_number=turn_number,
        current_location=player_row.get("location_id"),
        current_planet=player_row.get("planet_id"),
        player=player,
        campaign=campaign,
        history=history,
        era_summaries=_era_sums,
        recent_narrative=recent_narrative,
        player_starship=_player_starship,
        known_npcs=_known_npcs,
    )
