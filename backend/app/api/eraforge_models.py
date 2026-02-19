"""Pydantic request/response models for EraForge API."""
from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Phase 1: Period Discovery
# ---------------------------------------------------------------------------


class EraForgeSuggestRequest(BaseModel):
    """User provides a setting name; system proposes time periods."""

    setting_prompt: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Setting description, e.g. 'Game of Thrones', 'Warhammer 40k'",
    )


class EraForgePeriodProposal(BaseModel):
    """A single proposed time period within the setting."""

    period_id: str = Field(..., description="Normalized identifier, e.g. 'war_of_five_kings'")
    display_name: str = Field(..., description="Human-readable, e.g. 'War of the Five Kings'")
    time_period: str = Field(..., description="Date/era label, e.g. '298-300 AC'")
    summary: str = Field(..., description="2-3 sentence summary of this time period")
    tone: str = Field(default="", description="e.g. 'political intrigue, brutal warfare'")
    key_conflicts: list[str] = Field(default_factory=list)


class EraForgeSuggestOutput(BaseModel):
    """LLM output schema for period discovery (validated via call_with_json_reliability)."""

    setting_id: str = Field(..., description="Normalized setting identifier")
    setting_name: str = Field(..., description="Display name for the setting")
    setting_genre: str = Field(default="fantasy", description="Genre descriptor")
    periods: list[EraForgePeriodProposal] = Field(..., min_length=1, max_length=7)


class EraForgeSuggestResponse(BaseModel):
    """API response for period suggestion."""

    setting_id: str
    setting_name: str
    setting_genre: str
    periods: list[EraForgePeriodProposal]


# ---------------------------------------------------------------------------
# Phase 2: Pack Generation
# ---------------------------------------------------------------------------


class EraForgeGenerateRequest(BaseModel):
    """User picks a period; system generates the full era pack."""

    setting_id: str
    setting_name: str
    setting_genre: str = "fantasy"
    period_id: str
    display_name: str
    time_period: str
    summary: str
    tone: str = ""
    key_conflicts: list[str] = Field(default_factory=list)
    source_prompt: str = ""  # original user input for audit trail


class EraForgeGenerateResponse(BaseModel):
    """API response after pack generation."""

    setting_id: str
    period_id: str
    display_name: str
    version: int
    pack_id: int  # generated_era_packs.id
    backgrounds_count: int
    species_count: int
    canon_characters_count: int


# ---------------------------------------------------------------------------
# Phase 3: Canon Character Refinement
# ---------------------------------------------------------------------------


class EraForgeRefineCanonRequest(BaseModel):
    """After background selection, refine canon character proximity."""

    pack_id: int  # generated_era_packs.id
    background_id: str
    background_name: str = ""
    background_description: str = ""
    location_hints: list[str] = Field(
        default_factory=list,
        description="Location hints from background CYOA answers",
    )
    faction_hints: list[str] = Field(
        default_factory=list,
        description="Faction hints from background CYOA answers",
    )


class EraForgeRefineCanonResponse(BaseModel):
    """API response after canon character refinement."""

    pack_id: int
    canon_characters_count: int
    adjustments_made: int  # how many characters had proximity changed
