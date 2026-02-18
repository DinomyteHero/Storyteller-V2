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

    affinity_map = campaign.get("party_affinity") or {}
    recent_narrative = state.get("final_text") or ""

    reactions = generate_companion_reactions(
        party=party,
        party_traits=party_traits,
        affinity_map=affinity_map,
        mechanic_result=mechanic_result,
        companion_getter=get_companion_by_id,
        recent_narrative=recent_narrative,
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

    # Check for companion-initiated events
    companion_events = check_companion_triggers(state)
    if companion_events:
        pending = list(state.get("pending_companion_events") or [])
        pending.extend(companion_events)
        state = {**state, "pending_companion_events": pending}

    return state
