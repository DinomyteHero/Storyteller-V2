"""Commit node factory (DB writes)."""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)

from backend.app.core.error_handling import log_error_with_context
from backend.app.core.event_store import append_events, get_current_turn_number
from backend.app.core.projections import apply_projection
from backend.app.core.state_loader import build_initial_gamestate, load_turn_history
from backend.app.core.transcript_store import write_rendered_turn
from backend.app.core.ledger import update_ledger, update_era_summaries
from backend.app.constants import MEMORY_COMPRESSION_CHUNK_SIZE
from backend.app.core.encounter_throttle import (
    apply_last_location_update_from_event,
    apply_npc_introduction_from_event,
)
from backend.app.models.dialogue_turn import (
    DialogueTurn,
    NPCUtterance,
    PlayerResponse,
    SceneFrame,
    ValidationReport,
)
from backend.app.models.events import Event


def make_commit_node():
    """Commit node: all DB writes happen here. Reads conn from state['__runtime_conn']."""

    def commit_node(state: dict[str, Any]) -> dict[str, Any]:
        conn: sqlite3.Connection = state["__runtime_conn"]
        campaign_id = state.get("campaign_id", "")
        player_id = state.get("player_id", "")
        intent = state.get("intent")
        user_input = (state.get("user_input") or "").strip()
        mechanic_result = state.get("mechanic_result") or {}
        final_text = state.get("final_text")
        suggested_actions = state.get("suggested_actions") or []

        next_turn_number = get_current_turn_number(conn, campaign_id) + 1
        events: list[Event] = [
            Event(event_type="TURN", payload={"user_input": user_input}, is_hidden=True),
        ]
        spawn_events = state.get("spawn_events") or []
        for e in spawn_events:
            if isinstance(e, Event):
                events.append(e)
            elif isinstance(e, dict):
                events.append(Event(event_type=e.get("event_type", "NPC_SPAWN"), payload=e.get("payload") or {}, is_hidden=e.get("is_hidden", False)))
        if intent == "TALK":
            events.append(
                Event(
                    event_type="DIALOGUE",
                    payload={"speaker": "Player", "text": user_input},
                )
            )
        if mechanic_result:
            mech_events = mechanic_result.get("events") or []
            for e in mech_events:
                if isinstance(e, dict):
                    events.append(
                        Event(event_type=e.get("event_type", ""), payload=e.get("payload") or {})
                    )
                else:
                    events.append(e)

        world_sim_events = list(state.get("world_sim_events") or [])
        if not world_sim_events:
            world_sim_events = list(state.get("world_sim_rumors") or [])
        for e in world_sim_events:
            if isinstance(e, Event):
                events.append(e)
            elif isinstance(e, dict):
                events.append(Event(
                    event_type=e.get("event_type", "RUMOR"),
                    payload=e.get("payload") or {},
                    is_hidden=e.get("is_hidden", False),
                    is_public_rumor=e.get("is_public_rumor", False),
                ))

        throttle_events = state.get("throttle_events") or []
        for e in throttle_events:
            if isinstance(e, Event):
                events.append(e)
            elif isinstance(e, dict):
                events.append(Event(
                    event_type=e.get("event_type", ""),
                    payload=e.get("payload") or {},
                    is_hidden=e.get("is_hidden", True),
                ))

        try:
            if not conn.in_transaction:
                conn.execute("BEGIN")
            if intent != "META":
                pending = state.get("pending_world_time_minutes")
                if pending is not None:
                    events.append(
                        Event(
                            event_type="WORLD_TIME_ADVANCE",
                            payload={"mode": "set", "world_time_minutes": int(pending)},
                            is_hidden=True,
                        )
                    )
                else:
                    time_cost = int(mechanic_result.get("time_cost_minutes") or 0)
                    if time_cost > 0:
                        events.append(
                            Event(
                                event_type="WORLD_TIME_ADVANCE",
                                payload={"mode": "add", "minutes": time_cost},
                                is_hidden=True,
                            )
                        )
            _raw_ws = (state.get("campaign") or {}).get("world_state_json")
            world_state = dict(_raw_ws) if isinstance(_raw_ws, dict) else {}
            if state.get("world_sim_ran") and state.get("world_sim_factions_update") is not None:
                world_state = {**world_state, "active_factions": state["world_sim_factions_update"]}
            camp = state.get("campaign") or {}
            for key in ("party_affinity", "loyalty_progress", "banter_queue", "alignment", "faction_reputation", "party", "party_traits", "news_feed"):
                if key in camp:
                    world_state[key] = camp[key]
            world_state["ledger"] = update_ledger(
                world_state.get("ledger"),
                events,
                final_text or "",
            )
            # V2.5: project stress changes to characters.psych_profile (authoritative).
            stress_delta = int(mechanic_result.get("stress_delta", 0))
            if stress_delta != 0:
                events.append(
                    Event(
                        event_type="PLAYER_PSYCH_UPDATE",
                        payload={"character_id": player_id, "stress_delta": stress_delta},
                        is_hidden=True,
                    )
                )
            # Compress old turns into era summaries (non-fatal on failure)
            try:
                from backend.app.core.event_store import get_events as _get_events

                era_summaries = list(world_state.get("era_summaries") or [])
                last_compressed_turn = len(era_summaries) * MEMORY_COMPRESSION_CHUNK_SIZE
                since_turn = max(0, last_compressed_turn + 1)
                recent_campaign_events = _get_events(
                    conn,
                    campaign_id,
                    since_turn=since_turn,
                    include_hidden=False,
                )
                world_state = update_era_summaries(world_state, next_turn_number, recent_campaign_events)
            except Exception as _era_err:
                logger.warning("Era summary compression failed (non-fatal): %s", _era_err)
            # Persist arc state from arc planner (Phase 4: dynamic arc staging)
            arc_guidance = state.get("arc_guidance") or {}
            if isinstance(arc_guidance, dict) and "arc_state" in arc_guidance:
                world_state["arc_state"] = arc_guidance["arc_state"]
            # Era transition: execute if pending
            if isinstance(arc_guidance, dict) and arc_guidance.get("era_transition_pending"):
                try:
                    from backend.app.core.era_transition import get_next_era, execute_transition
                    current_era = camp.get("time_period") or camp.get("era") or ""
                    next_era = get_next_era(current_era) if current_era else None
                    if next_era:
                        world_state = execute_transition(world_state, current_era, next_era)
                        # Update the campaign's time_period
                        conn.execute(
                            "UPDATE campaigns SET time_period = ? WHERE id = ?",
                            (next_era, campaign_id),
                        )
                        events.append(Event(
                            event_type="ERA_TRANSITION",
                            payload={
                                "from_era": current_era,
                                "to_era": next_era,
                            },
                            is_hidden=False,
                        ))
                        logger.info(
                            "Era transition committed: %s -> %s (campaign %s)",
                            current_era, next_era, campaign_id,
                        )
                except Exception as _era_trans_err:
                    logger.warning(
                        "Era transition failed (non-fatal): %s", _era_trans_err
                    )
            # Persist companion memories (Phase 5: deep companion system)
            pending_moments = camp.get("pending_companion_moments") or []
            if pending_moments:
                from backend.app.core.companion_reactions import record_companion_moment
                for moment in pending_moments:
                    if isinstance(moment, dict) and moment.get("companion_id") and moment.get("text"):
                        record_companion_moment(world_state, moment["companion_id"], moment["text"])
            # V2.20: Persist PartyState (sync legacy fields into party_state)
            try:
                from backend.app.core.party_state import load_party_state, save_party_state
                _ps = load_party_state(world_state)
                save_party_state(world_state, _ps)
            except Exception as _ps_err:
                logger.warning("PartyState persistence failed (non-fatal): %s", _ps_err)

            # V2.12: Mark present NPCs as known (player has seen them in the scene)
            _known = set(world_state.get("known_npcs") or [])
            for npc in (state.get("present_npcs") or []):
                npc_name = npc.get("name", "") if isinstance(npc, dict) else ""
                if npc_name:
                    _known.add(npc_name)
            world_state["known_npcs"] = sorted(_known)

            # V3.0: Quest tracking — check entry/stage conditions after events committed
            try:
                from backend.app.core.quest_tracker import process_quests_for_turn
                quest_era = str(camp.get("time_period") or camp.get("era") or "REBELLION").strip()
                quest_events = [
                    {"event_type": e.event_type, "payload": e.payload or {}}
                    if isinstance(e, Event) else e
                    for e in events
                ]
                quest_notifications = process_quests_for_turn(
                    world_state, quest_era, next_turn_number,
                    state.get("current_location"), quest_events,
                )
                if quest_notifications:
                    existing_warnings = list(state.get("warnings") or [])
                    for qn in quest_notifications:
                        existing_warnings.append(f"[QUEST] {qn}")
                    state["warnings"] = existing_warnings
            except Exception as _quest_err:
                logger.warning("Quest tracking failed (non-fatal): %s", _quest_err)

            conn.execute(
                "UPDATE campaigns SET world_state_json = ? WHERE id = ?",
                (json.dumps(world_state), campaign_id),
            )
            append_events(conn, campaign_id, next_turn_number, events, commit=False)
            apply_projection(conn, campaign_id, events, commit=False)
            for e in throttle_events:
                if isinstance(e, Event):
                    event_type = e.event_type
                    payload = e.payload or {}
                elif isinstance(e, dict):
                    event_type = e.get("event_type", "")
                    payload = e.get("payload") or {}
                else:
                    continue
                if event_type == "NPC_INTRODUCTION_RECORDED":
                    npc_id = payload.get("npc_id")
                    world_time = payload.get("world_time_minutes", 0)
                    trigger = payload.get("trigger", "spawn")
                    if npc_id:
                        apply_npc_introduction_from_event(conn, campaign_id, npc_id, world_time, trigger)
                elif event_type == "LAST_LOCATION_UPDATED":
                    effective_loc = payload.get("effective_location")
                    apply_last_location_update_from_event(conn, campaign_id, effective_loc)
            # V2.15: Suggestions come from Director's generate_suggestions() only.
            # embedded_suggestions is always None (Narrator writes prose only).
            final_suggestions = suggested_actions
            write_rendered_turn(
                conn,
                campaign_id,
                next_turn_number,
                final_text or "",
                state.get("lore_citations") or [],
                final_suggestions,
                commit=False,
            )
            # Episodic memory: store turn summary for long-term recall
            try:
                from backend.app.core.episodic_memory import EpisodicMemory
                epi = EpisodicMemory(conn, campaign_id)
                npcs_present = [
                    n.get("name", "") for n in (state.get("present_npcs") or [])
                    if n.get("name")
                ]
                key_events_for_mem = []
                for e in events:
                    if isinstance(e, Event) and not e.is_hidden:
                        key_events_for_mem.append({
                            "event_type": e.event_type,
                            "payload": e.payload or {},
                        })
                    elif isinstance(e, dict) and not e.get("is_hidden"):
                        key_events_for_mem.append({
                            "event_type": e.get("event_type", ""),
                            "payload": e.get("payload") or {},
                        })
                stress_lvl = 0
                player_data = state.get("player")
                if isinstance(player_data, dict):
                    psych = player_data.get("psych_profile") or {}
                    stress_lvl = int(psych.get("stress_level", 0) or 0)
                elif player_data and hasattr(player_data, "psych_profile"):
                    psych = getattr(player_data, "psych_profile", None) or {}
                    stress_lvl = int(psych.get("stress_level", 0) or 0)
                arc_g = state.get("arc_guidance") or {}
                cur_arc = arc_g.get("arc_stage") if isinstance(arc_g, dict) else None
                cur_beat = arc_g.get("hero_beat") if isinstance(arc_g, dict) else None
                prev_arc = (arc_g.get("arc_state") or {}).get("current_stage") if isinstance(arc_g, dict) else None
                epi.store(
                    turn_number=next_turn_number,
                    location_id=state.get("current_location"),
                    npcs_present=npcs_present,
                    key_events=key_events_for_mem,
                    stress_level=stress_lvl,
                    arc_stage=cur_arc,
                    hero_beat=cur_beat,
                    narrative_text=final_text or "",
                    prev_arc_stage=prev_arc,
                )
            except Exception as _epi_err:
                logger.warning(
                    "Episodic memory store failed (non-fatal): %s", _epi_err
                )
            conn.commit()
        except Exception as e:
            conn.rollback()
            log_error_with_context(
                error=e,
                node_name="commit",
                campaign_id=campaign_id,
                turn_number=next_turn_number,
                agent_name="CommitNode",
                extra_context={"intent": intent, "user_input": user_input[:100] if user_input else None},
            )
            raise

        refreshed = build_initial_gamestate(conn, campaign_id, player_id)
        refreshed_dict = refreshed.model_dump(mode="json")
        refreshed_dict["history"] = load_turn_history(conn, campaign_id, limit=10)
        refreshed_dict["final_text"] = final_text
        refreshed_dict["suggested_actions"] = suggested_actions
        refreshed_dict["embedded_suggestions"] = state.get("embedded_suggestions")
        refreshed_dict["lore_citations"] = state.get("lore_citations") or []
        refreshed_dict["warnings"] = state.get("warnings") or []

        # V2.17: Assemble DialogueTurn from pipeline state
        scene_frame_data = state.get("scene_frame")
        npc_utterance_data = state.get("npc_utterance")
        player_responses_data = state.get("player_responses") or []
        if scene_frame_data and npc_utterance_data:
            try:
                dialogue_turn = DialogueTurn(
                    turn_id=f"{campaign_id}_t{next_turn_number}",
                    scene_frame=SceneFrame.model_validate(scene_frame_data),
                    npc_utterance=NPCUtterance.model_validate(npc_utterance_data),
                    player_responses=[
                        PlayerResponse.model_validate(pr)
                        for pr in player_responses_data
                    ],
                    narrated_prose=final_text or "",
                    validation=None,
                )
                refreshed_dict["dialogue_turn"] = dialogue_turn.model_dump(mode="json")
            except Exception as _dt_err:
                logger.warning("DialogueTurn assembly failed (non-fatal): %s", _dt_err)
                refreshed_dict["dialogue_turn"] = None
        else:
            refreshed_dict["dialogue_turn"] = None

        return refreshed_dict

    return commit_node
