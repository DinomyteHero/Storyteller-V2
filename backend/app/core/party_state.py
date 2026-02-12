"""Persistent party state with per-companion runtime data and influence system.

PartyState lives in world_state_json["party_state"] and is loaded/saved by
the commit node. It is the single source of truth for who is in the party
and what their relationship status is.

Backward-compatible: if party_state is absent in world_state_json, one is
built from the legacy party/party_affinity/party_traits fields.
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class CompanionRuntimeState(BaseModel):
    """Per-companion runtime data (persisted in world_state_json)."""
    companion_id: str
    influence: int = 0        # -100..100
    trust: int = 0            # optional axis: -100..100
    respect: int = 0          # optional axis: -100..100
    fear: int = 0             # optional axis: -100..100
    loyalty_progress: int = 0  # 0..100
    traits: dict[str, int] = Field(default_factory=dict)
    memories: list[str] = Field(default_factory=list)  # max 10
    triggers_fired: list[str] = Field(default_factory=list)
    banter_last_turn: int = 0  # last turn this companion bantered


class PartyState(BaseModel):
    """Persistent party state (stored in world_state_json["party_state"])."""
    active_companions: list[str] = Field(default_factory=list)  # ordered list of companion ids
    companion_states: dict[str, CompanionRuntimeState] = Field(default_factory=dict)

    def has_companion(self, comp_id: str) -> bool:
        return comp_id in self.active_companions

    def get_companion_state(self, comp_id: str) -> CompanionRuntimeState | None:
        return self.companion_states.get(comp_id)

    def companion_affordances(self) -> tuple[list[str], list[str]]:
        """Return (enables, blocks) aggregated from all active companions."""
        from backend.app.core.companions import get_companion_by_id

        enables: list[str] = []
        blocks: list[str] = []
        for cid in self.active_companions:
            # Check era-pack companion first
            comp_data = get_companion_by_id(cid)
            if comp_data:
                enables.extend(comp_data.get("enables_affordances") or [])
                blocks.extend(comp_data.get("blocks_affordances") or [])
        return enables, blocks


def _clamp(value: int, lo: int = -100, hi: int = 100) -> int:
    return max(lo, min(hi, value))


def add_companion_to_party(
    party_state: PartyState,
    comp_id: str,
    initial_influence: int = 0,
    traits: dict[str, int] | None = None,
) -> bool:
    """Add a companion. Returns True if newly added, False if already present."""
    if comp_id in party_state.active_companions:
        return False
    party_state.active_companions.append(comp_id)
    party_state.companion_states[comp_id] = CompanionRuntimeState(
        companion_id=comp_id,
        influence=_clamp(initial_influence),
        traits=dict(traits or {}),
    )
    return True


def remove_companion_from_party(party_state: PartyState, comp_id: str) -> bool:
    """Remove a companion. Returns True if removed, False if not found."""
    if comp_id not in party_state.active_companions:
        return False
    party_state.active_companions.remove(comp_id)
    party_state.companion_states.pop(comp_id, None)
    return True


def apply_influence_delta(
    party_state: PartyState,
    comp_id: str,
    delta: int,
    reason: str = "",
    *,
    trust_delta: int = 0,
    respect_delta: int = 0,
    fear_delta: int = 0,
) -> int:
    """Apply an influence delta to a companion. Returns the new influence value.

    Also applies optional trust/respect/fear axis deltas.
    """
    cs = party_state.companion_states.get(comp_id)
    if not cs:
        return 0
    cs.influence = _clamp(cs.influence + delta)
    if trust_delta:
        cs.trust = _clamp(cs.trust + trust_delta)
    if respect_delta:
        cs.respect = _clamp(cs.respect + respect_delta)
    if fear_delta:
        cs.fear = _clamp(cs.fear + fear_delta)
    # Record significant moments
    if abs(delta) >= 2 and reason:
        cs.memories.append(reason[:200])
        if len(cs.memories) > 10:
            cs.memories = cs.memories[-10:]
    return cs.influence


def load_party_state(world_state: dict[str, Any]) -> PartyState:
    """Load PartyState from world_state_json, with backward-compat migration."""
    raw = world_state.get("party_state")
    if raw and isinstance(raw, dict):
        try:
            return PartyState.model_validate(raw)
        except Exception:
            logger.warning("Failed to parse party_state; rebuilding from legacy fields")

    # Backward-compat: build from legacy party/party_affinity/party_traits
    party = world_state.get("party") or []
    party_affinity = world_state.get("party_affinity") or {}
    party_traits = world_state.get("party_traits") or {}
    loyalty_progress = world_state.get("loyalty_progress") or {}

    companion_states: dict[str, CompanionRuntimeState] = {}
    for cid in party:
        companion_states[cid] = CompanionRuntimeState(
            companion_id=cid,
            influence=int(party_affinity.get(cid, 0)),
            traits=dict(party_traits.get(cid) or {}),
            loyalty_progress=int(loyalty_progress.get(cid, 0)),
            memories=list((world_state.get("companion_memories") or {}).get(cid) or []),
        )
    return PartyState(active_companions=list(party), companion_states=companion_states)


def save_party_state(world_state: dict[str, Any], party_state: PartyState) -> dict[str, Any]:
    """Persist PartyState into world_state_json. Also writes legacy fields for backward compat."""
    world_state["party_state"] = party_state.model_dump(mode="json")
    # Write legacy fields so existing code (companion_reactions, commit) still works
    world_state["party"] = list(party_state.active_companions)
    world_state["party_affinity"] = {
        cid: cs.influence for cid, cs in party_state.companion_states.items()
    }
    world_state["party_traits"] = {
        cid: dict(cs.traits) for cid, cs in party_state.companion_states.items()
    }
    world_state["loyalty_progress"] = {
        cid: cs.loyalty_progress for cid, cs in party_state.companion_states.items()
    }
    return world_state


def compute_available_affordances(
    location_services: list[str],
    party_state: PartyState,
) -> list[str]:
    """Merge location services with companion-enabled affordances, minus blocked ones.

    Returns a deduplicated list of available affordance tokens.
    """
    enables, blocks = party_state.companion_affordances()
    block_set = set(blocks)
    available = set(location_services)
    available.update(enables)
    available -= block_set
    return sorted(available)


def compute_influence_from_response(
    party_state: PartyState,
    intent: str,
    meaning_tag: str,
    tone_tag: str,
) -> dict[str, tuple[int, str]]:
    """Compute per-companion influence deltas from a player response.

    Returns {companion_id: (delta, reason)}.
    Uses companion traits + era-pack influence triggers if available.
    """
    from backend.app.core.companions import get_companion_by_id

    results: dict[str, tuple[int, str]] = {}
    for cid in party_state.active_companions:
        cs = party_state.companion_states.get(cid)
        if not cs:
            continue
        comp_data = get_companion_by_id(cid)
        delta = 0
        reason = ""

        # Check era-pack influence triggers first
        if comp_data:
            triggers = (comp_data.get("influence") or {}).get("triggers") or []
            if isinstance(triggers, list):
                for trigger in triggers:
                    if not isinstance(trigger, dict):
                        continue
                    if trigger.get("intent") and trigger["intent"] == intent:
                        delta += int(trigger.get("delta", 0))
                        reason = f"{intent} trigger"
                    if trigger.get("meaning_tag") and trigger["meaning_tag"] == meaning_tag:
                        delta += int(trigger.get("delta", 0))
                        reason = f"{meaning_tag} trigger"

        # Trait-based reaction (small nudge from tone alignment)
        if not delta and cs.traits:
            from backend.app.core.companion_reactions import _tone_match_score, _score_to_affinity_delta
            score = _tone_match_score(tone_tag, cs.traits)
            trait_delta = _score_to_affinity_delta(score)
            if trait_delta:
                delta = trait_delta
                reason = f"{tone_tag.lower()} choice"

        # Clamp individual delta to [-5, 5]
        delta = max(-5, min(5, delta))
        if delta:
            results[cid] = (delta, reason)
    return results
