"""Pydantic request/response models for V2 campaign API."""
from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.models.state import ActionSuggestion
from backend.app.models.turn_contract import Intent, TurnContract


# --- Request / Response models ---


class CreateCampaignRequest(BaseModel):
    title: str = "New Campaign"
    time_period: str | None = None
    genre: str | None = None
    player_name: str = "Player"
    starting_location: str = "Unknown"
    player_stats: dict[str, int] = Field(default_factory=dict)
    hp_current: int = 10
    # V3.1: Campaign scale — controls NPC/location/quest density
    campaign_scale: str = "medium"  # small | medium | large | epic


class CreateCampaignResponse(BaseModel):
    campaign_id: str
    player_id: str


class SetupAutoRequest(BaseModel):
    # Canonical content coordinates
    setting_id: str | None = None
    period_id: str | None = None
    # Legacy alias still accepted for backward compatibility
    time_period: str | None = None
    genre: str | None = None
    themes: list[str] = Field(default_factory=list)
    player_concept: str = "A hero in a vast world"
    # Optional starting location controls (Star Wars era packs)
    starting_location: str | None = None
    randomize_starting_location: bool = False
    # Era-specific background (Phase 1: SWTOR-style character creation)
    background_id: str | None = None
    background_answers: dict | None = None  # {question_id: choice_index, ...}
    # V2.8: Player gender for pronoun handling
    player_gender: str | None = None  # "male" or "female"
    # V2.10: Cross-campaign legacy — link to player profile
    player_profile_id: str | None = None
    # V3.0: Campaign mode — "historical" (lore immutable) or "sandbox" (player reshapes galaxy)
    campaign_mode: str = "historical"
    # V3.1: Campaign scale — controls NPC/location/quest density
    campaign_scale: str = "medium"  # small | medium | large | epic
    # V3.2: Difficulty — affects DC, damage, and HP modifiers
    difficulty: str = "normal"  # easy | normal | hard


class SetupAutoResponse(BaseModel):
    campaign_id: str
    player_id: str
    skeleton: dict
    character_sheet: dict


class ContentCatalogEntry(BaseModel):
    setting_id: str
    setting_display_name: str
    period_id: str
    period_display_name: str
    legacy_era_id: str
    source: str
    summary: str = ""
    playable: bool = True
    playability_reasons: list[str] = Field(default_factory=list)
    locations_count: int = 0
    backgrounds_count: int = 0
    companions_count: int = 0
    quests_count: int = 0


class ContentCatalogResponse(BaseModel):
    items: list[ContentCatalogEntry]


class ContentDefaultResponse(BaseModel):
    setting_id: str
    period_id: str
    legacy_era_id: str


class ContentSummaryResponse(BaseModel):
    setting_id: str
    period_id: str
    legacy_era_id: str
    backgrounds_count: int
    locations_count: int
    companions_count: int
    quests_count: int
    playable: bool


class TurnRequest(BaseModel):
    user_input: str = ""
    intent: Intent | None = None
    debug: bool = False
    include_state: bool = False


class PartyStatusItem(BaseModel):
    """Companion status for UI. Optional in turn response."""
    id: str
    name: str
    affinity: int
    loyalty_progress: int
    mood_tag: str | None = None
    # V2.20: PartyState fields (optional for backward compat)
    influence: int | None = None
    trust: int | None = None
    respect: int | None = None
    fear: int | None = None
    # V4.1: LLM-generated spoken reaction in companion voice
    spoken_reaction: str | None = None


class TurnResponse(BaseModel):
    """UI contract: required fields always present. state and debug are optional."""
    narrated_text: str
    suggested_actions: list[ActionSuggestion]
    player_sheet: dict
    inventory: list
    quest_log: dict
    world_time_minutes: int | None = None
    canonical_year_label: str | None = None
    state: dict | None = None
    debug: dict | None = None
    # Optional companion/alignment UI (render if present)
    party_status: list[PartyStatusItem] | None = None
    alignment: dict | None = None  # {light_dark, paragon_renegade}
    faction_reputation: dict | None = None
    # ME-style comms/briefing (UI contract: list of {id, headline, body, source_tag, urgency, related_factions})
    news_feed: list[dict] | None = None
    # Dev-only context stats (token budgeting info)
    context_stats: dict | None = None
    # Warning messages (LLM/RAG fallbacks, degradations)
    warnings: list[str] = Field(default_factory=list)
    # V2.17: Canonical DialogueTurn (scene + NPC utterance + player responses)
    dialogue_turn: dict | None = None
    turn_contract: TurnContract | None = None
    # V4.1: Dramatic moment type (TRIUMPH|DESPAIR|HP_CRITICAL|TURNING_POINT|NORMAL)
    consequence_type: str | None = None
    # V4.1: Present NPCs enriched with MemoryAgent state (emotional_state, agenda)
    active_npc_contexts: list[dict] | None = None


class CampaignSummary(BaseModel):
    """Lightweight campaign listing item for resume flows."""
    campaign_id: str
    title: str
    time_period: str | None = None
    player_id: str | None = None
    player_name: str | None = None
    current_turn: int = 0
    updated_at: str | None = None


class CampaignListResponse(BaseModel):
    items: list[CampaignSummary]

