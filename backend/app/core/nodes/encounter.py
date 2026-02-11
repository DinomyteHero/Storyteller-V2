"""Encounter node factory."""
from __future__ import annotations

import logging
import sqlite3
from typing import Any

from backend.app.core.agents import CastingAgent, EncounterManager
from backend.app.core.agents.base import AgentLLM
from backend.app.core.encounter_throttle import (
    can_introduce_new_npc,
    get_anonymous_extras,
    get_introduced_npc_names,
    load_world_state as throttle_load_world_state,
)
from backend.app.core.event_store import get_recent_public_rumors
from backend.app.models.events import Event

logger = logging.getLogger(__name__)


def make_encounter_node():
    """Encounter node: set present_npcs; spawn via CastingAgent only when throttling allows."""

    def _effective_location(s: dict) -> str | None:
        from backend.app.core.encounter_throttle import get_effective_location
        return get_effective_location(s)

    def encounter_node(state: dict[str, Any]) -> dict[str, Any]:
        conn: sqlite3.Connection = state["__runtime_conn"]
        manager = EncounterManager(conn)
        campaign_id = state.get("campaign_id", "")
        effective_loc = _effective_location(state) or state.get("current_location")
        npcs, spawn_payloads, spawn_request, departure_payloads, background_figures = manager.check(campaign_id, effective_loc, state=state)
        spawn_events: list[Event] = []
        throttle_events: list[Event] = []
        for dep in departure_payloads:
            spawn_events.append(
                Event(event_type="NPC_DEPART", payload=dep, is_hidden=True)
            )
        present: list[dict]
        if spawn_payloads:
            allowed, _reason = can_introduce_new_npc(conn, campaign_id, state)
            if allowed:
                for payload in spawn_payloads:
                    char_id = payload.get("character_id") or payload.get("id")
                    if not char_id:
                        continue
                    spawn_events.append(
                        Event(event_type="NPC_SPAWN", payload={**payload, "character_id": char_id})
                    )
                    campaign = state.get("campaign") or {}
                    world_time = int(campaign.get("world_time_minutes") or 0)
                    mechanic_result = state.get("mechanic_result") or {}
                    time_cost = int(mechanic_result.get("time_cost_minutes") or 0)
                    total_world_time = world_time + time_cost
                    throttle_events.append(
                        Event(
                            event_type="NPC_INTRODUCTION_RECORDED",
                            payload={
                                "npc_id": char_id,
                                "world_time_minutes": total_world_time,
                                "trigger": "spawn",
                            },
                            is_hidden=True,
                        )
                    )
                present = npcs or []
            else:
                present = get_anonymous_extras(effective_loc)
        elif spawn_request and not npcs:
            allowed, _reason = can_introduce_new_npc(conn, campaign_id, state)
            if allowed:
                try:
                    casting = CastingAgent(llm=AgentLLM("casting"))
                except Exception as e:
                    logger.warning(
                        "Failed to initialize CastingAgent with LLM for campaign %s, using fallback: %s",
                        campaign_id,
                        e,
                        exc_info=True,
                    )
                    casting = CastingAgent(llm=None)
                introduced_names = get_introduced_npc_names(conn, campaign_id)
                ws = throttle_load_world_state(conn, campaign_id)
                triggers = ws.get("npc_introduction_triggers") or []
                payload = casting.spawn(
                    spawn_request["campaign_id"],
                    spawn_request["location_id"],
                    context=state.get("user_input", ""),
                    introduced_npcs=introduced_names,
                    npc_introduction_triggers=triggers if triggers else None,
                    warnings=state.get("warnings"),
                )
                char_id = payload.get("character_id")
                if char_id:
                    spawn_events.append(
                        Event(event_type="NPC_SPAWN", payload={**payload, "character_id": char_id})
                    )
                    campaign = state.get("campaign") or {}
                    world_time = int(campaign.get("world_time_minutes") or 0)
                    mechanic_result = state.get("mechanic_result") or {}
                    time_cost = int(mechanic_result.get("time_cost_minutes") or 0)
                    total_world_time = world_time + time_cost
                    throttle_events.append(
                        Event(
                            event_type="NPC_INTRODUCTION_RECORDED",
                            payload={
                                "npc_id": char_id,
                                "world_time_minutes": total_world_time,
                                "trigger": "spawn",
                            },
                            is_hidden=True,
                        )
                    )
                present = [{
                    "id": char_id,
                    "name": payload.get("name", "Wanderer"),
                    "role": payload.get("role", "Wanderer"),
                    "relationship_score": payload.get("relationship_score", 0),
                    "location_id": payload.get("location_id"),
                    "has_secret_agenda": bool(payload.get("secret_agenda")),
                }]
            else:
                present = get_anonymous_extras(spawn_request["location_id"])
        elif npcs:
            present = list(npcs)
        else:
            present = []
        throttle_events.append(
            Event(
                event_type="LAST_LOCATION_UPDATED",
                payload={"effective_location": effective_loc},
                is_hidden=True,
            )
        )
        active_rumors = get_recent_public_rumors(conn, campaign_id, limit=3)
        return {
            **state,
            "present_npcs": present,
            "spawn_events": spawn_events,
            "throttle_events": throttle_events,
            "active_rumors": active_rumors,
            "background_figures": background_figures,
        }

    return encounter_node
