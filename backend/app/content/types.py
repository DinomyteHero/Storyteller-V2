from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TravelLink:
    to_location_id: str
    method: str = "travel"
    risk: str | int | None = None
    cost: int | None = None


@dataclass(frozen=True)
class EncounterEntry:
    template_id: str
    weight: int = 1
    conditions: Any | None = None


@dataclass(frozen=True)
class EncounterTable:
    location_id: str
    scene_type: str | None = None
    entries: tuple[EncounterEntry, ...] = ()


@dataclass(frozen=True)
class Location:
    id: str
    name: str
    tags: tuple[str, ...] = ()
    services: tuple[str, ...] = ()
    travel_links: tuple[TravelLink, ...] = ()
    scene_types: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NPCBlueprint:
    id: str
    name: str | None = None
    template_id: str | None = None
    faction_id: str | None = None
    role: str | None = None
    tags: tuple[str, ...] = ()
    source: str = "procedural"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MissionOffer:
    id: str
    title: str
    location_id: str | None = None
    source: str = "authored"
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MissionInstance:
    id: str
    offer_id: str
    title: str
    seed: int
    objectives: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
