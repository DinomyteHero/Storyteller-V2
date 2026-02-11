from __future__ import annotations

import hashlib
import random
from typing import Any

from backend.app.content.repository import ContentRepository
from backend.app.content.types import NPCBlueprint


class NpcResolver:
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

    def _rng(self, seed: str | int) -> random.Random:
        digest = hashlib.sha256(str(seed).encode("utf-8")).hexdigest()
        return random.Random(int(digest[:16], 16))

    def get_scene_cast(self, context: dict[str, Any], desired_count: int = 3) -> list[NPCBlueprint]:
        pack = self._pack()
        location_id = str(context.get("location_id") or "")
        tags = set(context.get("tags") or [])
        out: list[NPCBlueprint] = []

        for npc in pack.npcs.anchors:
            if npc.default_location_id == location_id:
                out.append(NPCBlueprint(id=npc.id, name=npc.name, faction_id=npc.faction_id, role=npc.role, tags=tuple(npc.tags), source="anchor"))

        rotating = []
        for npc in pack.npcs.rotating:
            if location_id and npc.default_location_id and npc.default_location_id != location_id:
                continue
            if tags and not tags.intersection(set(npc.tags or [])):
                continue
            rotating.append(npc)

        rng = self._rng(context.get("seed", "default-scene-cast"))
        rng.shuffle(rotating)
        for npc in rotating:
            if len(out) >= desired_count:
                break
            out.append(NPCBlueprint(id=npc.id, name=npc.name, faction_id=npc.faction_id, role=npc.role, tags=tuple(npc.tags), source="rotating"))

        while len(out) < desired_count and pack.npcs.templates:
            template = rng.choice(pack.npcs.templates)
            out.append(self.generate_npc(template_id=template.id, tags=None, seed=f"{context.get('seed','seed')}:{len(out)}", context=context))

        return out[:desired_count]

    def generate_npc(self, template_id: str | None = None, tags: list[str] | None = None, seed: str | int = "default", context: dict[str, Any] | None = None) -> NPCBlueprint:
        pack = self._pack()
        candidates = pack.npcs.templates
        if template_id:
            candidates = [t for t in candidates if t.id == template_id]
        if tags:
            tag_set = set(tags)
            candidates = [t for t in candidates if tag_set.intersection(set(t.tags or []))]
        if not candidates:
            raise ValueError("No NPC template candidates found")

        rng = self._rng(seed)
        template = rng.choice(candidates)
        namebank = pack.namebanks.get(template.namebank or "", []) if template.namebank else []
        generated_name = rng.choice(namebank) if namebank else f"{template.role.title()}-{rng.randint(100,999)}"
        return NPCBlueprint(
            id=f"proc-{template.id}-{rng.randint(1000,9999)}",
            name=generated_name,
            template_id=template.id,
            role=template.role,
            tags=tuple(template.tags or []),
            source="procedural",
            metadata={"context": context or {}},
        )
