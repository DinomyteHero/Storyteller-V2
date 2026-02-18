"""MechanicAgent: routes action resolution through the LLM-based ResolutionAgent.

V4.0: Replaced deterministic d20 Python engine with ResolutionAgent — a Game Master LLM that
reads the Storyteller Core rule system and resolves actions contextually. No deterministic
fallbacks. All dice, DC, events, and consequence logic is LLM-driven.

The MechanicAgent class is kept as the stable public interface so that the LangGraph node
(nodes/mechanic.py) and any callers remain unchanged.
"""
from __future__ import annotations

import logging

from backend.app.models.state import (
    GameState,
    MechanicOutput,
    TONE_TAG_PARAGON,
    TONE_TAG_NEUTRAL,
)
from backend.app.time_economy import get_time_cost, DIALOGUE_ONLY_MINUTES
from backend.app.core.agents.resolution_agent import ResolutionAgent

logger = logging.getLogger(__name__)


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
        return self._resolver.resolve(state)
