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
import re
from typing import Any

from backend.app.constants import SANDBOX_ARC_STAGE_ORDER, SANDBOX_IMPACT_TIERS, WOUNDED_DC_PENALTY
from backend.app.models.state import (
    ActionSuggestion,
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


def _world_state_from_campaign(campaign: Any) -> dict[str, Any]:
    if not isinstance(campaign, dict):
        return {}
    ws = campaign.get("world_state_json") or {}
    return ws if isinstance(ws, dict) else {}


def _campaign_mode(state: GameState) -> str:
    ws = _world_state_from_campaign(state.campaign)
    return str(ws.get("campaign_mode") or "historical").strip().lower()


def _arc_stage(state: GameState) -> str:
    ws = _world_state_from_campaign(state.campaign)
    arc_state = ws.get("arc_state") if isinstance(ws, dict) else {}
    if isinstance(arc_state, dict):
        stage = str(arc_state.get("current_stage") or "").strip().upper()
        if stage:
            return stage
    arc_guidance = state.arc_guidance or {}
    if isinstance(arc_guidance, dict):
        stage = str(arc_guidance.get("arc_stage") or "").strip().upper()
        if stage:
            return stage
        nested = arc_guidance.get("arc_state")
        if isinstance(nested, dict):
            stage = str(nested.get("current_stage") or "").strip().upper()
            if stage:
                return stage
    return "SETUP"


def _impact_from_text(user_input: str) -> str:
    text = (user_input or "").lower()
    if re.search(r"\[(tsunami)\]", text):
        return "tsunami"
    if re.search(r"\[(wave)\]", text):
        return "wave"
    if re.search(r"\[(ripple)\]", text):
        return "ripple"
    tsunami_markers = (
        "destroy planet",
        "wipe out",
        "galaxy",
        "world order",
        "annihilate",
    )
    wave_markers = (
        "kill the leader",
        "assassinate",
        "overthrow",
        "declare war",
        "sabotage",
        "destroy the",
    )
    if any(marker in text for marker in tsunami_markers):
        return "tsunami"
    if any(marker in text for marker in wave_markers):
        return "wave"
    return "ripple"


def _suggestion_text(suggestion: ActionSuggestion | dict[str, Any]) -> str:
    if isinstance(suggestion, ActionSuggestion):
        return suggestion.intent_text or suggestion.label or ""
    if isinstance(suggestion, dict):
        return str(suggestion.get("intent_text") or suggestion.get("label") or "")
    return ""


def _suggestion_impact_tier(suggestion: ActionSuggestion | dict[str, Any]) -> str:
    if isinstance(suggestion, ActionSuggestion):
        tier = suggestion.impact_tier
    elif isinstance(suggestion, dict):
        tier = suggestion.get("impact_tier") or "ripple"
    else:
        tier = "ripple"
    tier_l = str(tier).strip().lower()
    return tier_l if tier_l in SANDBOX_IMPACT_TIERS else "ripple"


def _selected_impact_tier(state: GameState) -> str:
    user_input = (state.user_input or "").strip().lower()
    suggestions = list(state.suggested_actions or [])
    if user_input and suggestions:
        # 1) Exact/contained match against current action suggestions.
        for suggestion in suggestions:
            s_text = _suggestion_text(suggestion).strip().lower()
            if not s_text:
                continue
            if user_input == s_text or user_input in s_text or s_text in user_input:
                return _suggestion_impact_tier(suggestion)
        # 2) Fuzzy overlap fallback.
        user_words = set(re.findall(r"[a-z0-9']+", user_input))
        if user_words:
            best_score = 0.0
            best_tier = "ripple"
            for suggestion in suggestions:
                s_words = set(re.findall(r"[a-z0-9']+", _suggestion_text(suggestion).lower()))
                if not s_words:
                    continue
                overlap = len(user_words & s_words)
                score = overlap / max(1, len(s_words))
                if score > best_score:
                    best_score = score
                    best_tier = _suggestion_impact_tier(suggestion)
            if best_score >= 0.55:
                return best_tier
    # 3) Text-only heuristic when no suggestion match is available.
    return _impact_from_text(state.user_input or "")


def _stage_allows_impact(arc_stage: str, impact_tier: str) -> bool:
    tier_cfg = SANDBOX_IMPACT_TIERS.get(impact_tier) or SANDBOX_IMPACT_TIERS["ripple"]
    required_stage = str(tier_cfg.get("min_arc_stage") or "SETUP").upper()
    cur_rank = SANDBOX_ARC_STAGE_ORDER.get((arc_stage or "SETUP").upper(), 0)
    req_rank = SANDBOX_ARC_STAGE_ORDER.get(required_stage, 0)
    return cur_rank >= req_rank


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

        mode = _campaign_mode(state)
        impact_tier = "ripple"
        arc_stage = _arc_stage(state)
        if mode == "sandbox":
            impact_tier = _selected_impact_tier(state)
            if not _stage_allows_impact(arc_stage, impact_tier):
                required = str(SANDBOX_IMPACT_TIERS[impact_tier]["min_arc_stage"]).upper()
                return MechanicOutput(
                    action_type="ACTION",
                    time_cost_minutes=0,
                    events=[],
                    narrative_facts=[
                        f"Sandbox impact gate: {impact_tier.upper()} requires arc stage {required} or later.",
                    ],
                    outcome_summary=(
                        f"That action is too world-altering for this point in the story "
                        f"(current stage: {arc_stage}, required: {required})."
                    ),
                    tone_tag=TONE_TAG_NEUTRAL,
                    invalid_action=True,
                    rephrase_message=(
                        f"That is a {impact_tier} action and unlocks at {required}. "
                        "Try a smaller action for now."
                    ),
                    dice_result="Failure",
                    difficulty="Trivial",
                )

        # All other intents: delegate to LLM ResolutionAgent
        try:
            result = self._resolver.resolve(state)
        except Exception as resolve_err:
            logger.warning(
                "MechanicAgent: ResolutionAgent failed, returning graceful failure: %s",
                resolve_err,
            )
            result = MechanicOutput(
                action_type=(intent or "INTERACT"),
                dice_result="Failure",
                difficulty="Moderate",
                success=False,
                narrative_facts=["The outcome was uncertain \u2014 fate intervened."],
                outcome_summary="Action failed due to unforeseen circumstances.",
                invalid_action=False,
                time_cost_minutes=5,
                tone_tag=TONE_TAG_NEUTRAL,
            )

        # Phase 4.3: Sandbox impact-tier pressure on mechanics.
        if mode == "sandbox":
            tier_cfg = SANDBOX_IMPACT_TIERS.get(impact_tier) or SANDBOX_IMPACT_TIERS["ripple"]
            dc_mod = int(tier_cfg.get("dc_modifier") or 0)
            if dc_mod:
                result.modifiers = list(result.modifiers or []) + [
                    {"source": f"sandbox_impact:{impact_tier}", "value": dc_mod}
                ]
                if result.dc is not None:
                    result.dc = int(result.dc) + dc_mod
                updated_checks = []
                for c in list(result.checks or []):
                    if c.dc is not None:
                        c.dc = int(c.dc) + dc_mod
                    updated_checks.append(c)
                result.checks = updated_checks
            facts = list(result.narrative_facts or [])
            facts.append(f"Sandbox impact tier: {impact_tier}.")
            result.narrative_facts = facts

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

        # V1.1: WOUNDED state — mechanical DC penalty + restrict dangerous actions
        ws = _world_state_from_campaign(state.campaign)
        if ws.get("player_wounded"):
            # +2 DC penalty on all checks while wounded
            result.modifiers = list(result.modifiers or []) + [
                {"source": "wounded_penalty", "value": WOUNDED_DC_PENALTY}
            ]
            if result.dc is not None:
                result.dc = int(result.dc) + WOUNDED_DC_PENALTY
            for c in list(result.checks or []):
                if c.dc is not None:
                    c.dc = int(c.dc) + WOUNDED_DC_PENALTY
            facts = list(result.narrative_facts or [])
            facts.append("Player is WOUNDED: +2 DC penalty to all actions.")
            result.narrative_facts = facts
            result.world_reaction_needed = True

            # Restrict physically dangerous actions at extreme difficulty
            if result.action_type == "ATTACK" and result.difficulty in ("Formidable", "Extreme"):
                result.invalid_action = True
                result.rephrase_message = (
                    "You're too badly wounded for that. "
                    "Try a less physically demanding approach, or find healing first."
                )

        return result
