from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.world.era_pack_models import EraPack


@dataclass(frozen=True)
class ContentIndices:
    locations_by_id: dict[str, dict[str, Any]]
    locations_by_tag: dict[str, list[str]]
    services_to_locations: dict[str, list[str]]
    travel_graph: dict[str, list[str]]
    npc_templates_by_id: dict[str, dict[str, Any]]
    npc_templates_by_tag: dict[str, list[str]]
    anchors_by_location: dict[str, list[str]]
    rotating_pool_by_tag: dict[str, list[str]]
    quests_by_id: dict[str, dict[str, Any]]
    quests_by_tag: dict[str, list[str]]
    quests_by_location: dict[str, list[str]]
    mission_templates_by_id: dict[str, dict[str, Any]]
    namebanks: dict[str, dict[str, dict[str, list[str]]]]


def build_indices(pack: EraPack) -> ContentIndices:
    locations_by_id = {l.id: l.model_dump(mode="json") for l in pack.locations}
    locations_by_tag: dict[str, list[str]] = {}
    services_to_locations: dict[str, list[str]] = {}
    travel_graph: dict[str, list[str]] = {}
    for loc in pack.locations:
        for tag in loc.tags or []:
            locations_by_tag.setdefault(tag, []).append(loc.id)
        for svc in loc.services or []:
            services_to_locations.setdefault(svc, []).append(loc.id)
        travel_graph[loc.id] = [link.to_location_id for link in loc.travel_links or []]

    npc_templates_by_id = {t.id: t.model_dump(mode="json") for t in pack.npcs.templates}
    npc_templates_by_tag: dict[str, list[str]] = {}
    for t in pack.npcs.templates:
        for tag in t.tags or []:
            npc_templates_by_tag.setdefault(tag, []).append(t.id)

    anchors_by_location: dict[str, list[str]] = {}
    for npc in pack.npcs.anchors:
        if npc.default_location_id:
            anchors_by_location.setdefault(npc.default_location_id, []).append(npc.id)

    rotating_pool_by_tag: dict[str, list[str]] = {}
    for npc in pack.npcs.rotating:
        for tag in npc.tags or []:
            rotating_pool_by_tag.setdefault(tag, []).append(npc.id)

    quests_by_id = {q.id: q.model_dump(mode="json") for q in pack.quests}
    quests_by_tag: dict[str, list[str]] = {}
    quests_by_location: dict[str, list[str]] = {}
    for q in pack.quests:
        for tag in getattr(q, "tags", []) or []:
            quests_by_tag.setdefault(tag, []).append(q.id)
        loc_id = getattr(q, "location_id", None)
        if loc_id:
            quests_by_location.setdefault(loc_id, []).append(q.id)

    mission_templates = []
    if isinstance(pack.metadata, dict):
        mission_templates = [
            m for m in (pack.metadata.get("mission_templates") or []) if isinstance(m, dict)
        ]
    mission_templates_by_id = {
        str(m.get("id")): m for m in mission_templates if m.get("id")
    }

    normalized_namebanks: dict[str, dict[str, dict[str, list[str]]]] = {}
    for key, values in (pack.namebanks or {}).items():
        if isinstance(values, list):
            normalized_namebanks.setdefault(key, {}).setdefault("default", {})["default"] = list(values)
        elif isinstance(values, dict):
            culture_bucket: dict[str, dict[str, list[str]]] = {}
            for culture, gender_map in values.items():
                if isinstance(gender_map, dict):
                    culture_bucket[str(culture)] = {
                        str(g): list(v)
                        for g, v in gender_map.items()
                        if isinstance(v, list)
                    }
            if culture_bucket:
                normalized_namebanks[key] = culture_bucket

    return ContentIndices(
        locations_by_id=locations_by_id,
        locations_by_tag=locations_by_tag,
        services_to_locations=services_to_locations,
        travel_graph=travel_graph,
        npc_templates_by_id=npc_templates_by_id,
        npc_templates_by_tag=npc_templates_by_tag,
        anchors_by_location=anchors_by_location,
        rotating_pool_by_tag=rotating_pool_by_tag,
        quests_by_id=quests_by_id,
        quests_by_tag=quests_by_tag,
        quests_by_location=quests_by_location,
        mission_templates_by_id=mission_templates_by_id,
        namebanks=normalized_namebanks,
    )
