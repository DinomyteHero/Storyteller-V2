"""Projections: update normalized tables from events (truth is event store). Deterministic only."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from backend.app.models.events import Event


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _load_world_state(conn: sqlite3.Connection, campaign_id: str) -> dict[str, Any] | None:
    cur = conn.execute(
        "SELECT world_state_json FROM campaigns WHERE id = ?",
        (campaign_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    try:
        state = json.loads(row[0]) if row[0] else {}
    except (TypeError, json.JSONDecodeError):
        state = {}
    return state if isinstance(state, dict) else {}


def _save_world_state(conn: sqlite3.Connection, campaign_id: str, state: dict[str, Any]) -> None:
    conn.execute(
        "UPDATE campaigns SET world_state_json = ? WHERE id = ?",
        (json.dumps(state), campaign_id),
    )


def _load_character_psych_profile(
    conn: sqlite3.Connection,
    campaign_id: str,
    character_id: str,
) -> dict[str, Any] | None:
    cur = conn.execute(
        "SELECT psych_profile FROM characters WHERE id = ? AND campaign_id = ?",
        (character_id, campaign_id),
    )
    row = cur.fetchone()
    if row is None:
        return None
    try:
        psych = json.loads(row[0]) if row[0] else {}
    except (TypeError, json.JSONDecodeError):
        psych = {}
    return psych if isinstance(psych, dict) else {}


def _derive_mood(stress_level: int, previous: str | None = None) -> str:
    if stress_level >= 8:
        return "distressed"
    if stress_level <= 2:
        return "calm"
    return previous or "neutral"


def apply_projection(
    conn: sqlite3.Connection, campaign_id: str, events: list[Event], commit: bool = True
) -> None:
    """Apply each event to normalized tables. Deterministic. If commit=False, caller manages transaction."""
    for e in events:
        payload = e.payload or {}
        event_type = (e.event_type or "").upper()
        if not event_type:
            continue

        if event_type == "MOVE":
            character_id = payload.get("character_id")
            to_location = payload.get("to_location")
            to_planet = payload.get("to_planet")
            if character_id is not None and to_location is not None:
                if to_planet:
                    conn.execute(
                        "UPDATE characters SET location_id = ?, planet_id = ? WHERE id = ? AND campaign_id = ?",
                        (to_location, to_planet, character_id, campaign_id),
                    )
                else:
                    conn.execute(
                        "UPDATE characters SET location_id = ? WHERE id = ? AND campaign_id = ?",
                        (to_location, character_id, campaign_id),
                    )
                # Skip if no row updated

        elif event_type == "DAMAGE":
            character_id = payload.get("character_id")
            amount = _coerce_int(payload.get("amount", 0), 0)
            if character_id is not None:
                cur = conn.execute(
                    "SELECT hp_current FROM characters WHERE id = ? AND campaign_id = ?",
                    (character_id, campaign_id),
                )
                row = cur.fetchone()
                if row is not None:
                    hp = max(0, (row[0] or 0) - amount)
                    conn.execute(
                        "UPDATE characters SET hp_current = ? WHERE id = ? AND campaign_id = ?",
                        (hp, character_id, campaign_id),
                    )

        elif event_type == "HEAL":
            character_id = payload.get("character_id")
            amount = _coerce_int(payload.get("amount", 0), 0)
            if character_id is not None:
                cur = conn.execute(
                    "SELECT hp_current FROM characters WHERE id = ? AND campaign_id = ?",
                    (character_id, campaign_id),
                )
                row = cur.fetchone()
                if row is not None:
                    hp = (row[0] or 0) + amount
                    conn.execute(
                        "UPDATE characters SET hp_current = ? WHERE id = ? AND campaign_id = ?",
                        (hp, character_id, campaign_id),
                    )

        elif event_type == "RELATIONSHIP":
            npc_id = payload.get("npc_id")
            delta = _coerce_int(payload.get("delta", 0), 0)
            if npc_id is not None:
                cur = conn.execute(
                    "SELECT relationship_score FROM characters WHERE id = ? AND campaign_id = ?",
                    (npc_id, campaign_id),
                )
                row = cur.fetchone()
                if row is not None:
                    score = (row[0] or 0) + delta
                    conn.execute(
                        "UPDATE characters SET relationship_score = ? WHERE id = ? AND campaign_id = ?",
                        (score, npc_id, campaign_id),
                    )

        elif event_type == "FLAG_SET":
            key = payload.get("key")
            value = payload.get("value")
            if key is not None:
                state = _load_world_state(conn, campaign_id)
                if state is not None:
                    state[key] = value
                    _save_world_state(conn, campaign_id, state)

        elif event_type == "WORLD_TIME_ADVANCE":
            mode = str(payload.get("mode") or "").lower()
            if mode == "set":
                world_time = max(0, _coerce_int(payload.get("world_time_minutes", 0), 0))
                conn.execute(
                    "UPDATE campaigns SET world_time_minutes = ? WHERE id = ?",
                    (world_time, campaign_id),
                )
            else:
                minutes = _coerce_int(payload.get("minutes", 0), 0)
                if minutes != 0:
                    conn.execute(
                        "UPDATE campaigns SET world_time_minutes = COALESCE(world_time_minutes, 0) + ? WHERE id = ?",
                        (minutes, campaign_id),
                    )

        elif event_type == "PLAYER_PSYCH_UPDATE":
            character_id = payload.get("character_id")
            stress_delta = _coerce_int(payload.get("stress_delta", 0), 0)
            if character_id and stress_delta:
                psych = _load_character_psych_profile(conn, campaign_id, character_id)
                if psych is not None:
                    current_stress = _coerce_int(psych.get("stress_level", 3), 3)
                    new_stress = max(0, min(10, current_stress + stress_delta))
                    current_mood = str(psych.get("current_mood") or "").strip() or None
                    psych["stress_level"] = new_stress
                    psych["current_mood"] = _derive_mood(new_stress, previous=current_mood)
                    conn.execute(
                        "UPDATE characters SET psych_profile = ? WHERE id = ? AND campaign_id = ?",
                        (json.dumps(psych), character_id, campaign_id),
                    )
                    # Optional mirror for compatibility with existing world_state_json readers.
                    state = _load_world_state(conn, campaign_id)
                    if state is not None:
                        state["psych_profile"] = psych
                        _save_world_state(conn, campaign_id, state)

        elif event_type == "NPC_DEPART":
            character_id = payload.get("character_id")
            if character_id:
                conn.execute(
                    "UPDATE characters SET location_id = NULL WHERE id = ? AND campaign_id = ?",
                    (character_id, campaign_id),
                )

        elif event_type in ("FACTION_MOVE", "NPC_ACTION", "PLOT_TICK", "RUMOR_SPREAD"):
            state = _load_world_state(conn, campaign_id)
            if state is not None:
                log = list(state.get("world_sim_events") or [])
                log.append({
                    "event_type": event_type,
                    "payload": payload,
                    "is_hidden": bool(getattr(e, "is_hidden", False)),
                })
                if len(log) > 50:
                    log = log[-50:]
                state["world_sim_events"] = log
                _save_world_state(conn, campaign_id, state)

        elif event_type in ("ITEM_GET", "ITEM_LOSE"):
            owner_id = payload.get("owner_id")
            item_name = payload.get("item_name")
            quantity_delta = payload.get("quantity_delta", 0)
            if event_type == "ITEM_LOSE":
                quantity_delta = -abs(quantity_delta)
            if owner_id is None or item_name is None:
                continue
            inv_id = f"{owner_id}:{item_name}"
            cur = conn.execute(
                "SELECT quantity, attributes_json FROM inventory WHERE id = ?",
                (inv_id,),
            )
            row = cur.fetchone()
            if row is not None:
                new_qty = (row[0] or 0) + quantity_delta
                if new_qty <= 0:
                    conn.execute("DELETE FROM inventory WHERE id = ?", (inv_id,))
                else:
                    conn.execute(
                        "UPDATE inventory SET quantity = ? WHERE id = ?",
                        (new_qty, inv_id),
                    )
            elif quantity_delta > 0:
                attrs = payload.get("attributes", {})
                attrs_json = json.dumps(attrs) if attrs else "{}"
                conn.execute(
                    """INSERT INTO inventory (id, owner_id, item_name, quantity, attributes_json)
                       VALUES (?, ?, ?, ?, ?)""",
                    (inv_id, owner_id, item_name, quantity_delta, attrs_json),
                )

        elif event_type == "NPC_SPAWN":
            # Insert new character from CastingAgent output
            name = payload.get("name")
            role = payload.get("role", "NPC")
            location_id = payload.get("location_id")
            relationship_score = payload.get("relationship_score", 0)
            secret_agenda = payload.get("secret_agenda")
            stats_json = json.dumps(payload.get("stats_json") or {})
            hp_current = payload.get("hp_current", 10)
            char_id = payload.get("character_id")
            if char_id and name is not None and location_id is not None:
                try:
                    conn.execute(
                        """INSERT INTO characters (id, campaign_id, name, role, location_id, stats_json, hp_current, relationship_score, secret_agenda, credits)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                        (char_id, campaign_id, name, role, location_id, stats_json, hp_current, relationship_score or None, secret_agenda),
                    )
                except sqlite3.IntegrityError:
                    pass

        elif event_type == "STARSHIP_ACQUIRED":
            ship_type = payload.get("ship_type")
            acquired_method = payload.get("acquired_method", "quest")
            custom_name = payload.get("custom_name")
            if ship_type:
                try:
                    conn.execute(
                        """INSERT INTO player_starships (campaign_id, ship_type, custom_name, acquired_method)
                           VALUES (?, ?, ?, ?)""",
                        (campaign_id, ship_type, custom_name, acquired_method),
                    )
                except sqlite3.IntegrityError:
                    pass
                # Update world_state_json flags so pipeline nodes can detect starship ownership
                state = _load_world_state(conn, campaign_id)
                if state is not None:
                    state["has_starship"] = True
                    state["active_starship"] = ship_type
                    _save_world_state(conn, campaign_id, state)

    if commit:
        conn.commit()
