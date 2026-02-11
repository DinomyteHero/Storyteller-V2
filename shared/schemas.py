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

