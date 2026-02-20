"""Commit node factory (DB writes)."""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any

logger = logging.getLogger(__name__)

from backend.app.core.error_handling import (  # noqa: E402
    AgentFailureError,
    authoritative_call,
    log_error_with_context,
)
from backend.app.core.event_store import append_events, reserve_next_turn_number  # noqa: E402
from backend.app.core.projections import apply_projection  # noqa: E402
from backend.app.core.state_loader import build_initial_gamestate, load_turn_history  # noqa: E402
from backend.app.core.transcript_store import write_rendered_turn  # noqa: E402
from backend.app.core.ledger import update_ledger, update_era_summaries  # noqa: E402
from backend.app.constants import (  # noqa: E402
    MEMORY_COMPRESSION_CHUNK_SIZE,
    MAINTENANCE_AGENT_FREQUENCY,
    NPC_STATES_MAX,
)
from backend.app.core.story_position import advance_story_position  # noqa: E402
from backend.app.core.encounter_throttle import (  # noqa: E402
    apply_last_location_update_from_event,
    apply_npc_introduction_from_event,
)
from backend.app.models.dialogue_turn import (  # noqa: E402
    DialogueTurn,
    NPCUtterance,
    PlayerResponse,
    SceneFrame,
)
from backend.app.models.events import Event  # noqa: E402
from backend.app.models.event_utils import ensure_event  # noqa: E402


def _extract_latest_turn_from_memories(memories: list[Any]) -> int:
    """Best-effort extraction of latest turn marker from memory strings."""
    latest = 0
    for item in memories or []:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text:
            continue
        upper = text.upper()
        if not upper.startswith("TURN "):
            continue
        digits = []
        for ch in text[5:]:
            if ch.isdigit():
                digits.append(ch)
            else:
                break
        if digits:
            try:
                latest = max(latest, int("".join(digits)))
            except ValueError:
                continue
    return latest


def _touch_and_cap_npc_states(world_state: dict[str, Any], present_npcs: list[dict[str, Any]], turn_number: int) -> None:
    """Stamp present NPC recency and cap npc_states to the most recently seen entries."""
    existing = world_state.get("npc_states") or {}
    if not isinstance(existing, dict):
        existing = {}

    # Mark all currently present NPCs as seen this turn.
    for npc in present_npcs or []:
        if not isinstance(npc, dict):
            continue
        npc_id = str(npc.get("id") or "").strip()
        npc_name = str(npc.get("name") or "").strip()
        target_key = npc_id or npc_name
        if not target_key:
            continue
        entry = existing.get(target_key)
        if not isinstance(entry, dict):
            entry = {}
        entry["last_seen_turn"] = int(turn_number)
        existing[target_key] = entry

    if len(existing) <= NPC_STATES_MAX:
        world_state["npc_states"] = existing
        return

    scored: list[tuple[str, int]] = []
    for key, value in existing.items():
        if not isinstance(value, dict):
            scored.append((key, 0))
            continue
        seen_turn = value.get("last_seen_turn")
        if isinstance(seen_turn, int):
            score = seen_turn
        else:
            memories = value.get("memories") or []
            score = _extract_latest_turn_from_memories(memories if isinstance(memories, list) else [])
        scored.append((key, score))
    scored.sort(key=lambda item: item[1], reverse=True)
    keep_keys = {k for k, _ in scored[:NPC_STATES_MAX]}
    world_state["npc_states"] = {k: v for k, v in existing.items() if k in keep_keys}


def _derive_crystallized_memory(
    *,
    turn_number: int,
    events: list[dict[str, Any]],
    arc_stage: str | None,
    hero_beat: str | None,
    final_text: str,
    location_id: str | None,
    npcs_present: list[str],
) -> dict[str, Any] | None:
    """Build a crystallized-memory payload for major moments, if any."""
    beat = (hero_beat or "").upper()
    stage = (arc_stage or "").upper()

    memory_type = ""
    emotional_tag = ""
    summary = ""

    if beat in {"ORDEAL", "RESURRECTION"} or stage == "CLIMAX":
        memory_type = "arc_climax"
        emotional_tag = "revelation"
        summary = f"Arc climax ({beat or stage}) reshaped the campaign's direction."
    else:
        for ev in events:
            etype = str((ev or {}).get("event_type") or "").upper()
            payload = (ev or {}).get("payload") or {}
            payload_text = json.dumps(payload).upper() if isinstance(payload, dict) else ""
            if "DEATH" in etype:
                memory_type = "death"
                emotional_tag = "loss"
                summary = f"A major death event occurred ({etype})."
                break
            if etype in {"QUEST_COMPLETED", "QUEST_COMPLETE"} or "QUEST COMPLETED" in payload_text:
                memory_type = "quest_completion"
                emotional_tag = "triumph"
                summary = "A key quest reached completion."
                break
            if "COMPANION" in etype and ("LOYAL" in etype or "TRUST" in etype or "LOYAL" in payload_text or "TRUST" in payload_text):
                memory_type = "companion_event"
                emotional_tag = "bond"
                summary = "A companion relationship crossed a major loyalty threshold."
                break

    if not memory_type:
        return None

    prose = (final_text or "").strip()
    if prose:
        summary = prose[:280]
    return {
        "turn_number": int(turn_number),
        "memory_type": memory_type,
        "summary": summary[:400],
        "full_text": prose[:2000],
        "npcs_involved": [n for n in npcs_present[:10] if n],
        "location": location_id,
        "emotional_tag": emotional_tag or None,
    }


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
        commit_started_at = time.perf_counter()
        _segment_last = commit_started_at
        commit_segments: dict[str, float] = {}

        def _mark_segment(name: str) -> None:
            nonlocal _segment_last
            now = time.perf_counter()
            commit_segments[name] = round(now - _segment_last, 3)
            _segment_last = now

        next_turn_number = 0
        run_maintenance_agents = False
        events: list[Event] = [
            Event(event_type="TURN", payload={"user_input": user_input}, is_hidden=True),
        ]
        spawn_events = state.get("spawn_events") or []
        for e in spawn_events:
            event = ensure_event(e, default_event_type="NPC_SPAWN")
            events.append(event)
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
            # For dict events, ensure is_public_rumor is preserved
            if isinstance(e, dict) and "event_type" not in e:
                e = {**e, "event_type": "RUMOR"}
            event = ensure_event(e, default_event_type="RUMOR")
            events.append(event)

        throttle_events = state.get("throttle_events") or []
        for e in throttle_events:
            # For dict events, ensure is_hidden defaults to True for throttle events
            if isinstance(e, dict) and "is_hidden" not in e:
                e = {**e, "is_hidden": True}
            event = ensure_event(e)
            events.append(event)

        try:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            next_turn_number = reserve_next_turn_number(conn, campaign_id)
            run_maintenance_agents = (
                intent != "META"
                and next_turn_number > 0
                and next_turn_number % MAINTENANCE_AGENT_FREQUENCY == 0
            )
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
            _mark_segment("reserve_turn_and_prepare_events")
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
            # V5.0: ContinuityAgent — authoritative LLM semantic pass on the ledger.
            # Runs on maintenance turns to reduce commit-node latency.
            if run_maintenance_agents and final_text and intent != "META":
                from backend.app.core.agents.continuity_agent import ContinuityAgent  # noqa: E402
                _cont_events = [
                    {"event_type": ensure_event(e).event_type, "payload": ensure_event(e).payload or {}}
                    for e in events
                ]
                authoritative_call(
                    "ContinuityAgent",
                    ContinuityAgent().update,
                    world_state=world_state,
                    final_text=final_text,
                    user_input=user_input,
                    mechanic_result=mechanic_result,
                    events=_cont_events,
                )
            # V7.0: Historical Timeline Scheduler — check and trigger canon events.
            _campaign_mode = world_state.get("campaign_mode") or "sandbox"
            _era_id = world_state.get("era_id") or (camp.get("time_period") or "").upper().replace(" ", "_")
            if _campaign_mode == "historical" and _era_id and intent != "META":
                try:
                    from backend.app.core.canon_scheduler import check_canon_events
                    _arc_stage = world_state.get("arc_stage") or state.get("arc_stage") or "SETUP"
                    _triggered = check_canon_events(
                        conn=conn,
                        campaign_id=campaign_id,
                        era_id=_era_id,
                        campaign_mode=_campaign_mode,
                        arc_stage=_arc_stage,
                        turn_number=next_turn_number,
                    )
                    if _triggered:
                        # Surface triggered events as warnings so they reach the player
                        for _ce in _triggered:
                            _ce_title = _ce.get("title", "Canon Event")
                            state.setdefault("warnings", []).append(
                                f"[CANON EVENT] {_ce_title}: {_ce.get('event_text', '')[:200]}"
                            )
                except Exception as _canon_exc:
                    logger.warning("Canon event check failed (non-fatal): %s", _canon_exc)

            # Phase 3.2: Sandbox Consequence Propagation
            if _campaign_mode != "historical" and intent != "META":
                try:
                    from backend.app.core.consequence_propagator import (
                        tick_consequences,
                        create_consequence,
                    )
                    # Tick down existing consequences
                    tick_consequences(world_state)
                    # Create new consequence for wave/tsunami actions
                    _narrative_facts = mechanic_result.get("narrative_facts") or []
                    _impact_tier = "ripple"
                    for _fact in _narrative_facts:
                        if "Sandbox impact tier: tsunami" in str(_fact):
                            _impact_tier = "tsunami"
                            break
                        elif "Sandbox impact tier: wave" in str(_fact):
                            _impact_tier = "wave"
                            break
                    if _impact_tier in ("wave", "tsunami"):
                        _action_summary = mechanic_result.get("outcome_summary") or user_input[:200]
                        _arc_stage = world_state.get("arc_stage") or state.get("arc_stage") or "SETUP"
                        create_consequence(world_state, _impact_tier, _action_summary, _arc_stage)
                except Exception as _cons_exc:
                    logger.warning("Consequence propagation failed (non-fatal): %s", _cons_exc)

            _mark_segment("continuity_and_world_state_updates")
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
                from backend.app.core.event_store import get_events as _get_events  # noqa: E402

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
            # Persist arc state from arc planner (Phase 4: dynamic arc staging, V8.0: multi-arc)
            arc_guidance = state.get("arc_guidance") or {}
            if isinstance(arc_guidance, dict) and "arc_state" in arc_guidance:
                world_state["arc_state"] = arc_guidance["arc_state"]

            # V8.0: Persist new arc seed when multi-arc transition occurs
            if isinstance(arc_guidance, dict) and arc_guidance.get("new_arc_seed"):
                world_state["arc_seed"] = arc_guidance["new_arc_seed"]
                events.append(Event(
                    event_type="ARC_TRANSITION",
                    payload={
                        "new_arc_number": arc_guidance.get("current_arc_number", 0),
                        "new_arc_id": arc_guidance.get("current_arc_id", ""),
                        "previous_arcs": len(arc_guidance.get("arc_history") or []),
                    },
                    is_hidden=False,
                ))

            # V8.0: Campaign completion
            if isinstance(arc_guidance, dict) and arc_guidance.get("campaign_complete"):
                try:
                    conn.execute(
                        "UPDATE campaigns SET status = 'completed' WHERE id = ?",
                        (campaign_id,),
                    )
                    events.append(Event(
                        event_type="CAMPAIGN_COMPLETE",
                        payload={
                            "total_arcs": len(arc_guidance.get("arc_history") or []),
                            "total_turns": next_turn_number,
                        },
                        is_hidden=False,
                    ))
                    logger.info("Campaign %s marked as completed at turn %d", campaign_id, next_turn_number)
                except Exception as _complete_err:
                    logger.warning("Campaign completion update failed (non-fatal): %s", _complete_err)

            # Persist prologue arc state (contains stages_visited for completion tracking)
            if isinstance(arc_guidance, dict) and "prologue_arc_state" in arc_guidance:
                world_state["prologue_arc_state"] = arc_guidance["prologue_arc_state"]

            # Auto-complete prologue when all stages visited
            if world_state.get("prologue_mode"):
                try:
                    from backend.app.core.prologue_engine import is_prologue_complete
                    if is_prologue_complete(world_state):
                        logger.info("Prologue complete for campaign %s — clearing prologue_mode", campaign_id)
                        world_state["prologue_mode"] = False
                        world_state["prologue_completed"] = True
                except Exception as _prol_err:
                    logger.warning("Prologue completion check failed (non-fatal): %s", _prol_err)

            # V3.1: Scale advisor — auto-apply recommended scale change
            scale_rec = arc_guidance.get("scale_recommendation") if isinstance(arc_guidance, dict) else None
            if isinstance(scale_rec, dict) and scale_rec.get("recommended_scale"):
                new_scale = scale_rec["recommended_scale"]
                old_scale = world_state.get("campaign_scale", "medium")
                world_state["campaign_scale"] = new_scale
                world_state["last_scale_change_turn"] = next_turn_number
                events.append(Event(
                    event_type="SCALE_CHANGE",
                    payload={
                        "from_scale": old_scale,
                        "to_scale": new_scale,
                        "direction": scale_rec.get("direction", ""),
                        "reason": scale_rec.get("reason", ""),
                    },
                    is_hidden=False,
                ))
                existing_warnings = list(state.get("warnings") or [])
                existing_warnings.append(
                    f"[SCALE_CHANGED] Campaign scale shifted from {old_scale} to {new_scale}: "
                    f"{scale_rec.get('reason', '')}"
                )
                state["warnings"] = existing_warnings
                logger.info(
                    "Scale auto-applied: %s -> %s (campaign %s, turn %d)",
                    old_scale, new_scale, campaign_id, next_turn_number,
                )

            # V3.1: Conclusion planner — surface conclusion_ready warning
            conclusion_plan = arc_guidance.get("conclusion_plan") if isinstance(arc_guidance, dict) else None
            if isinstance(conclusion_plan, dict):
                world_state["conclusion_plan"] = conclusion_plan
                if conclusion_plan.get("conclusion_ready"):
                    existing_warnings = list(state.get("warnings") or [])
                    existing_warnings.append(
                        f"[CONCLUSION_READY] Campaign ending style: {conclusion_plan.get('ending_style', 'unknown')} "
                        f"(resolved ratio: {conclusion_plan.get('resolved_ratio', 0):.0%})"
                    )
                    state["warnings"] = existing_warnings
            # Era transition: execute if pending
            if isinstance(arc_guidance, dict) and arc_guidance.get("era_transition_pending"):
                try:
                    from backend.app.core.era_transition import get_next_era, execute_transition  # noqa: E402
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
                from backend.app.core.companion_reactions import record_companion_moment  # noqa: E402
                for moment in pending_moments:
                    if isinstance(moment, dict) and moment.get("companion_id") and moment.get("text"):
                        record_companion_moment(world_state, moment["companion_id"], moment["text"])
            # V2.20: Persist PartyState (sync legacy fields into party_state)
            try:
                from backend.app.core.party_state import load_party_state, save_party_state  # noqa: E402
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

            _mark_segment("projection_prep_and_arc_updates")

            # V3.0: Quest tracking — deterministic entry/stage conditions (stays in-transaction)
            try:
                from backend.app.core.quest_tracker import process_quests_for_turn  # noqa: E402
                quest_era = str(camp.get("time_period") or camp.get("era") or "REBELLION").strip()
                quest_events = [
                    {"event_type": ensure_event(e).event_type, "payload": ensure_event(e).payload or {}}
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
                # V2.21: Quest-to-ledger integration — feed quest events into narrative ledger
                if quest_notifications:
                    try:
                        world_state.get("quest_log") or {}
                        ledger = world_state.get("narrative_ledger") or {}
                        facts = list(ledger.get("established_facts") or [])
                        threads = list(ledger.get("open_threads") or [])
                        for qn in quest_notifications:
                            if "completed" in qn.lower():
                                quest_title = qn.replace("Quest completed: ", "")
                                facts.append(f"Resolved: {quest_title}")
                                threads = [t for t in threads if quest_title.lower() not in t.lower()]
                            elif "New quest" in qn:
                                quest_title = qn.replace("New quest: ", "")
                                threads.append(f"Active quest: {quest_title}")
                            elif "Objective complete" in qn:
                                facts.append(qn)
                        ledger["established_facts"] = facts
                        ledger["open_threads"] = threads
                        world_state["narrative_ledger"] = ledger
                    except Exception as _ql_err:
                        logger.warning("Quest-ledger integration failed (non-fatal): %s", _ql_err)
            except Exception as _quest_err:
                logger.warning("Quest tracking failed (non-fatal): %s", _quest_err)

            # V7.0: LLM maintenance agents (Memory, QuestWeaver, Progression, PsychArchivist)
            # are now DEFERRED to run post-commit via deferred_agents.py.
            # This reduces transaction lock time from 10-20s to ~2s on maintenance turns.
            # Their world_state mutations are stored as patches and applied on next turn load.
            _mark_segment("maintenance_agents_deferred")

            _touch_and_cap_npc_states(
                world_state=world_state,
                present_npcs=[n for n in (state.get("present_npcs") or []) if isinstance(n, dict)],
                turn_number=next_turn_number,
            )
            # Phase 4.1: Sync NPC states to normalized table.
            try:
                from backend.app.core.npc_state_store import sync_from_world_state as _sync_npc
                _sync_npc(conn, campaign_id, world_state, next_turn_number)
            except Exception as _npc_sync_err:
                logger.warning("NPC state table sync failed (non-fatal): %s", _npc_sync_err)
            # Phase 4.2: Sync quest entries to normalized table.
            try:
                from backend.app.core.quest_store import sync_from_world_state as _sync_quests
                _sync_quests(conn, campaign_id, world_state, next_turn_number)
            except Exception as _quest_sync_err:
                logger.warning("Quest entry table sync failed (non-fatal): %s", _quest_sync_err)

            # V5.0: NPC persistent memory — authoritative (deterministic, not LLM).
            from backend.app.core.npc_memory import (  # noqa: E402
                ensure_npc_memory_table,
                extract_npc_memories_from_events,
                record_npc_interaction,
            )
            ensure_npc_memory_table(conn)
            npc_mems = extract_npc_memories_from_events(
                [{"event_type": ensure_event(e).event_type, "payload": ensure_event(e).payload or {}} for e in events],
                present_npcs=state.get("present_npcs"),
            )
            for mem in npc_mems:
                record_npc_interaction(
                    conn, campaign_id, mem["npc_name"], next_turn_number,
                    mem["event_type"], mem["summary"], mem.get("sentiment", 0),
                )

            # Phase 1-3: advance story-position timeline (year/chapter + divergence signals)
            try:
                base_world_time = int(camp.get("world_time_minutes") or 0) if isinstance(camp, dict) else 0
                pending_world_time = state.get("pending_world_time_minutes")
                if pending_world_time is not None:
                    effective_world_time = int(pending_world_time)
                else:
                    effective_world_time = base_world_time + int(mechanic_result.get("time_cost_minutes") or 0)
                world_state["story_position"] = advance_story_position(
                    story_position=world_state.get("story_position") if isinstance(world_state, dict) else None,
                    world_time_minutes=effective_world_time,
                    campaign_mode=str(world_state.get("campaign_mode") or "historical"),
                    event_types=[ensure_event(e).event_type for e in events],
                )
            except Exception as _story_pos_err:
                logger.warning("Story-position advance failed (non-fatal): %s", _story_pos_err)

            # V10.0 Feature 4: Append choice metadata for player behavioral profiling
            if intent != "META":
                from backend.app.constants import PLAYER_PROFILE_HISTORY_MAX
                _choice_history = world_state.setdefault("choice_history", [])
                _si = state.get("structured_intent") or {}
                _choice_history.append({
                    "turn": next_turn_number,
                    "tone": _si.get("tone_tag", "NEUTRAL") if _si else "NEUTRAL",
                    "action_type": _si.get("action_type", "TALK") if _si else "TALK",
                    "risk": _si.get("risk_level", "SAFE") if _si else "SAFE",
                    "is_free_text": not bool(_si),
                    "input_length": len(user_input or ""),
                    "creative_deviation": bool(state.get("creative_deviation", False)),
                })
                if len(_choice_history) > PLAYER_PROFILE_HISTORY_MAX:
                    _choice_history[:] = _choice_history[-PLAYER_PROFILE_HISTORY_MAX:]

            _ws_json_str = json.dumps(world_state)
            conn.execute(
                "UPDATE campaigns SET world_state_json = ? WHERE id = ?",
                (_ws_json_str, campaign_id),
            )
            # Phase 3.4: Store world_state snapshot for rewind capability.
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO turn_snapshots
                       (campaign_id, turn_number, world_state_json)
                       VALUES (?, ?, ?)""",
                    (campaign_id, next_turn_number, _ws_json_str),
                )
            except Exception as _snap_err:
                logger.warning("Snapshot write failed (non-fatal): %s", _snap_err)
            append_events(conn, campaign_id, next_turn_number, events, commit=False)
            apply_projection(conn, campaign_id, events, commit=False)
            for e in throttle_events:
                event = ensure_event(e)
                event_type = event.event_type
                payload = event.payload or {}
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
            _mark_segment("persist_events_projection_rendered_turn")
            # Episodic memory: store turn summary for long-term recall
            try:
                from backend.app.core.episodic_memory import EpisodicMemory  # noqa: E402
                epi = EpisodicMemory(conn, campaign_id)
                npcs_present = [
                    n.get("name", "") for n in (state.get("present_npcs") or [])
                    if n.get("name")
                ]
                key_events_for_mem = []
                for e in events:
                    event = ensure_event(e)
                    is_hidden = event.is_hidden if isinstance(e, Event) else (e.get("is_hidden", False) if isinstance(e, dict) else False)
                    if not is_hidden:
                        key_events_for_mem.append({
                            "event_type": event.event_type,
                            "payload": event.payload or {},
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
                crystallized = _derive_crystallized_memory(
                    turn_number=next_turn_number,
                    events=key_events_for_mem,
                    arc_stage=cur_arc,
                    hero_beat=cur_beat,
                    final_text=final_text or "",
                    location_id=state.get("current_location"),
                    npcs_present=npcs_present,
                )
                if crystallized:
                    epi.add_crystallized_memory(**crystallized)
                # V3.1: Track pivotal events for scale advisor density scoring
                from backend.app.core.episodic_memory import _is_pivotal  # noqa: E402
                if _is_pivotal(key_events_for_mem, cur_arc, prev_arc, stress_lvl):
                    piv_count = int(world_state.get("pivotal_event_count") or 0) + 1
                    world_state["pivotal_event_count"] = piv_count
            except Exception as _epi_err:
                logger.warning(
                    "Episodic memory store failed (non-fatal): %s", _epi_err
                )

            # Phase 4.2: Codex discovery — check if lore citations unlock codex entries
            try:
                from backend.app.core.codex_discovery import CodexDiscovery  # noqa: E402
                from backend.app.content.repository import CONTENT_REPOSITORY  # noqa: E402
                _era_id = (state.get("campaign") or {}).get("time_period") or world_state.get("era_id") or ""
                _era_id = str(_era_id).strip()
                _era_pack_for_codex = CONTENT_REPOSITORY.get_pack(_era_id) if _era_id else None
                if _era_pack_for_codex:
                    _lore_citations = state.get("lore_citations") or []
                    _codex_discovery = CodexDiscovery()
                    _newly_unlocked = _codex_discovery.check_unlocks(
                        world_state=world_state,
                        lore_citations=_lore_citations,
                        era_pack=_era_pack_for_codex,
                    )
                    if _newly_unlocked:
                        # Re-persist world_state with updated unlocked_codex_ids
                        conn.execute(
                            "UPDATE campaigns SET world_state_json = ? WHERE id = ?",
                            (json.dumps(world_state), campaign_id),
                        )
                        logger.info(
                            "Codex: %d entries unlocked this turn: %s",
                            len(_newly_unlocked), _newly_unlocked,
                        )
            except Exception as _codex_err:
                logger.debug("Codex discovery failed (non-fatal): %s", _codex_err)

            conn.commit()
            _mark_segment("episodic_codex_and_db_commit")
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

        # V7.0: Fire deferred maintenance agents AFTER commit (outside transaction).
        # These LLM agents (Memory, QuestWeaver, Progression, PsychArchivist) run in
        # a background thread and write their world_state patches for next-turn merge.
        if run_maintenance_agents and final_text and intent != "META":
            import copy as _copy
            from backend.app.core.deferred_agents import run_deferred_maintenance  # noqa: E402
            from backend.app.config import DEFAULT_DB_PATH as _db_path  # noqa: E402
            _events_snapshot = [
                {"event_type": ensure_event(e).event_type, "payload": ensure_event(e).payload or {}}
                for e in events
            ]
            _state_snapshot = {
                "final_text": final_text,
                "intent": intent,
                "present_npcs": state.get("present_npcs") or [],
                "recent_narrative": state.get("recent_narrative") or [],
                "player": state.get("player"),
                "current_location": state.get("current_location"),
            }
            run_deferred_maintenance(
                db_path=_db_path,
                campaign_id=campaign_id,
                player_id=player_id,
                turn_number=next_turn_number,
                world_state_snapshot=_copy.deepcopy(world_state),
                state_snapshot=_state_snapshot,
                events_snapshot=_events_snapshot,
                arc_guidance=arc_guidance if isinstance(arc_guidance, dict) else {},
            )
            _mark_segment("deferred_agents_launched")

        total_commit = round(time.perf_counter() - commit_started_at, 3)
        commit_segments["total"] = total_commit
        merged_agent_timings = dict(state.get("agent_timings") or {})
        merged_agent_timings["commit"] = {
            "turn_number": int(next_turn_number or 0),
            "maintenance_turn": bool(run_maintenance_agents),
            "segments": commit_segments,
        }
        state["agent_timings"] = merged_agent_timings

        refreshed = build_initial_gamestate(conn, campaign_id, player_id)
        refreshed_dict = refreshed.model_dump(mode="json")
        refreshed_dict["history"] = load_turn_history(conn, campaign_id, limit=10)
        refreshed_dict["final_text"] = final_text
        refreshed_dict["suggested_actions"] = suggested_actions
        refreshed_dict["embedded_suggestions"] = state.get("embedded_suggestions")
        refreshed_dict["lore_citations"] = state.get("lore_citations") or []
        refreshed_dict["context_stats"] = state.get("context_stats")
        refreshed_dict["agent_timings"] = state.get("agent_timings")
        refreshed_dict["llm_timings"] = state.get("llm_timings")
        refreshed_dict["warnings"] = state.get("warnings") or []

        # V5.0: Surface consequence_hints from ledger for player UI
        _refreshed_ws = refreshed_dict.get("campaign", {})
        if isinstance(_refreshed_ws, dict):
            _refreshed_wsj = _refreshed_ws.get("world_state_json") or {}
            if isinstance(_refreshed_wsj, str):
                import json as _json_ws
                try:
                    _refreshed_wsj = _json_ws.loads(_refreshed_wsj)
                except Exception:
                    _refreshed_wsj = {}
            _ledger = _refreshed_wsj.get("ledger") or {} if isinstance(_refreshed_wsj, dict) else {}
            _consequence_hints = _ledger.get("consequence_hints") or [] if isinstance(_ledger, dict) else []
            refreshed_dict["active_obligations"] = [str(h) for h in _consequence_hints[:5] if h]
        else:
            refreshed_dict["active_obligations"] = []

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
