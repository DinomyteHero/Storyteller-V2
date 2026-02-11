"""Campaign Architect: produces skeleton JSON + 12 NPC cast; world sim (Clock-Tick) returns WorldSimOutput."""
from __future__ import annotations

import json
import logging
from typing import Any

from backend.app.core.agents.base import AgentLLM
from backend.app.core.json_reliability import call_with_json_reliability
from backend.app.core.error_handling import log_error_with_context
from shared.schemas import WorldSimOutput, SetupOutput

logger = logging.getLogger(__name__)


def _faction_dicts(active: list[Any]) -> list[dict[str, Any]]:
    """Normalize active_factions to list of dicts with location, current_goal, resources (1-10), is_hostile."""
    out = []
    for f in active if isinstance(active, list) else []:
        if not isinstance(f, dict):
            continue
        # Accept both V2.5 (location, current_goal) and legacy (current_location, goal)
        loc = f.get("location") or f.get("current_location") or "loc-cantina"
        goal = f.get("current_goal") or f.get("goal") or ""
        res = f.get("resources", 5)
        if not isinstance(res, int) or res < 1 or res > 10:
            res = max(1, min(10, int(res) if isinstance(res, (int, float)) else 5))
        out.append({
            "name": f.get("name", "Faction"),
            "location": loc,
            "current_goal": goal,
            "resources": res,
            "is_hostile": bool(f.get("is_hostile", False)),
        })
    return out


class CampaignArchitect:
    """Produces campaign skeleton (title, time_period, locations, themes) and 12 NPC definitions with name, role, secret_agenda."""

    def __init__(self, llm: AgentLLM | None = None) -> None:
        self._llm = llm

    def build(
        self,
        time_period: str | None = None,
        themes: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Return skeleton dict (SetupOutput shape): title, time_period, locations, npc_cast, active_factions.
        active_factions: List[FactionModel] with name, location, current_goal, resources (1-10), is_hostile.
        If LLM available, use it; else return deterministic default.
        """
        def fallback() -> dict[str, Any]:
            """Deterministic fallback (V2.5: 3-5 factions with location, current_goal, resources 1-10, is_hostile)."""
            return {
                "title": "New Campaign",
                "time_period": time_period or "REBELLION",
                "locations": [
                    "loc-cantina", "loc-marketplace", "loc-docking-bay",
                    "loc-lower-streets", "loc-hangar", "loc-spaceport",
                ],
                "npc_cast": [
                    {"name": "Draven Koss", "role": "Villain", "secret_agenda": "Dominate the sector through ruthless control."},
                    {"name": "Vekk Tano", "role": "Rival", "secret_agenda": "Beat you to the prize — ambitious and relentless."},
                    {"name": "Nura Besh", "role": "Merchant", "secret_agenda": "Black market goods through Twi'lek trade networks."},
                    {"name": "Gorrak Mun", "role": "Merchant", "secret_agenda": "Grudge against syndicate — Sullustan never forgets."},
                    {"name": "Whisper", "role": "Informant", "secret_agenda": "Bothan spymaster — sells secrets."},
                    {"name": "Zeel Kaat", "role": "Informant", "secret_agenda": "Devaronian working multiple factions."},
                    {"name": "TK-4471", "role": "Guard", "secret_agenda": "Bribable."},
                    {"name": "Hera Solus", "role": "Local", "secret_agenda": "Mirialan who knows more than she lets on."},
                    {"name": "Renn Voss", "role": "Pilot", "secret_agenda": "Smuggles on the side."},
                    {"name": "Grumthar", "role": "Barkeep", "secret_agenda": "Ithorian barkeep — eavesdrops."},
                    {"name": "Pix", "role": "Mechanic", "secret_agenda": "Jawa tinkerer — intel on ships."},
                    {"name": "Sarik Vey", "role": "Stranger", "secret_agenda": "Chiss operative — just passing through."},
                ],
                "active_factions": [
                    {"name": "Crimson Claw Syndicate", "location": "loc-docking-bay", "current_goal": "Dominate the sector's smuggling routes", "resources": 5, "is_hostile": True},
                    {"name": "Merchant Coalition", "location": "loc-marketplace", "current_goal": "Control trade routes", "resources": 7, "is_hostile": False},
                    {"name": "Shadow Wing Cartel", "location": "loc-hangar", "current_goal": "Evade Republic/Imperial patrols", "resources": 4, "is_hostile": False},
                ],
                "world_state_json": {
                    "active_factions": [
                        {"name": "Crimson Claw Syndicate", "location": "loc-docking-bay", "current_goal": "Dominate the sector's smuggling routes", "resources": 5, "is_hostile": True},
                        {"name": "Merchant Coalition", "location": "loc-marketplace", "current_goal": "Control trade routes", "resources": 7, "is_hostile": False},
                        {"name": "Shadow Wing Cartel", "location": "loc-hangar", "current_goal": "Evade Republic/Imperial patrols", "resources": 4, "is_hostile": False},
                    ],
                },
            }

        system = (
            "You are the World Architect for a Star Wars narrative RPG. "
            "All factions, NPCs, and locations must be Star Wars-appropriate "
            "(e.g., use species like Twi'lek, Rodian, Wookiee, Zabrak, Bothan, Chiss; "
            "factions like syndicates, cartels, Imperial remnants, rebel cells, Hutt clans; "
            "locations like cantinas, docking bays, spaceports, hangars). "
            "When creating the campaign skeleton, you MUST create 3-5 active factions with conflicting goals. "
            "Assign them specific starting locations within the world. "
            "Output ONLY valid JSON with keys: "
            "title, time_period, locations (array of location ids), "
            "npc_cast (array of exactly 12 objects with name, role, secret_agenda), "
            "active_factions (array of 3-5 faction objects). "
            "Each faction in active_factions must have: name (str), location (str, starting location within the world), "
            "current_goal (str), resources (int, 1-10), is_hostile (bool). "
            "Roles in npc_cast must include exactly: Villain, Rival, 2x Merchant, 2x Informant, 6x generic (Guard, Local, Pilot, Barkeep, Mechanic, Stranger)."
        )
        user = (
            f"time_period: {time_period or 'any'}. themes: {themes or []}. "
            "Produce skeleton + 12 NPCs + 3-5 active_factions with conflicting goals and specific starting locations (use location ids from the world)."
        )

        try:
            # Use JSON reliability wrapper (validates against SetupOutput schema)
            validated = call_with_json_reliability(
                llm=self._llm,
                role="architect",
                agent_name="CampaignArchitect.build",
                campaign_id=None,
                system_prompt=system,
                user_prompt=user,
                schema_class=SetupOutput,
                fallback_fn=fallback,
            )
            # Convert Pydantic model to dict (or use dict directly if fallback returned dict)
            data = validated.model_dump(mode="json") if isinstance(validated, SetupOutput) else validated
            # Normalize active_factions (may be under world_state_json or top-level)
            active = data.get("active_factions")
            if not isinstance(active, list):
                ws = data.get("world_state_json")
                active = (ws.get("active_factions") if isinstance(ws, dict) else None) or []
            if not isinstance(active, list):
                active = []
            # Ensure world_state_json for backward compat and DB persistence
            data["active_factions"] = active
            data["world_state_json"] = {"active_factions": _faction_dicts(active)}
            return data
        except Exception as e:
            log_error_with_context(
                error=e,
                node_name="architect",
                campaign_id=None,
                turn_number=None,
                agent_name="CampaignArchitect.build",
                extra_context={"time_period": time_period, "themes": themes},
            )
            logger.warning("CampaignArchitect.build failed, using fallback")
            return fallback()

    def simulate_off_screen(
        self,
        campaign_id: str,
        world_state_context: str = "",
        active_factions: list[dict] | None = None,
        warnings: list[str] | None = None,
    ) -> WorldSimOutput:
        """
        Simulate what happens off-screen (factions, rumors). Returns WorldSimOutput.
        Used by WorldSimNode when world_time_minutes hits tick interval.
        If active_factions is provided, inject into prompt and ask LLM to return updated_factions
        (updated resources and/or current_location per faction).
        """
        factions = active_factions or []

        def fallback() -> WorldSimOutput:
            """Safe fallback: no-op WorldSimOutput."""
            return WorldSimOutput(
                elapsed_time_summary="Time advanced.",
                faction_moves=[],
                new_rumors=[],
                hidden_events=[],
                updated_factions=None,
            )

        system = (
            "You are a campaign architect simulating off-screen world events. "
            "Output ONLY valid JSON with keys: elapsed_time_summary (string), "
            "faction_moves (array of strings), new_rumors (array of strings, public events), "
            "hidden_events (array of strings, GM-only), "
            "updated_factions (array of faction objects: name, location, current_goal, resources (1-10), is_hostile). "
            "updated_factions must reflect each faction's new resources and/or location after their off-screen moves."
        )
        factions_blob = json.dumps(factions) if factions else "[]"
        user = (
            f"Campaign id: {campaign_id}. "
            f"{world_state_context or 'No extra context.'} "
            f"Current active_factions (from world_state_json): {factions_blob}. "
            "Simulate off-screen moves. Return updated_factions with updated resources or location for each faction (same shape: name, location, current_goal, resources, is_hostile)."
        )

        try:
            # Use JSON reliability wrapper (validates against WorldSimOutput schema)
            validated = call_with_json_reliability(
                llm=self._llm,
                role="architect",
                agent_name="CampaignArchitect.simulate_off_screen",
                campaign_id=campaign_id,
                system_prompt=system,
                user_prompt=user,
                schema_class=WorldSimOutput,
                fallback_fn=fallback,
                warnings=warnings,
            )
            # Normalize updated_factions
            if validated.updated_factions:
                validated.updated_factions = _faction_dicts(validated.updated_factions)
            return validated
        except Exception as e:
            log_error_with_context(
                error=e,
                node_name="world_sim",
                campaign_id=campaign_id,
                turn_number=None,
                agent_name="CampaignArchitect.simulate_off_screen",
                extra_context={"world_state_context": world_state_context[:200] if world_state_context else None},
            )
            logger.warning("World sim LLM failed for campaign %s; returning no-op WorldSimOutput", campaign_id)
            from backend.app.core.warnings import add_warning
            add_warning(warnings, "LLM error: Architect used fallback output.")
            return fallback()
