"""Pydantic event and payload models for event-sourced architecture.

All payloads are JSON-serializable. Event.payload is stored as a plain dict.
"""
from typing import Any, Optional, Union

from pydantic import BaseModel, Field


class Event(BaseModel):
    """Generic event envelope."""
    event_type: str
    payload: dict = Field(default_factory=dict)
    is_hidden: bool = False
    is_public_rumor: bool = False


# --- Typed payload models (minimal, JSON-serializable) ---


class MovePayload(BaseModel):
    character_id: str
    from_location: Optional[str] = None
    to_location: str


class DamagePayload(BaseModel):
    character_id: str
    amount: int
    source: Optional[str] = None


class HealPayload(BaseModel):
    character_id: str
    amount: int
    source: Optional[str] = None


class ItemDeltaPayload(BaseModel):
    owner_id: str
    item_name: str
    quantity_delta: int
    attributes: dict = Field(default_factory=dict)


class FlagSetPayload(BaseModel):
    key: str
    value: Any


class RelationshipPayload(BaseModel):
    npc_id: str
    delta: int
    reason: Optional[str] = None


PayloadUnion = Union[
    MovePayload,
    DamagePayload,
    HealPayload,
    ItemDeltaPayload,
    FlagSetPayload,
    RelationshipPayload,
]
