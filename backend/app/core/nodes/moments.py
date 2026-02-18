"""Moments node for the LangGraph pipeline (Phase 4.3).

Checks ``EraMoment`` triggers after companion_reaction and before arc_planner.
When a moment fires, its ``narrative_beat`` is injected into ``arc_guidance``
as additional Director instructions, and the moment ID is added to
``world_state["fired_moments"]`` (once_only enforcement).

Trigger conditions checked:
- companion_id + affinity_threshold: companion affinity >= threshold
- arc_stage: current arc stage matches
- turn_number_min: current turn >= minimum
- location_tags_any: current location has any of these tags
- quest_id_completed: quest is in the completed quests list

Pipeline position: companion_reaction → moments → arc_planner
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def moments_node(state: dict[str, Any]) -> dict[str, Any]:
    """Check and fire EraMoment triggers for the current turn.

    Reads the era pack's moments list, checks each trigger against current
    world state, and injects fired moments into arc_guidance for the Director.

    Returns:
        Updated state with arc_guidance.fired_moments_beats and
        world_state fired_moments list updated.
    """
    try:
        return _moments_node_impl(state)
    except Exception as e:
        logger.warning("Moments node failed (non-fatal): %s", e, exc_info=True)
        return state


def _moments_node_impl(state: dict[str, Any]) -> dict[str, Any]:
    campaign = (state.get("campaign") or {})
    if not isinstance(campaign, dict):
        return state

    ws = campaign.get("world_state_json")
    if not isinstance(ws, dict):
        return state

    # Load era pack
    era_id = (campaign.get("time_period") or ws.get("era_id") or "").strip()
    if not era_id:
        return state

    try:
        from backend.app.content.repository import CONTENT_REPOSITORY
        era_pack = CONTENT_REPOSITORY.get_pack(era_id)
    except Exception as _e:
        logger.debug("Moments node: could not load era pack %s: %s", era_id, _e)
        return state

    if era_pack is None:
        return state

    moments = getattr(era_pack, "moments", []) or []
    if not moments:
        return state

    # Current state
    fired_moments: set[str] = set(ws.get("fired_moments") or [])
    arc_guidance: dict[str, Any] = dict(state.get("arc_guidance") or {})
    turn_number = int(ws.get("turn_number") or state.get("turn_number") or 0)
    arc_stage = arc_guidance.get("arc_stage") or (ws.get("arc_state") or {}).get("current_stage") or "SETUP"
    current_location_id = ws.get("current_location") or ""

    # Get current location tags
    current_location_tags: list[str] = []
    try:
        loc = era_pack.location_by_id(current_location_id)
        if loc:
            current_location_tags = [t.lower() for t in (loc.tags or [])]
    except Exception:
        pass

    # Get companion affinities
    party_state = ws.get("party_state") or {}
    companion_states = party_state.get("companion_states") if isinstance(party_state, dict) else {}
    if not isinstance(companion_states, dict):
        companion_states = {}

    # Get completed quests
    completed_quests: set[str] = set(ws.get("completed_quests") or [])

    # Get alignment values
    alignment: dict[str, int] = {}
    try:
        player_data = state.get("player") or {}
        if isinstance(player_data, dict):
            alignment = dict(player_data.get("alignment") or {})
        elif hasattr(player_data, "alignment"):
            alignment = dict(getattr(player_data, "alignment") or {})
    except Exception:
        pass

    newly_fired: list[str] = []
    fired_beats: list[str] = []

    for moment in moments:
        moment_id = getattr(moment, "id", None)
        if not moment_id:
            continue

        # Once-only check
        once_only = getattr(moment, "once_only", True)
        if once_only and moment_id in fired_moments:
            continue

        trigger = getattr(moment, "trigger", None)
        if trigger is None:
            continue

        # Evaluate trigger conditions — all specified conditions must pass
        if not _check_trigger(
            trigger=trigger,
            arc_stage=arc_stage,
            turn_number=turn_number,
            current_location_tags=current_location_tags,
            companion_states=companion_states,
            completed_quests=completed_quests,
            alignment=alignment,
        ):
            continue

        # Moment fires!
        newly_fired.append(moment_id)
        narrative_beat = getattr(moment, "narrative_beat", "") or ""
        if narrative_beat:
            fired_beats.append(narrative_beat)

        logger.info("Moment fired: %s (%s)", moment_id, getattr(moment, "title", ""))

    if newly_fired:
        # Update world state with fired moments
        updated_fired = list(fired_moments) + newly_fired
        ws["fired_moments"] = updated_fired
        # Mutate campaign world_state reference in state
        if isinstance(state.get("campaign"), dict):
            state["campaign"]["world_state_json"] = ws

        # Inject beats into arc_guidance for Director
        if fired_beats:
            existing_beats = arc_guidance.get("fired_moments_beats") or []
            arc_guidance["fired_moments_beats"] = list(existing_beats) + fired_beats
            # Also prepend to scene_instructions if present
            scene_instr = arc_guidance.get("scene_instructions") or ""
            beats_text = "\n".join(f"[MOMENT] {b}" for b in fired_beats)
            arc_guidance["scene_instructions"] = (
                (beats_text + "\n\n" + scene_instr) if scene_instr else beats_text
            )

        return {**state, "arc_guidance": arc_guidance}

    return state


def _check_trigger(
    trigger: Any,
    arc_stage: str,
    turn_number: int,
    current_location_tags: list[str],
    companion_states: dict[str, Any],
    completed_quests: set[str],
    alignment: dict[str, int],
) -> bool:
    """Return True if ALL specified trigger conditions are satisfied."""
    # arc_stage condition
    req_stage = getattr(trigger, "arc_stage", None) or (trigger.get("arc_stage") if isinstance(trigger, dict) else None)
    if req_stage and req_stage.upper() != arc_stage.upper():
        return False

    # turn_number_min condition
    turn_min = getattr(trigger, "turn_number_min", None) if not isinstance(trigger, dict) else trigger.get("turn_number_min")
    if turn_min is not None and turn_number < int(turn_min):
        return False

    # location_tags_any condition
    loc_tags_req = list(getattr(trigger, "location_tags_any", []) or []) if not isinstance(trigger, dict) else list(trigger.get("location_tags_any") or [])
    if loc_tags_req:
        req_lower = {t.lower() for t in loc_tags_req}
        if not (req_lower & set(current_location_tags)):
            return False

    # companion_id + affinity_threshold condition
    comp_id = getattr(trigger, "companion_id", None) if not isinstance(trigger, dict) else trigger.get("companion_id")
    affinity_thresh = getattr(trigger, "affinity_threshold", None) if not isinstance(trigger, dict) else trigger.get("affinity_threshold")
    if comp_id:
        comp_state = companion_states.get(comp_id) or {}
        if isinstance(comp_state, dict):
            current_affinity = int(comp_state.get("affinity", comp_state.get("affinity_score", 0)) or 0)
        else:
            current_affinity = 0
        if affinity_thresh is not None and current_affinity < int(affinity_thresh):
            return False

    # quest_id_completed condition
    quest_req = getattr(trigger, "quest_id_completed", None) if not isinstance(trigger, dict) else trigger.get("quest_id_completed")
    if quest_req and quest_req not in completed_quests:
        return False

    # alignment_min condition
    align_min = dict(getattr(trigger, "alignment_min", {}) or {}) if not isinstance(trigger, dict) else dict(trigger.get("alignment_min") or {})
    for align_key, min_val in align_min.items():
        if int(alignment.get(align_key, 0)) < int(min_val):
            return False

    return True
