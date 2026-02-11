from __future__ import annotations

from typing import Any

from backend.app.content.repository import ContentRepository
from backend.app.content.types import MissionInstance, MissionOffer


class MissionResolver:
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

    def _pack(self):
        if self.setting_id and self.period_id:
            return self.repository.get_content(self.setting_id, self.period_id)
        if self.era_id:
            return self.repository.get_pack(self.era_id)
        return self.repository.get_pack_by_alias()

    def get_available_missions(self, context: dict[str, Any]) -> list[MissionOffer]:
        pack = self._pack()
        location_id = context.get("location_id")
        turn = int(context.get("turn", 0))

        offers: list[MissionOffer] = []
        for quest in pack.quests:
            quest_location = getattr(quest, "location_id", None)
            if location_id and quest_location and quest_location != location_id:
                continue
            offers.append(
                MissionOffer(
                    id=quest.id,
                    title=quest.title,
                    location_id=quest_location,
                    source="authored",
                    tags=tuple(getattr(quest, "tags", []) or []),
                )
            )

        templates = []
        if isinstance(pack.metadata, dict):
            templates = [t for t in (pack.metadata.get("mission_templates") or []) if isinstance(t, dict)]
        for tmpl in templates:
            min_turn = int(tmpl.get("min_turn", 0))
            if turn < min_turn:
                continue
            offers.append(
                MissionOffer(
                    id=str(tmpl.get("id")),
                    title=str(tmpl.get("title") or tmpl.get("id")),
                    location_id=location_id,
                    source="procedural",
                    tags=tuple(tmpl.get("tags", [])),
                    metadata=tmpl,
                )
            )
        return offers

    def instantiate_mission(self, mission_offer_id: str, context: dict[str, Any], seed: int) -> MissionInstance:
        offers = self.get_available_missions(context)
        offer = next((o for o in offers if o.id == mission_offer_id), None)
        if offer is None:
            raise ValueError(f"Unknown mission offer id: {mission_offer_id}")
        objectives = tuple((offer.metadata or {}).get("objectives", [f"Complete mission: {offer.title}"]))
        return MissionInstance(
            id=f"instance-{offer.id}-{seed}",
            offer_id=offer.id,
            title=offer.title,
            seed=seed,
            objectives=objectives,
            metadata={"context": context, "source": offer.source},
        )
