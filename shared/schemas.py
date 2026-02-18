"""Shared Pydantic schemas used by the V2 agents (LLM JSON outputs)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FactionModel(BaseModel):
    """A faction in the living world (active_factions in world_state_json)."""

    name: str
    location: str = Field(..., description="Starting / current location within the world")
    current_goal: str = Field(..., description="What the faction is trying to achieve")
    resources: int = Field(..., ge=1, le=10, description="Faction resources 1-10")
    is_hostile: bool = Field(default=False, description="Whether the faction is hostile to the player")


class SetupOutput(BaseModel):
    """Architect campaign skeleton output (V2.5)."""

    title: str = "New Campaign"
    time_period: Optional[str] = None
    locations: List[str] = Field(default_factory=list, description="Location ids in the world")
    npc_cast: List[Dict[str, Any]] = Field(default_factory=list, description="12 NPCs: name, role, secret_agenda")
    active_factions: List[FactionModel] = Field(
        default_factory=list,
        description="3-5 active factions with conflicting goals and specific starting locations",
    )


class WorldSimOutput(BaseModel):
    """Output from the Architect world simulation (GM / Living World)."""

    elapsed_time_summary: str
    faction_moves: List[str] = Field(default_factory=list)
    new_rumors: List[str] = Field(default_factory=list, description="Public events")
    hidden_events: List[str] = Field(default_factory=list, description="GM only")
    updated_factions: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Updated active_factions to persist to world_state_json",
    )
    # 2.1: Faction memory for multi-turn plan continuity
    faction_memory: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    # 3.1: NPC autonomy state tracking
    npc_states: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class CharacterSheetOutput(BaseModel):
    """BiographerAgent JSON output: character sheet from player concept."""

    name: str
    stats: Dict[str, int] = Field(..., description="Combat, Stealth, Charisma, Tech, General")
    hp_current: int
    starting_location: str = Field(..., description="Location id, e.g. loc-cantina, loc-docking-bay, loc-hangar")
    starting_planet: str | None = Field(default=None, description="Planet name, e.g. Tatooine, Coruscant")
    background: str = Field(..., description="Short background string")
    gender: str | None = Field(default=None, description="male or female")


class NPCSpawnOutput(BaseModel):
    """CastingAgent JSON output: NPC spawn for NPC_SPAWN event."""

    character_id: str = Field(..., description="UUID string")
    name: str
    role: str
    relationship_score: int = Field(default=0, ge=-100, le=100)
    secret_agenda: Optional[str] = Field(default=None, description="Short string or null")
    location_id: str
    stats_json: Dict[str, Any] = Field(default_factory=dict)
    hp_current: int = Field(default=10)


class TurnEvent(BaseModel):
    """Turn event record (LLD / API)."""

    id: Optional[int] = None
    campaign_id: str
    turn_number: int
    event_type: str
    payload_json: Dict[str, Any] = Field(default_factory=dict)
    is_hidden: bool = False
    is_public_rumor: bool = False
    timestamp: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Phase 0.4 — Prologue Screenplay
# ---------------------------------------------------------------------------

class PrologueNpc(BaseModel):
    """An NPC in the prologue cast."""

    name: str
    role: str = Field(..., description="Brief role, e.g. 'mentor', 'antagonist', 'bystander'")
    motivation: str = ""
    location_id: str | None = None


class PrologueScreenplay(BaseModel):
    """PrologueScreenplayAgent output: sets up the opening scene before Arc 1.

    This is generated once at campaign creation and stored in
    ``world_state_json["prologue_screenplay"]``. The prologue turn loop
    reads it to constrain and colour the first 3-5 turns.
    """

    prologue_title: str = Field(..., description="Short evocative title for the prologue chapter")
    opening_location_id: str = Field(..., description="Location ID where the prologue begins")
    npc_cast: List[PrologueNpc] = Field(
        default_factory=list,
        description="2-4 NPCs who appear in the prologue",
    )
    inciting_moment: str = Field(
        ...,
        description="One-sentence description of the event that kicks off the story",
    )
    opening_narration: str = Field(
        default="",
        description="2-3 sentence atmospheric opening narration injected as the first scene",
    )
    departure_trigger: str = Field(
        ...,
        description="Condition that ends the prologue and hands off to Arc 1",
    )
    tone: str = Field(default="gritty", description="Overall tone: gritty, heroic, noir, etc.")
    origin_context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Handoff data written to world_state_json['origin_context'] at prologue end",
    )


# ---------------------------------------------------------------------------
# Phase 2.1 — Arc Screenplay
# ---------------------------------------------------------------------------

class ArcAct(BaseModel):
    """A single act in an arc's three-act structure."""

    summary: str = ""
    key_scenes: List[str] = Field(default_factory=list)
    must_include_npcs: List[str] = Field(default_factory=list)
    must_include_locations: List[str] = Field(default_factory=list)


class ArcScreenplay(BaseModel):
    """ArcScreenplayAgent output: per-arc narrative blueprint.

    Generated (optionally via cloud LLM) at campaign setup and stored in
    ``world_state_json["arc_screenplay"]``. The Director and ArcWeaver use
    it as a loose structural guide; player choices always override it.
    """

    title: str = Field(..., description="Arc title, e.g. 'Shadows of the Empire'")
    tone: str = Field(default="gritty", description="Arc tone: gritty, heroic, political, etc.")
    opening_crawl: str = Field(
        default="",
        description="Star Wars-style opening crawl text (2-4 sentences). Shown once at campaign start.",
    )
    act_structure: Dict[str, ArcAct] = Field(
        default_factory=dict,
        description="Keys: 'act_1', 'act_2', 'act_3'. Each act has summary + key_scenes.",
    )
    cast: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Named characters: name, role, motivation",
    )
    locations: List[str] = Field(
        default_factory=list,
        description="Location IDs that should feature prominently",
    )
    quests: List[str] = Field(
        default_factory=list,
        description="Quest IDs that should be available or seeded",
    )
    moments: List[str] = Field(
        default_factory=list,
        description="Moment IDs that should fire during this arc",
    )
    climax_question: str = Field(
        default="",
        description="The central dramatic question that the arc resolves",
    )
    resolution_hooks: List[str] = Field(
        default_factory=list,
        description="Seeds / dangling threads that feed into Arc 2",
    )

