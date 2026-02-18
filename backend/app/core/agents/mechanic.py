"""MechanicAgent: routes action resolution through the LLM-based ResolutionAgent.

V4.0: Replaced deterministic d20 Python engine with ResolutionAgent — a Game Master LLM that
reads the Storyteller Core rule system and resolves actions contextually. No deterministic
fallbacks. All dice, DC, events, and consequence logic is LLM-driven.

Phase 4.4: Added _compute_item_modifiers() to apply EraItem.mechanics.difficulty_modifier
to the MechanicOutput.modifiers list based on the player's inventory and action type.

The MechanicAgent class is kept as the stable public interface so that the LangGraph node
(nodes/mechanic.py) and any callers remain unchanged.
"""
from __future__ import annotations

import logging
from typing import Any

from backend.app.models.state import (
    GameState,
    MechanicOutput,
    TONE_TAG_PARAGON,
    TONE_TAG_NEUTRAL,
)
from backend.app.time_economy import get_time_cost, DIALOGUE_ONLY_MINUTES
from backend.app.core.agents.resolution_agent import ResolutionAgent

logger = logging.getLogger(__name__)


# Action type → item tag mapping for modifier relevance
# If an EraItem has any of these tags, it applies to the given action type
_ACTION_ITEM_TAGS: dict[str, list[str]] = {
    "ATTACK": ["weapon", "offensive"],
    "STEALTH": ["covert", "stealth"],
    "TRAVEL": ["tool", "vehicle"],
    "INTERACT": ["tool", "document", "key"],
    "HEAL": ["consumable", "medical"],
}


def _compute_item_modifiers(
    inventory: list[dict[str, Any]],
    action_type: str,
    era_pack: Any | None = None,
) -> list[dict[str, Any]]:
    """Compute difficulty modifiers from equipped/carried items.

    Phase 4.4: Reads EraItem.mechanics.difficulty_modifier from the era pack
    and returns a list of modifier dicts to be appended to MechanicOutput.modifiers.

    Args:
        inventory: Player inventory list (dicts with 'item_id' or 'id' field).
        action_type: The resolved action type (ATTACK, STEALTH, etc.).
        era_pack: EraPack instance for item lookups. If None, returns empty list.

    Returns:
        List of {"source": str, "value": int} modifier dicts.
    """
    if not inventory or era_pack is None:
        return []

    relevant_tags = _ACTION_ITEM_TAGS.get(action_type.upper(), [])
    modifiers: list[dict[str, Any]] = []

    for inv_entry in inventory:
        if not isinstance(inv_entry, dict):
            continue
        item_id = inv_entry.get("item_id") or inv_entry.get("id") or ""
        if not item_id:
            continue

        # Look up item in era pack
        try:
            era_item = None
            items = getattr(era_pack, "items", []) or []
            for it in items:
                it_id = getattr(it, "id", None) if not isinstance(it, dict) else it.get("id")
                if it_id == item_id:
                    era_item = it
                    break
            if era_item is None:
                continue

            # Check item tags for relevance to this action type
            item_tags: list[str] = []
            if isinstance(era_item, dict):
                item_tags = list(era_item.get("tags") or [])
                item_mechanics = era_item.get("mechanics") or {}
                difficulty_mod = int(item_mechanics.get("difficulty_modifier", 0))
                item_name = era_item.get("name", item_id)
            else:
                item_tags = list(getattr(era_item, "tags", []) or [])
                mechanics = getattr(era_item, "mechanics", None)
                difficulty_mod = int(getattr(mechanics, "difficulty_modifier", 0)) if mechanics else 0
                item_name = getattr(era_item, "name", item_id)

            if difficulty_mod == 0:
                continue

            # Apply modifier if item is relevant to this action type
            tag_set = {t.lower() for t in item_tags}
            relevant_tag_set = {t.lower() for t in relevant_tags}
            if not relevant_tags or (tag_set & relevant_tag_set):
                modifiers.append({"source": item_name, "value": difficulty_mod})
                logger.debug(
                    "Item modifier: %s %+d to %s check",
                    item_name, difficulty_mod, action_type,
                )
        except Exception as _item_err:
            logger.debug("Item modifier lookup failed for %s (non-fatal): %s", item_id, _item_err)

    return modifiers


class MechanicAgent:
    """Resolves game mechanics from user input and state via LLM-based ResolutionAgent.

    V4.0: All resolution logic is delegated to ResolutionAgent (LLM Game Master).
    No deterministic fallbacks — if the LLM fails, the exception propagates.
    """

    def __init__(self, llm: object | None = None) -> None:
        self._resolver = ResolutionAgent()

    def resolve(self, state: GameState) -> MechanicOutput:
        """Resolve state into validated MechanicOutput via the LLM Game Master."""
        user_input = (state.user_input or "").strip()
        intent = state.intent

        # TALK intent: bypass LLM resolution — pure narrative, no mechanics needed
        if intent == "TALK":
            return MechanicOutput(
                action_type="TALK",
                time_cost_minutes=DIALOGUE_ONLY_MINUTES,
                events=[],
                outcome_summary="Dialogue (no mechanic).",
                tone_tag=TONE_TAG_PARAGON,
                alignment_delta={"light_dark": 1, "paragon_renegade": 1},
                faction_reputation_delta={},
                companion_affinity_delta={},
                companion_reaction_reason={},
                dice_result="Success",
                difficulty="Trivial",
            )

        # Empty input fast-path
        if not user_input:
            return MechanicOutput(
                action_type="IDLE",
                time_cost_minutes=0,
                events=[],
                narrative_facts=["No input provided."],
                outcome_summary="No input.",
                tone_tag=TONE_TAG_NEUTRAL,
                invalid_action=True,
                dice_result="Failure",
                difficulty="Trivial",
            )

        # All other intents: delegate to LLM ResolutionAgent
        result = self._resolver.resolve(state)

        # Phase 4.4: Apply item difficulty modifiers from player inventory
        try:
            from backend.app.content.repository import CONTENT_REPOSITORY
            campaign = getattr(state, "campaign", None) or {}
            if isinstance(campaign, dict):
                ws = campaign.get("world_state_json") or {}
                era_id = (campaign.get("time_period") or ws.get("era_id") or "").strip()
                era_pack = CONTENT_REPOSITORY.get_pack(era_id) if era_id else None
            else:
                era_pack = None

            if era_pack:
                inventory = list(getattr(state, "inventory", []) or [])
                item_mods = _compute_item_modifiers(inventory, result.action_type, era_pack)
                if item_mods:
                    result.modifiers = list(result.modifiers or []) + item_mods
        except Exception as _item_mod_err:
            logger.debug("Item modifier application failed (non-fatal): %s", _item_mod_err)

        return result
