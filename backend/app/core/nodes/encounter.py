"""Encounter node factory."""
from __future__ import annotations

import logging
import sqlite3
from typing import Any

from backend.app.content.repository import CONTENT_REPOSITORY
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


def _slugify_name(name: str) -> str:
    return "-".join(part for part in (name or "").lower().replace("_", " ").split() if part)


def _detect_exclusion_trigger(state: dict[str, Any], exclusion_events: list[str]) -> str | None:
    if not exclusion_events:
        return None
    campaign = state.get("campaign") if isinstance(state.get("campaign"), dict) else {}
    ws = campaign.get("world_state_json") if isinstance(campaign.get("world_state_json"), dict) else {}
    arc_guidance = state.get("arc_guidance") if isinstance(state.get("arc_guidance"), dict) else {}
    context_parts = [
        str(ws.get("current_beat") or ""),
        str(ws.get("arc_stage") or ""),
        str(arc_guidance.get("hero_beat") or ""),
        str(state.get("user_input") or ""),
    ]
    haystack = " ".join(context_parts).lower()
    for event_name in exclusion_events:
        event = str(event_name or "").strip()
        if not event:
            continue
        if event.lower() in haystack:
            return event
    return None


def _inject_extended_fields(npc: dict[str, Any], rule: Any) -> None:
    """Copy voice, personality, and knowledge data from a canon rule to an NPC dict."""
    voice = getattr(rule, "voice", None)
    if voice:
        npc["voice"] = voice.model_dump(mode="json") if hasattr(voice, "model_dump") else voice
    for field in (
        "knowledge_boundary", "knowledge_exclusions", "scene_hooks",
        "off_limits", "archetype", "voice_tags", "traits",
        "motivation", "faction_id", "character_voice_id",
    ):
        val = getattr(rule, field, None)
        if val:
            npc[field] = val


def apply_canon_proximity_rules(
    *,
    state: dict[str, Any],
    effective_loc: str | None,
    present_npcs: list[dict[str, Any]],
    background_figures: list[str],
    canon_rules: list[Any],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Enforce historical-mode canon character proximity rules."""
    campaign = state.get("campaign") if isinstance(state.get("campaign"), dict) else {}
    ws = campaign.get("world_state_json") if isinstance(campaign.get("world_state_json"), dict) else {}
    mode = str(ws.get("campaign_mode") or "historical").lower()
    if mode != "historical" or not canon_rules:
        return present_npcs, background_figures, []

    present = list(present_npcs or [])
    bg_figs = [str(x) for x in (background_figures or []) if str(x).strip()]
    warnings: list[str] = []
    loc = str(effective_loc or "").strip()

    for rule in canon_rules:
        name = str(getattr(rule, "name", "") or "").strip()
        proximity = str(getattr(rule, "proximity", "cameo") or "cameo").lower()
        rule_locs = [str(x).strip() for x in (getattr(rule, "locations", []) or []) if str(x).strip()]
        exclusion_events = [str(x).strip() for x in (getattr(rule, "exclusion_events", []) or []) if str(x).strip()]
        if not name:
            continue
        if rule_locs and loc and loc not in rule_locs:
            continue

        # Exclusion events take priority over all proximity tiers (including extended).
        trigger = _detect_exclusion_trigger(state, exclusion_events)
        if trigger:
            present = [npc for npc in present if str(npc.get("name", "")).strip().lower() != name.lower()]
            msg = f"[CANON] {name} is canon-protected during '{trigger}'. You are redirected away from that event."
            warnings.append(msg)
            bg_figs.append(f"Your orders pull you away from {trigger} before you can intervene directly.")
            continue

        if proximity == "exclusion":
            # Exclusion without active trigger — no-op (character not forced out).
            continue

        if proximity == "cameo":
            present = [npc for npc in present if str(npc.get("name", "")).strip().lower() != name.lower()]
            cameo_line = f"You spot {name} at a distance, surrounded by events larger than this moment."
            if cameo_line not in bg_figs:
                bg_figs.append(cameo_line)
            continue

        if proximity == "interaction":
            found = False
            for npc in present:
                if str(npc.get("name", "")).strip().lower() == name.lower():
                    npc["canon_protected"] = True
                    npc["canon_proximity"] = "interaction"
                    found = True
                    break
            if not found:
                present.append(
                    {
                        "id": f"canon-{_slugify_name(name)}",
                        "name": name,
                        "role": "Canon Figure",
                        "relationship_score": 0,
                        "location_id": loc or None,
                        "has_secret_agenda": False,
                        "canon_protected": True,
                        "canon_proximity": "interaction",
                    }
                )
            warnings.append(f"[CANON] {name} may appear, but their established fate cannot be altered.")
            continue

        if proximity == "extended":
            found = False
            for npc in present:
                if str(npc.get("name", "")).strip().lower() == name.lower():
                    npc["canon_protected"] = True
                    npc["canon_proximity"] = "extended"
                    _inject_extended_fields(npc, rule)
                    found = True
                    break
            if not found:
                extended_npc: dict[str, Any] = {
                    "id": f"canon-{_slugify_name(name)}",
                    "name": name,
                    "role": getattr(rule, "role", None) or "Canon Figure",
                    "relationship_score": 0,
                    "location_id": loc or None,
                    "has_secret_agenda": False,
                    "canon_protected": True,
                    "canon_proximity": "extended",
                }
                _inject_extended_fields(extended_npc, rule)
                present.append(extended_npc)
            warnings.append(
                f"[CANON EXTENDED] {name} is present for extended interaction. "
                f"Their established fate cannot be altered."
            )
            continue

    dedup_warnings = list(dict.fromkeys(warnings))
    return present, bg_figs, dedup_warnings


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
                # V12.0: Unified cloud resolution for CastingAgent
                try:
                    from backend.app.core.nodes._cloud_helper import make_turn_llm
                    from backend.app.core.nodes import dict_to_state
                    _cast_gs = dict_to_state(state)
                    _cast_llm = make_turn_llm("casting", _cast_gs, conn)
                    casting = CastingAgent(llm=_cast_llm)
                except Exception as e:
                    logger.warning(
                        "Failed to initialize CastingAgent with cloud LLM for campaign %s, using fallback: %s",
                        campaign_id,
                        e,
                        exc_info=True,
                    )
                    try:
                        casting = CastingAgent(llm=AgentLLM("casting"))
                    except Exception:
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
            # V3.0: Check generated NPCs from campaign world generation
            present = []
            try:
                ws = throttle_load_world_state(conn, campaign_id)
                gen_npcs = ws.get("generated_npcs") or []
                for gnpc in gen_npcs:
                    if isinstance(gnpc, dict) and gnpc.get("default_location_id") == effective_loc:
                        present.append({
                            "id": gnpc.get("id", ""),
                            "name": gnpc.get("name", "Wanderer"),
                            "role": gnpc.get("role", "NPC"),
                            "relationship_score": 0,
                            "location_id": effective_loc,
                            "has_secret_agenda": bool(gnpc.get("secret")),
                        })
                if present:
                    logger.info("Encounter: found %d generated NPCs at %s", len(present), effective_loc)
            except Exception as e:
                logger.debug("Failed to check generated NPCs: %s", e)
        throttle_events.append(
            Event(
                event_type="LAST_LOCATION_UPDATED",
                payload={"effective_location": effective_loc},
                is_hidden=True,
            )
        )
        active_rumors = get_recent_public_rumors(conn, campaign_id, limit=3)
        canon_warnings: list[str] = []
        try:
            campaign = state.get("campaign") if isinstance(state.get("campaign"), dict) else {}
            era_id = str(campaign.get("time_period") or "").strip()
            era_pack = CONTENT_REPOSITORY.get_pack(era_id) if era_id else None
            canon_rules = list(getattr(era_pack, "canon_characters", []) or []) if era_pack else []
            present, background_figures, canon_warnings = apply_canon_proximity_rules(
                state=state,
                effective_loc=effective_loc,
                present_npcs=present,
                background_figures=list(background_figures or []),
                canon_rules=canon_rules,
            )
        except Exception as e:
            logger.debug("Canon proximity enforcement skipped (non-fatal): %s", e)

        warnings = list(state.get("warnings") or [])
        if canon_warnings:
            warnings.extend(canon_warnings)
        return {
            **state,
            "present_npcs": present,
            "spawn_events": spawn_events,
            "throttle_events": throttle_events,
            "active_rumors": active_rumors,
            "background_figures": background_figures,
            "warnings": warnings,
        }

    return encounter_node
