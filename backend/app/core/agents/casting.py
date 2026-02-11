"""CastingAgent: spawn NPC via LLM; outputs NPC JSON for NPC_SPAWN event."""
from __future__ import annotations

import logging
import uuid
from typing import Any

from backend.app.core.agents.base import AgentLLM
from backend.app.core.json_reliability import call_with_json_reliability
from backend.app.core.error_handling import log_error_with_context
from shared.schemas import NPCSpawnOutput

logger = logging.getLogger(__name__)


def _default_npc(location_id: str) -> dict[str, Any]:
    return {
        "character_id": str(uuid.uuid4()),
        "name": "Wanderer",
        "role": "Wanderer",
        "relationship_score": 0,
        "secret_agenda": None,
        "location_id": location_id,
        "stats_json": {},
        "hp_current": 10,
    }


class CastingAgent:
    """Spawns NPC via LLM. Outputs: name, role, relationship_score, secret_agenda, location_id, stats_json, hp_current, character_id."""

    def __init__(self, llm: object | None = None) -> None:
        self._llm = llm

    def spawn(
        self,
        campaign_id: str,
        location_id: str,
        context: str = "",
        introduced_npcs: list[str] | None = None,
        npc_introduction_triggers: list[dict] | None = None,
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        """Return NPC dict for NPC_SPAWN payload. Respect introduced_npcs and triggers for pacing."""
        def fallback() -> dict[str, Any]:
            """Safe fallback NPC."""
            return _default_npc(location_id)

        llm = self._llm
        if llm is not None and not hasattr(llm, "complete"):
            llm = AgentLLM("casting")

        system = (
            "You are a casting director. Output ONLY valid JSON with keys: name, role, relationship_score (int 0-50), secret_agenda (short string or null), "
            "location_id, stats_json (object), hp_current (int). Add character_id as a UUID string. "
            "Use ONE simple, memorable name. Do not invent elaborate backstories or multiple NPCs. "
            "Keep introductions grounded and distinct from already-introduced characters."
        )
        parts = [f"Location: {location_id}.", f"Context: {context or 'random encounter'}."]
        if introduced_npcs:
            parts.append(f"Already introduced NPCs (avoid overlap): {', '.join(introduced_npcs[:15])}.")
        if npc_introduction_triggers:
            parts.append(f"Trigger to honor (create this NPC if specified): {npc_introduction_triggers}.")
        user = " ".join(parts)

        try:
            # Use JSON reliability wrapper (validates against NPCSpawnOutput schema)
            validated = call_with_json_reliability(
                llm=llm,
                role="casting",
                agent_name="CastingAgent.spawn",
                campaign_id=campaign_id,
                system_prompt=system,
                user_prompt=user,
                schema_class=NPCSpawnOutput,
                fallback_fn=fallback,
                warnings=warnings,
            )
            # Convert Pydantic model to dict and ensure required fields
            data = validated.model_dump(mode="json")
            data["character_id"] = data.get("character_id") or str(uuid.uuid4())
            data["location_id"] = data.get("location_id") or location_id
            data.setdefault("relationship_score", 0)
            data.setdefault("hp_current", 10)
            data.setdefault("stats_json", {})
            return data
        except Exception as e:
            log_error_with_context(
                error=e,
                node_name="encounter",
                campaign_id=campaign_id,
                turn_number=None,
                agent_name="CastingAgent.spawn",
                extra_context={"location_id": location_id},
            )
            logger.warning("CastingAgent.spawn failed after JSON validation, using fallback")
            from backend.app.core.warnings import add_warning
            add_warning(warnings, "LLM error: Casting used fallback output.")
            return fallback()
