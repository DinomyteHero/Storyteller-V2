"""World simulation node factory.

V4.0: Uses WorldMindAgent (LLM) instead of the deterministic faction engine.
The LLM reasons about world state + player action and generates contextually
appropriate rumors, faction moves, and hidden events.
"""
from __future__ import annotations

import logging
import math
import sqlite3
from typing import Any

from backend.app.config import WORLD_TICK_INTERVAL_HOURS
from backend.app.core.state_loader import load_campaign
from backend.app.models.news import rumors_to_news_feed, NEWS_FEED_MAX

logger = logging.getLogger(__name__)


def world_sim_tick_crosses_boundary(t0: int, t1: int, tick_minutes: int) -> bool:
    """PRE-COMMIT tick: True if moving from t0 to t1 crosses one or more tick boundaries."""
    if tick_minutes <= 0:
        return False
    return math.floor(t0 / tick_minutes) != math.floor(t1 / tick_minutes)


def _world_sim_travel_occurred(mechanic_result: dict[str, Any]) -> bool:
    """True if this turn involved player travel (MOVE event or TRAVEL action)."""
    if not mechanic_result:
        return False
    events = mechanic_result.get("events") or []
    if any(e.get("event_type") == "MOVE" for e in events if isinstance(e, dict)):
        return True
    if mechanic_result.get("action_type") == "TRAVEL":
        return True
    return False


def make_world_sim_node():
    """WorldSimNode: LLM-based world simulation (no DB writes).

    Reads conn from state['__runtime_conn'].
    Calls WorldMindAgent to generate contextual rumors, faction moves, and
    hidden plot events that respond to the player's action. Falls back to
    empty output on LLM failure so a world sim error never breaks a turn.
    """
    interval_minutes = WORLD_TICK_INTERVAL_HOURS * 60

    def world_sim_node(state: dict[str, Any]) -> dict[str, Any]:
        conn: sqlite3.Connection | None = state.get("__runtime_conn")
        campaign = state.get("campaign") or {}
        t0 = int(campaign.get("world_time_minutes") or 0)
        mechanic_result = state.get("mechanic_result") or {}
        dt = int(mechanic_result.get("time_cost_minutes") or 0)
        t1 = t0 + dt
        campaign_id = state.get("campaign_id", "")
        tick_crossed = world_sim_tick_crosses_boundary(t0, t1, interval_minutes)
        travel_occurred = _world_sim_travel_occurred(mechanic_result)
        # V2.5: Also trigger on major player events (e.g. NPC death, faction flag)
        world_reaction_needed = bool(mechanic_result.get("world_reaction_needed", False))
        # One sim per turn: run when tick boundary crossed OR travel OR world reaction needed
        run_sim = tick_crossed or travel_occurred or world_reaction_needed

        if not run_sim:
            return {
                **state,
                "pending_world_time_minutes": t1,
                "world_sim_rumors": [],
                "world_sim_factions_update": None,
                "world_sim_ran": False,
                "world_sim_events": state.get("world_sim_events") or [],
                "new_rumors": state.get("new_rumors") or [],
            }

        active_factions: list[dict] = []
        if conn and campaign_id:
            loaded = load_campaign(conn, campaign_id)
            if loaded:
                world_state = loaded.get("world_state_json")
                if isinstance(world_state, dict):
                    active_factions = world_state.get("active_factions") or []

        # Extract arc stage for story-phase-aware simulation
        campaign_ws = campaign.get("world_state_json") if isinstance(campaign, dict) else None
        if not isinstance(campaign_ws, dict):
            campaign_ws = {}
        arc_state = campaign_ws.get("arc_state") or {}
        arc_stage = arc_state.get("current_stage", "SETUP")

        # Build action summaries for the LLM
        user_action_summary = (state.get("user_input") or "").strip()[:200]

        mechanic_result = state.get("mechanic_result") or {}
        mechanic_result_summary = str(
            mechanic_result.get("outcome_summary") or ""
        ).strip()[:300]
        if not mechanic_result_summary:
            dice = mechanic_result.get("dice_result", "")
            action = mechanic_result.get("action_type", "")
            if dice and action:
                mechanic_result_summary = f"{action}: {dice}"

        # Load faction memory and NPC states from persisted world state
        faction_memory = campaign_ws.get("faction_memory") or {}
        npc_states = campaign_ws.get("npc_states") or {}

        # Load known NPCs from characters table for NPC context
        known_npcs: list[dict] = []
        if conn and campaign_id:
            try:
                import json as _json
                rows = conn.execute(
                    "SELECT id, name, role, location_id, stats_json, relationship_score"
                    " FROM characters WHERE campaign_id = ? AND role != 'Player'",
                    (campaign_id,),
                ).fetchall()
                for r in rows:
                    stats = {}
                    raw = r[4] if len(r) > 4 else "{}"
                    if raw:
                        try:
                            stats = _json.loads(raw) if isinstance(raw, str) else raw
                        except (TypeError, _json.JSONDecodeError):
                            stats = {}
                    known_npcs.append({
                        "character_id": r[0],
                        "name": r[1],
                        "role": r[2],
                        "location_id": r[3],
                        "stats_json": stats if isinstance(stats, dict) else {},
                        "relationship_score": r[5],
                    })
            except Exception:
                logger.debug("Failed to load known NPCs for world sim", exc_info=True)

        # V4.0: LLM-based world simulation via WorldMindAgent
        # V12.0: Unified cloud resolution
        _wm_llm = None
        try:
            from backend.app.core.nodes._cloud_helper import make_turn_llm
            from backend.app.core.nodes import dict_to_state
            _wm_gs = dict_to_state(state)
            _wm_llm = make_turn_llm("world_mind", _wm_gs, conn)
        except Exception as _wm_cloud_err:
            logger.debug("WorldMind cloud resolution failed, using default: %s", _wm_cloud_err)

        try:
            from backend.app.core.agents.world_mind_agent import WorldMindAgent
            out = WorldMindAgent(llm=_wm_llm).simulate(
                active_factions=active_factions,
                turn_number=int(state.get("turn_number") or 0),
                player_location=state.get("current_location") or "loc-cantina",
                arc_stage=arc_stage,
                world_time_minutes=t1,
                travel_occurred=travel_occurred,
                world_reaction_needed=world_reaction_needed,
                user_action_summary=user_action_summary,
                mechanic_result_summary=mechanic_result_summary,
                faction_memory=faction_memory,
                npc_states=npc_states,
                known_npcs=known_npcs,
            )
        except Exception as _wsim_err:
            logger.warning(
                "WorldMindAgent failed for campaign %s (non-fatal): %s",
                campaign_id, _wsim_err,
            )
            from shared.schemas import WorldSimOutput as _WorldSimOutput
            out = _WorldSimOutput(
                elapsed_time_summary="Time passes quietly.",
                faction_moves=[],
                new_rumors=[],
                hidden_events=[],
                updated_factions=active_factions if active_factions else None,
                faction_memory=faction_memory,
                npc_states=npc_states,
            )

        # --- Phase 5.2: NPC death propagation ---
        # Check mechanic_result for DAMAGE events where NPC HP reaches 0 or explicit death events.
        npc_death_flag = False
        npc_death_rumors: list[str] = []
        npc_death_wave_consequences: list[dict] = []
        mr_events = mechanic_result.get("events") or []
        for ev in mr_events:
            if not isinstance(ev, dict):
                continue
            ev_type = (ev.get("event_type") or "").upper()
            payload = ev.get("payload") or {}
            if not isinstance(payload, dict):
                payload = {}

            npc_name = payload.get("target_name") or payload.get("npc_name") or payload.get("name") or ""
            npc_id = payload.get("target_id") or payload.get("npc_id") or payload.get("character_id") or ""

            is_death = False
            if ev_type == "DAMAGE":
                remaining_hp = payload.get("remaining_hp", payload.get("hp_after"))
                if remaining_hp is not None and int(remaining_hp) <= 0:
                    is_death = True
            if ev_type in ("NPC_DEATH", "DEATH", "KILL"):
                is_death = True
            if payload.get("death") or payload.get("killed") or payload.get("lethal"):
                is_death = True

            if is_death and (npc_name or npc_id):
                npc_death_flag = True
                display_name = npc_name or npc_id
                # Create a rumor about the death
                death_rumor = f"{display_name} has been killed. Word is spreading fast."
                npc_death_rumors.append(death_rumor)
                # Create a wave consequence
                npc_death_wave_consequences.append({
                    "event_type": "NPC_DEATH_WAVE",
                    "payload": {
                        "text": f"The death of {display_name} sends ripples through the area.",
                        "npc_name": display_name,
                        "npc_id": npc_id,
                        "impact_tier": "wave",
                    },
                    "is_hidden": False,
                })

        # Inject death rumors into WorldMindAgent output
        if npc_death_rumors:
            combined_rumors = list(out.new_rumors or []) + npc_death_rumors
            out = out.model_copy(update={"new_rumors": combined_rumors}) if hasattr(out, "model_copy") else out
            # Fallback for objects without model_copy
            if not hasattr(out, "model_copy"):
                for dr in npc_death_rumors:
                    if out.new_rumors is None:
                        out.new_rumors = []
                    out.new_rumors.append(dr)

        # --- Process output into events (same format as LLM-based version) ---
        rumor_events: list[dict] = []
        world_sim_events: list[dict] = []
        for text in out.new_rumors or []:
            ev = {
                "event_type": "RUMOR_SPREAD",
                "payload": {"text": text},
                "is_hidden": False,
                "is_public_rumor": True,
            }
            rumor_events.append(ev)
            world_sim_events.append(ev)

        # Add NPC death wave consequences to world_sim_events
        for wave_ev in npc_death_wave_consequences:
            world_sim_events.append(wave_ev)

        for text in out.faction_moves or []:
            world_sim_events.append({
                "event_type": "FACTION_MOVE",
                "payload": {"text": text},
                "is_hidden": True,
                "player_unaware": True,  # V10.0: Dramatic irony — player doesn't know this
            })

        for text in out.hidden_events or []:
            lowered = str(text).lower()
            event_type = "NPC_ACTION" if ("npc" in lowered or "agent" in lowered or "assassin" in lowered) else "PLOT_TICK"
            world_sim_events.append({
                "event_type": event_type,
                "payload": {"text": text},
                "is_hidden": True,
                "player_unaware": True,  # V10.0: Dramatic irony — player doesn't know this
            })

        for f in out.updated_factions or []:
            if not isinstance(f, dict):
                continue
            payload = {
                "faction": f.get("name"),
                "location": f.get("location"),
                "current_goal": f.get("current_goal"),
                "resources": f.get("resources"),
                "is_hostile": f.get("is_hostile"),
            }
            world_sim_events.append({
                "event_type": "FACTION_MOVE",
                "payload": payload,
                "is_hidden": True,
            })

        campaign = dict(state.get("campaign") or {})
        active_factions = campaign.get("active_factions") or active_factions or []
        faction_names = [f.get("name", "") for f in active_factions if isinstance(f, dict) and f.get("name")]
        existing_feed = campaign.get("news_feed") or []
        news_feed = rumors_to_news_feed(
            list(out.new_rumors or []),
            world_time_minutes=t1,
            active_faction_names=faction_names,
            existing_feed=existing_feed,
            max_items=NEWS_FEED_MAX,
        )
        campaign["news_feed"] = news_feed
        campaign["new_rumors_raw"] = list(out.new_rumors or [])
        # 2.1: Persist faction memory for multi-turn plan continuity
        # 3.1: Persist NPC states for NPC autonomy
        if out.faction_memory or out.npc_states:
            ws = dict(campaign.get("world_state_json") or {})
            if out.faction_memory:
                ws["faction_memory"] = out.faction_memory
            if out.npc_states:
                ws["npc_states"] = out.npc_states
            campaign["world_state_json"] = ws

        return {
            **state,
            "campaign": campaign,
            "pending_world_time_minutes": t1,
            "world_sim_rumors": rumor_events,
            "world_sim_factions_update": out.updated_factions,
            "world_sim_ran": True,
            "world_sim_debug": getattr(out, "elapsed_time_summary", None) or ("travel" if travel_occurred else "tick"),
            "world_sim_events": world_sim_events,
            "new_rumors": list(out.new_rumors or []),
            # Phase 5.2: NPC death propagation flag
            "npc_death_occurred": npc_death_flag,
        }

    return world_sim_node
