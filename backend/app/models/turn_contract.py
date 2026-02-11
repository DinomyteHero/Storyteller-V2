"""Strict turn contract and shared intent/outcome/state-delta schemas."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


IntentType = Literal[
    "TALK", "MOVE", "FIGHT", "SNEAK", "HACK", "INVESTIGATE", "REST", "BUY", "USE_ITEM", "FORCE", "PASSAGE"
]
OutcomeCategory = Literal["CRIT_FAIL", "FAIL", "PARTIAL", "SUCCESS", "CRIT_SUCCESS"]
RiskLevel = Literal["low", "med", "high"]
GameMode = Literal["SIM", "PASSAGE", "HYBRID"]


class Fact(BaseModel):
    fact_key: str
    fact_value: Any


class Intent(BaseModel):
    intent_type: IntentType
    target_ids: dict[str, str] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    user_utterance: str | None = None


class ChoiceCost(BaseModel):
    time_minutes: int = 0
    credits: int | None = None
    fatigue: int | None = None
    heat: int | None = None


class Choice(BaseModel):
    id: str
    label: str
    intent: Intent
    risk: RiskLevel
    cost: ChoiceCost = Field(default_factory=ChoiceCost)
    requirements_met: bool | None = None


class OutcomeCheck(BaseModel):
    skill: str
    dc: int
    roll: int
    total: int
    mods: dict[str, int] = Field(default_factory=dict)


class Outcome(BaseModel):
    category: OutcomeCategory
    check: OutcomeCheck | None = None
    consequences: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ObjectiveUpdate(BaseModel):
    objective_id: str
    progress_delta: int | None = None
    complete: bool | None = None


class StateDelta(BaseModel):
    time_minutes: int = 0
    health_delta: int | None = None
    credits_delta: int | None = None
    heat_delta: int | None = None
    inventory_add: list[str] = Field(default_factory=list)
    inventory_remove: list[str] = Field(default_factory=list)
    relationship_delta: dict[str, int] = Field(default_factory=dict)
    flags_set: dict[str, str | int | bool] = Field(default_factory=dict)
    objective_updates: list[ObjectiveUpdate] = Field(default_factory=list)
    facts_upsert: list[Fact] = Field(default_factory=list)


class TurnMeta(BaseModel):
    passage_id: str | None = None
    scene_id: str | None = None
    beats_remaining: int | None = None
    active_objectives: list[dict[str, Any]] = Field(default_factory=list)
    alignment: dict[str, int] | None = None
    reputations: dict[str, int] | None = None


class TurnDebug(BaseModel):
    validation_errors: list[str] = Field(default_factory=list)
    repaired: bool = False
    repair_count: int = 0


class TurnContract(BaseModel):
    mode: GameMode
    campaign_id: str
    turn_id: str
    display_text: str
    scene_goal: str
    obstacle: str
    stakes: str
    outcome: Outcome
    state_delta: StateDelta
    choices: list[Choice] = Field(min_length=2, max_length=4)
    meta: TurnMeta = Field(default_factory=TurnMeta)
    debug: TurnDebug | None = None

