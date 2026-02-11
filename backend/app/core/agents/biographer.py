"""Biographer: produces character sheet from player concept."""
from __future__ import annotations

import logging
from typing import Any

from backend.app.core.agents.base import AgentLLM
from backend.app.core.json_reliability import call_with_json_reliability
from backend.app.core.error_handling import log_error_with_context
from shared.schemas import CharacterSheetOutput

logger = logging.getLogger(__name__)


# Deterministic concept-to-location mapping for fallback and validation
_CONCEPT_LOCATION_MAP: dict[str, list[str]] = {
    "smuggler": ["docking-bay", "spaceport", "cantina"],
    "pilot": ["hangar", "spaceport", "docking-bay"],
    "jedi": ["jedi-temple", "cantina"],
    "padawan": ["jedi-temple", "cantina"],
    "sith": ["lower-streets", "cantina"],
    "bounty hunter": ["cantina", "lower-streets"],
    "soldier": ["hangar", "command-center"],
    "trooper": ["hangar", "command-center"],
    "merchant": ["marketplace", "spaceport"],
    "trader": ["marketplace", "spaceport"],
    "spy": ["cantina", "lower-streets"],
    "diplomat": ["spaceport", "marketplace"],
    "senator": ["spaceport", "marketplace"],
    "scavenger": ["docking-bay", "lower-streets", "marketplace"],
    "mechanic": ["hangar", "docking-bay"],
    "medic": ["med-bay", "cantina"],
    "doctor": ["med-bay", "cantina"],
    "slicer": ["lower-streets", "cantina"],
    "mandalorian": ["cantina", "hangar"],
    "wookiee": ["docking-bay", "hangar"],
}


def _suggest_starting_location(
    player_concept: str,
    available_locations: list[str] | None = None,
) -> str:
    """Map player concept keywords to a starting location from available_locations.

    Scans player_concept for known archetype keywords, finds the first matching
    location in available_locations, falls back to loc-cantina.
    """
    concept_lower = player_concept.lower() if player_concept else ""
    available = available_locations or []
    # Normalize available locations to bare suffixes for matching
    available_suffixes: dict[str, str] = {}
    for loc in available:
        bare = loc.lower()
        for prefix in ("loc-", "loc_", "location-", "location_"):
            if bare.startswith(prefix):
                bare = bare[len(prefix):]
                break
        available_suffixes[bare] = loc

    # Check each concept keyword against the map
    for keyword, loc_prefs in _CONCEPT_LOCATION_MAP.items():
        if keyword in concept_lower:
            for pref in loc_prefs:
                if pref in available_suffixes:
                    return available_suffixes[pref]
            # Keyword matched but no preferred location in available list
            break

    # Default: loc-cantina if available, else first available, else literal fallback
    if "cantina" in available_suffixes:
        return available_suffixes["cantina"]
    if available:
        return available[0]
    return "loc-cantina"


class BiographerAgent:
    """Produces character sheet (name, stats, hp, starting_location, brief_background) from player_concept."""

    def __init__(self, llm: AgentLLM | None = None) -> None:
        self._llm = llm

    def build(
        self,
        player_concept: str,
        time_period: str | None = None,
        available_locations: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Return character_sheet dict: name, stats (e.g. Combat, Stealth, Charisma, Tech, General),
        hp_current, starting_location, background (short string).
        """
        def fallback() -> dict[str, Any]:
            """Safe fallback character sheet with concept-aware starting location.
            Enhanced to parse CYOA elements from player_concept if LLM fails."""
            loc = _suggest_starting_location(player_concept, available_locations)

            # Parse name from player_concept
            # Format: "Name -- motivation, origin, inciting_incident, edge"
            name = "Hero"
            if player_concept and "--" in player_concept:
                name = player_concept.split("--", 1)[0].strip()
                if not name:  # If empty before --, use fallback
                    name = "Hero"

            # Enhanced fallback: extract background from concept string
            # Supports both formats:
            #   Era background: "Name -- Background Name: concept1, concept2"
            #   Legacy CYOA:    "Name -- motivation, origin, inciting_incident"
            bg = "A traveler in a vast galaxy."
            if player_concept and "--" in player_concept:
                after_dash = player_concept.split("--", 1)[1].strip()
                if after_dash:
                    # Accept any non-empty content — even a single phrase is
                    # better than the generic fallback
                    bg = after_dash[0].upper() + after_dash[1:] if after_dash else after_dash
                    if bg and not bg.endswith((".", "!", "?")):
                        bg += "."

            return {
                "name": name,
                "stats": {"Combat": 2, "Stealth": 1, "Charisma": 2, "Tech": 1, "General": 2},
                "hp_current": 10,
                "starting_location": loc,
                "background": bg,
            }

        locations_list = ", ".join(available_locations) if available_locations else "loc-cantina, loc-docking-bay, loc-marketplace, loc-hangar, loc-spaceport"
        system = (
            "You are a biographer for a Star Wars narrative RPG. Output ONLY valid JSON with keys: "
            "name, stats (object with numeric values for Combat, Stealth, Charisma, Tech, General), "
            "hp_current (int), starting_location (string), background (short string).\n"
            "Choose starting_location based on the character's background:\n"
            "- Smugglers, traders, pilots -> loc-docking-bay, loc-spaceport, loc-hangar\n"
            "- Jedi, Force-sensitives -> loc-jedi-temple (if available), or loc-cantina\n"
            "- Bounty hunters, mercenaries -> loc-cantina, loc-lower-streets\n"
            "- Military, soldiers -> loc-command-center, loc-hangar\n"
            "- Diplomats, politicians -> loc-marketplace, loc-spaceport\n"
            f"Available locations: {locations_list}\n"
            "Use Star Wars-appropriate location names."
        )
        user = f"Player concept: {player_concept}. Era/time_period: {time_period or 'any'}."

        try:
            # Use JSON reliability wrapper (validates against CharacterSheetOutput schema)
            validated = call_with_json_reliability(
                llm=self._llm,
                role="biographer",
                agent_name="BiographerAgent.build",
                campaign_id=None,
                system_prompt=system,
                user_prompt=user,
                schema_class=CharacterSheetOutput,
                fallback_fn=fallback,
            )
            # Convert Pydantic model to dict (or use dict directly if fallback returned dict)
            result = validated.model_dump(mode="json") if isinstance(validated, CharacterSheetOutput) else validated
            # Validate: if LLM returned a location not in available list, override
            if available_locations and result.get("starting_location") not in available_locations:
                suggested = _suggest_starting_location(player_concept, available_locations)
                logger.info(
                    "BiographerAgent: LLM returned location %r not in available list, overriding to %r",
                    result.get("starting_location"), suggested,
                )
                result["starting_location"] = suggested
            return result
        except Exception as e:
            log_error_with_context(
                error=e,
                node_name="setup",
                campaign_id=None,
                turn_number=None,
                agent_name="BiographerAgent.build",
                extra_context={"player_concept": player_concept[:100] if player_concept else None, "time_period": time_period},
            )
            logger.warning("BiographerAgent.build failed after JSON validation, using fallback")
            return fallback()
