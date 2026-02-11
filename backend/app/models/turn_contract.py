"""Strict turn contract models used by API + validators."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


IntentType = Literal[
    "TALK",
    "MOVE",
    "FIGHT",
    "SNEAK",
    "HACK",
    "INVESTIGATE",
    "REST",
    "BUY",
    "USE_ITEM",
    "FORCE",
]

OutcomeTier = Literal["CRIT_FAIL", "FAIL", "PARTIAL", "SUCCESS", "CRIT_SUCCESS"]
RiskTier = Literal["low", "med", "high"]


class IntentTargetIds(BaseModel):
    npc_id: str | None = None
    location_id: str | None = None
    item_id: str | None = None
    faction_id: str | None = None


class Intent(BaseModel):
    intent_type: IntentType
    target_ids: IntentTargetIds = Field(default_factory=IntentTargetIds)
    params: dict[str, Any] = Field(default_factory=dict)
    user_utterance: str | None = None


class ChoiceCost(BaseModel):
    time_minutes: int = Field(default=0, ge=0)
    credits: int | None = None
    fatigue: int | None = None
    heat: int | None = None


class Choice(BaseModel):
    id: str
    label: str
    intent: Intent
    risk: RiskTier
    cost: ChoiceCost = Field(default_factory=ChoiceCost)


class StateDelta(BaseModel):
    health: int = 0
    credits: int = 0
    heat: int = 0
    time_minutes: int = 0
    fatigue: int = 0
    inventory: list[dict[str, Any]] = Field(default_factory=list)
    relationships: dict[str, int] = Field(default_factory=dict)
    objectives: list[dict[str, Any]] = Field(default_factory=list)
    facts: dict[str, Any] = Field(default_factory=dict)


class Outcome(BaseModel):
    check: str = "NONE"
    difficulty: int | None = None
    roll: int | None = None
    skill_mod: int = 0
    situational_mod: int = 0
    total: int | None = None
    result: OutcomeTier


class TurnContract(BaseModel):
    scene_goal: str
    obstacle: str
    stakes: str
    choices: list[Choice] = Field(min_length=2, max_length=4)
    outcome: Outcome
    state_delta: StateDelta
    narration: str
    next_scene_hint: str | None = None
