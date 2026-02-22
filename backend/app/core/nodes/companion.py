"""Companion reaction node — V5.0: Authoritative LLM-driven companion system.

Replaces deterministic compute_companion_reactions() and cosmetic CompanionVoiceAgent
with a single authoritative CompanionSystemAgent that determines BOTH affinity deltas
AND spoken reactions in one LLM call.

No deterministic fallback for companion reactions. If the LLM fails, the node raises.
"""
from __future__ import annotations

import json as _json
import logging
from typing import Any

from backend.app.core.companion_reactions import (
    apply_alignment_and_faction,
    check_companion_triggers,
    format_companion_reactions_for_narrator,
    format_inter_party_tensions_for_narrator,
    format_inter_party_tensions_for_director,
    maybe_enqueue_news_banter,
    update_party_state,
)
from backend.app.core.warnings import add_warning
from backend.app.core.nodes import dict_to_state

logger = logging.getLogger(__name__)


def companion_reaction_node(state: dict[str, Any]) -> dict[str, Any]:
    """Authoritative node: LLM-driven companion reactions (affinity + voice + emotions)."""
    mechanic_result = state.get("mechanic_result")
    if not mechanic_result:
        return state

    state = apply_alignment_and_faction(state, mechanic_result)
    campaign = state.get("campaign") or {}
    party = campaign.get("party") or []
    party_traits = campaign.get("party_traits") or {}
    turn_number = int(state.get("turn_number") or 0)

    if not party:
        return state

    # V5.0: Use CompanionSystemAgent for authoritative reactions
    from backend.app.core.agents.companion_system_agent import generate_companion_reactions
    from backend.app.world.companion_bible import get_companion_by_id

    # V12.0: Unified cloud resolution for CompanionSystem
    gs = dict_to_state(state)
    _comp_llm = None
    try:
        from backend.app.core.nodes._cloud_helper import make_turn_llm
        _conn = state.get("__runtime_conn")
        _comp_llm = make_turn_llm("companion_system", gs, _conn)
    except Exception as _comp_e:
        logger.debug("Cloud companion_system init skipped: %s", _comp_e)

    affinity_map = campaign.get("party_affinity") or {}
    recent_narrative = state.get("final_text") or ""

    reactions = generate_companion_reactions(
        party=party,
        party_traits=party_traits,
        affinity_map=affinity_map,
        mechanic_result=mechanic_result,
        companion_getter=get_companion_by_id,
        recent_narrative=recent_narrative,
        llm=_comp_llm,
    )

    # Extract affinity deltas and reasons from LLM reactions
    affinity_deltas: dict[str, int] = {}
    reasons: dict[str, str] = {}
    spoken_reactions: dict[str, str] = {}
    tensions: list[dict[str, Any]] = []
    banter_lines: list[str] = []

    for r in reactions:
        cid = r["companion_id"]
        affinity_deltas[cid] = r["affinity_delta"]
        reasons[cid] = r.get("spoken_reaction") or ""
        if r.get("spoken_reaction"):
            spoken_reactions[cid] = r["spoken_reaction"]
        if r.get("tension_with"):
            tensions.append({
                "companion_a": cid,
                "companion_b": r["tension_with"],
                "emotional_state": r.get("emotional_state", "conflicted"),
            })
        if r.get("banter_line"):
            banter_lines.append(r["banter_line"])

    # Apply affinity deltas using existing state mutation utility
    state = update_party_state(
        state, affinity_deltas,
        reasons=reasons,
        mechanic_result=mechanic_result if isinstance(mechanic_result, dict) else None,
        turn_number=turn_number,
    )

    # Inject companion reactions summary for Narrator
    cr_summary = format_companion_reactions_for_narrator(state, affinity_deltas, reasons)
    campaign = dict(state.get("campaign") or {})
    if cr_summary:
        campaign["companion_reactions_summary"] = cr_summary
    if tensions:
        tension_narrator = format_inter_party_tensions_for_narrator(tensions)
        tension_director = format_inter_party_tensions_for_director(tensions)
        if tension_narrator:
            campaign["inter_party_tensions_narrator"] = tension_narrator
        if tension_director:
            campaign["inter_party_tensions_director"] = tension_director

    # Store spoken reactions in world_state_json
    ws = campaign.get("world_state_json") or {}
    if isinstance(ws, str):
        try:
            ws = _json.loads(ws)
        except Exception:
            ws = {}
    ws = dict(ws)
    if spoken_reactions:
        ws["companion_spoken_reactions"] = spoken_reactions
    if banter_lines:
        bq = list(ws.get("banter_queue") or [])
        bq.extend(banter_lines)
        ws["banter_queue"] = bq[-5:]  # Keep last 5
    campaign["world_state_json"] = ws
    state = {**state, "campaign": campaign}

    # V2.20: Apply influence deltas from PartyState
    try:
        from backend.app.core.party_state import (
            load_party_state,
            apply_influence_delta,
            compute_influence_from_response,
            save_party_state,
        )
        campaign = dict(state.get("campaign") or {})
        ws = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
        if isinstance(ws, dict):
            ps = load_party_state(ws)
            mr = mechanic_result if isinstance(mechanic_result, dict) else (
                mechanic_result.model_dump(mode="json") if hasattr(mechanic_result, "model_dump") else {}
            )
            intent = (mr.get("action_type") or "").lower()
            tone = (mr.get("tone_tag") or "NEUTRAL").upper()
            meaning = (mr.get("meaning_tag") or state.get("user_input_meaning_tag") or "")
            influence_deltas = compute_influence_from_response(ps, intent, meaning, tone)
            for cid, (delta, reason) in influence_deltas.items():
                apply_influence_delta(ps, cid, delta, reason)
            ws = dict(ws)
            save_party_state(ws, ps)
            campaign["world_state_json"] = ws
            state = {**state, "campaign": campaign}
    except Exception:
        logger.debug("PartyState influence computation skipped", exc_info=True)

    state = maybe_enqueue_news_banter(state)

    # Phase 6.2: Companion loyalty stakes — check influence thresholds and set flags
    try:
        from backend.app.constants import (
            COMPANION_LOYALTY_RELUCTANT,
            COMPANION_LOYALTY_THREATENS_LEAVE,
            COMPANION_LOYALTY_LEAVES,
        )
        from backend.app.core.party_state import load_party_state as _load_ps
        from backend.app.core.party_state import remove_companion_from_party, save_party_state as _save_ps

        campaign_loyalty = dict(state.get("campaign") or {})
        ws_loyalty = campaign_loyalty.get("world_state_json") or {}
        if isinstance(ws_loyalty, str):
            try:
                ws_loyalty = _json.loads(ws_loyalty)
            except Exception:
                ws_loyalty = {}
        if isinstance(ws_loyalty, dict):
            ps_loyalty = _load_ps(ws_loyalty)
            loyalty_warnings: list[str] = []
            companion_left_events: list[dict[str, Any]] = []

            for cid in list(ps_loyalty.active_companions):
                cs = ps_loyalty.companion_states.get(cid)
                if not cs:
                    continue
                influence = cs.influence

                if influence <= COMPANION_LOYALTY_LEAVES:
                    # Companion actually leaves the party
                    companion_name = cid  # default to id
                    try:
                        from backend.app.core.companions import get_companion_by_id as _get_comp
                        comp_data = _get_comp(cid)
                        if comp_data:
                            companion_name = comp_data.get("name", cid)
                    except Exception:
                        pass
                    loyalty_warnings.append(
                        f"CRITICAL DRAMATIC MOMENT: {companion_name} is leaving forever. "
                        f"This must be the emotional centerpiece of this turn. "
                        f"Show their final words, the weight of what's lost, and the silence after."
                    )
                    companion_left_events.append({
                        "event_type": "companion_left",
                        "companion_id": cid,
                        "companion_name": companion_name,
                        "influence": influence,
                    })
                    remove_companion_from_party(ps_loyalty, cid)
                    # V1.1: Track departed companions (potential future NPCs)
                    departed = list(ws_loyalty.get("departed_companions") or [])
                    departed.append({
                        "companion_id": cid,
                        "name": companion_name,
                        "influence_at_departure": influence,
                        "departure_turn": state.get("turn_number", 0),
                        "disposition": "hostile" if influence < -60 else "bitter",
                    })
                    ws_loyalty["departed_companions"] = departed
                    logger.info("Phase 6.2: Companion %s left the party (influence=%d)", cid, influence)

                elif influence <= COMPANION_LOYALTY_THREATENS_LEAVE:
                    companion_name = cid
                    try:
                        from backend.app.core.companions import get_companion_by_id as _get_comp
                        comp_data = _get_comp(cid)
                        if comp_data:
                            companion_name = comp_data.get("name", cid)
                    except Exception:
                        pass
                    loyalty_warnings.append(
                        f"WARNING: {companion_name} threatens to leave (influence={influence}). "
                        f"Show them voicing doubt, packing belongings, or confronting the player."
                    )
                    logger.info("Phase 6.2: Companion %s threatens to leave (influence=%d)", cid, influence)

                elif influence <= COMPANION_LOYALTY_RELUCTANT:
                    companion_name = cid
                    try:
                        from backend.app.core.companions import get_companion_by_id as _get_comp
                        comp_data = _get_comp(cid)
                        if comp_data:
                            companion_name = comp_data.get("name", cid)
                    except Exception:
                        pass
                    loyalty_warnings.append(
                        f"NOTICE: {companion_name} is reluctant (influence={influence}). "
                        f"They won't help with risky plans and may drag their feet."
                    )

            # Persist updated party state if any companion left
            if companion_left_events:
                ws_loyalty = dict(ws_loyalty)
                _save_ps(ws_loyalty, ps_loyalty)
                campaign_loyalty["world_state_json"] = ws_loyalty
                # Update legacy party list
                campaign_loyalty["party"] = list(ps_loyalty.active_companions)
                state = {**state, "campaign": campaign_loyalty}
                # V1.1: Record companion departures in decision_ledger
                try:
                    _conn = state.get("__runtime_conn")
                    _cid = state.get("campaign_id") or (campaign_loyalty.get("id") or "")
                    if _conn and _cid:
                        from backend.app.core.decision_ledger import record_decision as _rec_dec
                        for _evt in companion_left_events:
                            _rec_dec(
                                conn=_conn,
                                campaign_id=_cid,
                                turn_number=state.get("turn_number", 0),
                                chosen_text=f"{_evt['companion_name']} left the party permanently",
                                chosen_tone="NEUTRAL",
                                rejected_options=[],
                                consequence_hint=f"{_evt['companion_name']} may return as an NPC — hostile or regretful.",
                                impact_tier="wave",
                                context_summary="Companion departed due to low influence",
                                tags=["companion_departure", "permanent_loss"],
                            )
                except Exception as _dl_dep:
                    logger.debug("Decision ledger companion departure record failed: %s", _dl_dep)

            # Set loyalty flags in state for narrator and choice crafter
            if loyalty_warnings:
                state = {**state, "companion_loyalty_warnings": loyalty_warnings}
            if companion_left_events:
                pending = list(state.get("pending_companion_events") or [])
                pending.extend(companion_left_events)
                state = {**state, "pending_companion_events": pending}

            # Set companion_threatens_leave flag for choice crafter hint
            threatens_leave_names = []
            for cid in ps_loyalty.active_companions:
                cs = ps_loyalty.companion_states.get(cid)
                if cs and cs.influence <= COMPANION_LOYALTY_THREATENS_LEAVE:
                    companion_name = cid
                    try:
                        from backend.app.core.companions import get_companion_by_id as _get_comp
                        comp_data = _get_comp(cid)
                        if comp_data:
                            companion_name = comp_data.get("name", cid)
                    except Exception:
                        pass
                    threatens_leave_names.append(companion_name)
            if threatens_leave_names:
                state = {**state, "companion_threatens_leave": threatens_leave_names}

    except Exception:
        logger.debug("Phase 6.2: Loyalty stake check skipped", exc_info=True)

    # ── V10.0 Feature 6: Companion wound/reveal layer tracking ─────────
    try:
        campaign_rev = dict(state.get("campaign") or {})
        ws_rev = campaign_rev.get("world_state_json") or {}
        if isinstance(ws_rev, str):
            try:
                ws_rev = _json.loads(ws_rev)
            except Exception:
                ws_rev = {}
        if isinstance(ws_rev, dict):
            ws_rev = dict(ws_rev)
            _comp_revelations = dict(ws_rev.get("companion_revelations") or {})
            _aff_map = campaign_rev.get("party_affinity") or {}
            _rev_changed = False
            for cid in (campaign_rev.get("party") or []):
                current_aff = int(_aff_map.get(cid, 0))
                # Look up companion definition for revelation_stages
                try:
                    from backend.app.core.companions import get_companion_by_id as _get_comp_rev
                    _comp_def = _get_comp_rev(cid)
                except Exception:
                    _comp_def = None
                if not _comp_def or not _comp_def.get("revelation_stages"):
                    continue
                _stages = _comp_def["revelation_stages"]
                _current_rev = _comp_revelations.get(cid) or {}
                _current_stage = _current_rev.get("stage", "")
                _stage_order = ("surface", "deep", "core")
                _current_idx = _stage_order.index(_current_stage) if _current_stage in _stage_order else -1
                for _rs in _stages:
                    if not isinstance(_rs, dict):
                        continue
                    _threshold = int(_rs.get("affinity_threshold", 999))
                    _rs_stage = _rs.get("stage", "")
                    _rs_idx = _stage_order.index(_rs_stage) if _rs_stage in _stage_order else -1
                    if _rs_idx > _current_idx and current_aff >= _threshold:
                        _comp_revelations[cid] = {
                            "stage": _rs_stage,
                            "turn": turn_number,
                            "trigger_text": _rs.get("trigger", ""),
                            "revealed_this_turn": True,
                        }
                        _rev_changed = True
                        _comp_name = _comp_def.get("name", cid)
                        logger.info(
                            "V10.0: Companion %s wound revelation — stage '%s' unlocked at affinity %d",
                            _comp_name, _rs_stage, current_aff,
                        )
                        # V1.1: Generate COMPANION_REVELATION event + revelation_queue entry
                        _rev_event = {
                            "event_type": "COMPANION_REVELATION",
                            "companion_id": cid,
                            "revelation_stage": _rs_stage,
                            "trigger_text": _rs.get("trigger", ""),
                            "description": f"{_comp_name}'s guard drops — {_rs_stage} wound revealed.",
                        }
                        pending_rev = list(state.get("pending_companion_events") or [])
                        pending_rev.append(_rev_event)
                        state = {**state, "pending_companion_events": pending_rev}
                        # Inject into revelation_queue for Director to surface dramatically
                        from backend.app.constants import DEEP_COMPANION_REVELATION_DRAMATIC_VALUE
                        _rev_queue = list(ws_rev.get("revelation_queue") or [])
                        _rev_queue.append({
                            "id": f"rev-companion-{cid}-{_rs_stage}",
                            "content": _rs.get("trigger", f"{_comp_name} reveals something."),
                            "source": "companion_wound",
                            "source_npc": _comp_name,
                            "dramatic_value": DEEP_COMPANION_REVELATION_DRAMATIC_VALUE,
                            "optimal_conditions": ["quiet_moment", "after_combat", "campfire"],
                            "turn_queued": turn_number,
                            "revealed": False,
                        })
                        ws_rev["revelation_queue"] = _rev_queue
                        # Only advance one stage per turn
                        break
            if _rev_changed:
                ws_rev["companion_revelations"] = _comp_revelations
                campaign_rev["world_state_json"] = ws_rev
                state = {**state, "campaign": campaign_rev}
    except Exception:
        logger.debug("V10.0: Companion revelation check skipped", exc_info=True)

    # Clear revealed_this_turn flags from previous turns
    try:
        _cr = dict(state.get("campaign") or {})
        _cr_ws = _cr.get("world_state_json") or {}
        if isinstance(_cr_ws, dict):
            _cr_revs = _cr_ws.get("companion_revelations") or {}
            for _cid, _crev in _cr_revs.items():
                if isinstance(_crev, dict) and _crev.get("revealed_this_turn") and _crev.get("turn", 0) != turn_number:
                    _crev["revealed_this_turn"] = False
    except Exception:
        pass

    # Check for companion-initiated events
    companion_events = check_companion_triggers(state)
    if companion_events:
        pending = list(state.get("pending_companion_events") or [])
        pending.extend(companion_events)
        state = {**state, "pending_companion_events": pending}

    return state
