"""Pydantic schemas for Director LLM output."""
from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.models.state import (
    ACTION_CATEGORY_EXPLORE,
    ACTION_RISK_SAFE,
    STRATEGY_TAG_OPTIMAL,
    TONE_TAG_NEUTRAL,
)


class ActionSuggestionLLM(BaseModel):
    """Schema for a single action in LLM JSON output."""
    label: str
    intent_text: str
    category: str = ACTION_CATEGORY_EXPLORE
    risk_level: str = ACTION_RISK_SAFE
    strategy_tag: str = STRATEGY_TAG_OPTIMAL
    tone_tag: str = TONE_TAG_NEUTRAL
    intent_style: str = ""
    consequence_hint: str = ""
    companion_reactions: dict[str, int] = Field(
        default_factory=dict,
        description="V2.9: Companion affinity deltas. E.g., {'comp-kira': 2, 'comp-vex': -1}"
    )
    risk_factors: list[str] = Field(
        default_factory=list,
        description="V2.9: Why is this risky? Max 3 factors. E.g., ['Outnumbered 3-to-1', 'No cover available']"
    )


class DirectorLLMOutput(BaseModel):
    """Schema for the full Director LLM JSON response.

    V2.7: Split action system supports both legacy (suggested_actions) and new (dialogue_options + action_options).
    - Legacy: suggested_actions contains mixed dialogue + action
    - New: dialogue_options (tone-based conversational) + action_options (physical/strategic)
    """
    director_instructions: str = ""
    suggested_actions: list[ActionSuggestionLLM] = Field(default_factory=list)  # Legacy format (still supported)
    dialogue_options: list[ActionSuggestionLLM] = Field(default_factory=list)  # V2.7: Tone-based conversational responses
    action_options: list[ActionSuggestionLLM] = Field(default_factory=list)  # V2.7: Physical/strategic moves
