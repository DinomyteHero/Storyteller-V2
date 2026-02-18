"""Campaign Architect: world simulation only (Clock-Tick).

V6.0: Campaign skeleton/bible generation has been moved to CampaignBibleAgent.
CampaignArchitect now handles ONLY the off-screen world simulation that runs
every world-tick (every 4 in-game hours). This keeps faction state, rumors,
and hidden events evolving autonomously between turns.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from backend.app.core.agents.base import AgentLLM
from backend.app.core.json_reliability import call_with_json_reliability
from backend.app.core.error_handling import log_error_with_context
from shared.schemas import WorldSimOutput

logger = logging.getLogger(__name__)


def _faction_dicts(active: list[Any]) -> list[dict[str, Any]]:
    """Normalize active_factions to list of dicts with location, current_goal, resources (1-10), is_hostile."""
    out = []
    for f in active if isinstance(active, list) else []:
        if not isinstance(f, dict):
            continue
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
    """World simulation (Clock-Tick): simulates off-screen faction moves, rumors, and hidden events.

    V6.0: Campaign skeleton / bible generation moved to CampaignBibleAgent.
    This class now handles only the per-tick world simulation used by WorldSimNode.
    """

    def __init__(self, llm: AgentLLM | None = None) -> None:
        self._llm = llm

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
            "updated_factions must reflect each faction's new resources and/or location after their off-screen moves.\n\n"
            "Example output:\n"
            '{"elapsed_time_summary":"Four hours passed. Night fell over the spaceport.",'
            '"faction_moves":["Crimson Claw moved a shipment through the lower docks"],'
            '"new_rumors":["A bounty hunter was seen asking about a Corellian freighter"],'
            '"hidden_events":["Shadow Wing planted a mole in the Merchant Coalition"],'
            '"updated_factions":[{"name":"Crimson Claw Syndicate","location":"loc-docking-bay",'
            '"current_goal":"Secure the spice shipment","resources":5,"is_hostile":true}]}'
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
