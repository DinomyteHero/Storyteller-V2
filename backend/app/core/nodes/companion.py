"""Companion reaction node."""
from __future__ import annotations

import logging
from typing import Any

from backend.app.core.companion_reactions import (
    apply_alignment_and_faction,
    check_companion_triggers,
    compute_companion_reactions,
    compute_inter_party_tensions,
    format_companion_reactions_for_narrator,
    format_inter_party_tensions_for_director,
    format_inter_party_tensions_for_narrator,
    maybe_enqueue_banter,
    maybe_enqueue_news_banter,
    update_party_state,
)
from backend.app.core.warnings import add_warning
from backend.app.core.nodes import dict_to_state

logger = logging.getLogger(__name__)


def companion_reaction_node(state: dict[str, Any]) -> dict[str, Any]:
    """Pure node (no DB writes): compute affinity/loyalty/banter from mechanic_result."""
    try:
        mechanic_result = state.get("mechanic_result")
        if not mechanic_result:
            return state
        state = apply_alignment_and_faction(state, mechanic_result)
        campaign = state.get("campaign") or {}
        party = campaign.get("party") or []
        party_traits = campaign.get("party_traits") or {}
        turn_number = int(state.get("turn_number") or 0)
        if party:
            affinity_deltas, reasons = compute_companion_reactions(party, party_traits, mechanic_result)
            state = update_party_state(
                state, affinity_deltas,
                reasons=reasons,
                mechanic_result=mechanic_result if isinstance(mechanic_result, dict) else None,
                turn_number=turn_number,
            )
            # 1.2: Inject companion reactions summary for Narrator to weave into prose
            cr_summary = format_companion_reactions_for_narrator(state, affinity_deltas, reasons)
            # 3.2: Compute inter-companion tensions (opposing reactions to player's choice)
            tensions = compute_inter_party_tensions(party, party_traits, affinity_deltas)
            campaign = dict(state.get("campaign") or {})
            if cr_summary:
                campaign["companion_reactions_summary"] = cr_summary
            if tensions:
                campaign["inter_party_tensions_narrator"] = format_inter_party_tensions_for_narrator(tensions)
                campaign["inter_party_tensions_director"] = format_inter_party_tensions_for_director(tensions)
            state = {**state, "campaign": campaign}
            state, _banter_line = maybe_enqueue_banter(state, mechanic_result)
        # V2.20: Apply influence deltas from PartyState (meaning_tag + intent triggers)
        try:
            from backend.app.core.party_state import (
                load_party_state,
                apply_influence_delta,
                compute_influence_from_response,
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
                # Write back to world_state_json (will be persisted by commit)
                from backend.app.core.party_state import save_party_state
                ws = dict(ws)
                save_party_state(ws, ps)
                campaign["world_state_json"] = ws
                state = {**state, "campaign": campaign}
        except Exception:
            logger.debug("PartyState influence computation skipped", exc_info=True)

        state = maybe_enqueue_news_banter(state)
        # 2.2: Check for companion-initiated events (requests, quests, confrontations)
        companion_events = check_companion_triggers(state)
        if companion_events:
            pending = list(state.get("pending_companion_events") or [])
            pending.extend(companion_events)
            state = {**state, "pending_companion_events": pending}
        return state
    except Exception:
        logger.exception("companion_reaction_node failed; returning state unchanged")
        gs = dict_to_state(state)
        add_warning(gs, "Companion reactions failed — skipped for this turn.")
        return {**state, "warnings": gs.warnings}
