from __future__ import annotations

from collections import deque

from backend.app.content.repository import ContentRepository
from backend.app.content.types import EncounterEntry, EncounterTable, Location, TravelLink


class LocationResolver:
    def __init__(
        self,
        repository: ContentRepository,
        setting_id: str | None = None,
        period_id: str | None = None,
        *,
        era_id: str | None = None,
    ) -> None:
        self.repository = repository
        self.setting_id = setting_id
        self.period_id = period_id
        self.era_id = era_id

    def _indices(self):
        if self.setting_id and self.period_id:
            return self.repository.get_indices(self.setting_id, self.period_id)
        if self.era_id:
            pack = self.repository.get_pack(self.era_id)
            metadata = pack.metadata if isinstance(pack.metadata, dict) else {}
            return self.repository.get_indices(metadata.get("setting_id", "star_wars_legends"), metadata.get("period_id", self.era_id))
        pack = self.repository.get_pack_by_alias()
        metadata = pack.metadata if isinstance(pack.metadata, dict) else {}
        return self.repository.get_indices(metadata.get("setting_id", "star_wars_legends"), metadata.get("period_id", "rebellion"))

    def get_location(self, location_id: str) -> Location | None:
        loc = self._indices().locations_by_id.get(location_id)
        if not loc:
            return None
        return Location(
            id=loc["id"],
            name=loc.get("name", loc["id"]),
            tags=tuple(loc.get("tags", [])),
            services=tuple(loc.get("services", [])),
            scene_types=tuple(loc.get("scene_types", [])),
            travel_links=tuple(TravelLink(**l) for l in loc.get("travel_links", [])),
            metadata=loc.get("metadata", {}),
        )

    def find_locations(self, tags: list[str] | None = None, services: list[str] | None = None, near: str | None = None, limit: int = 20) -> list[Location]:
        indices = self._indices()
        ids = list(indices.locations_by_id.keys())
        if tags:
            tag_hits: set[str] = set()
            for tag in tags:
                tag_hits.update(indices.locations_by_tag.get(tag, []))
            ids = [i for i in ids if i in tag_hits]
        if services:
            svc_hits: set[str] = set(ids)
            for svc in services:
                svc_hits &= set(indices.services_to_locations.get(svc, []))
            ids = [i for i in ids if i in svc_hits]
        if near:
            reachable = {l.id for l in self.get_reachable_locations(near, max_hops=1)}
            ids = [i for i in ids if i in reachable]
        return [self.get_location(i) for i in ids[:limit] if self.get_location(i)]

    def get_reachable_locations(self, from_location_id: str, max_hops: int = 1, tags: list[str] | None = None) -> list[Location]:
        indices = self._indices()
        visited = {from_location_id}
        queue = deque([(from_location_id, 0)])
        out: list[Location] = []
        while queue:
            current, hops = queue.popleft()
            if hops >= max_hops:
                continue
            for nxt in indices.travel_graph.get(current, []):
                if nxt in visited:
                    continue
                visited.add(nxt)
                queue.append((nxt, hops + 1))
                loc = self.get_location(nxt)
                if not loc:
                    continue
                if tags and not set(tags).intersection(set(loc.tags)):
                    continue
                out.append(loc)
        return out

    def get_encounter_table(self, location_id: str, scene_type: str | None = None) -> EncounterTable:
        loc = self._indices().locations_by_id.get(location_id) or {}
        entries = tuple(EncounterEntry(**e) for e in loc.get("encounter_table", []))
        return EncounterTable(location_id=location_id, scene_type=scene_type, entries=entries)
