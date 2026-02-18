"""PrologueScreenplayAgent: generates an opening scene blueprint before Arc 1.

The agent takes the player's background, species, and choice effects from
character creation and produces a ``PrologueScreenplay`` that seeds the first
3-5 prologue turns with atmosphere, an NPC cast, and an inciting moment.

Pattern mirrors BiographerAgent/CampaignArchitect: AgentLLM("prologue") +
call_with_json_reliability() + deterministic fallback.
"""
from __future__ import annotations

import logging
from typing import Any

from backend.app.core.agents.base import AgentLLM
from backend.app.core.json_reliability import call_with_json_reliability
from backend.app.core.error_handling import log_error_with_context
from shared.schemas import PrologueScreenplay, PrologueNpc

logger = logging.getLogger(__name__)


def _build_fallback_screenplay(
    background_id: str,
    species_id: str,
    prologue_scenario: str | None,
    setting_name: str,
    opening_location_id: str,
) -> dict[str, Any]:
    """Deterministic fallback when LLM is unavailable."""
    title_map: dict[str, str] = {
        "smuggler": "A Debt Comes Due",
        "bounty_hunter": "The Last Contract",
        "force_sensitive_exile": "Ashes of the Order",
        "imperial_officer": "Orders and Conscience",
        "rebel_operative": "First Blood",
        "imperial_defector": "The Point of No Return",
    }
    tone_map: dict[str, str] = {
        "smuggler": "gritty",
        "bounty_hunter": "noir",
        "force_sensitive_exile": "melancholic",
        "imperial_officer": "tense",
        "rebel_operative": "heroic",
        "imperial_defector": "paranoid",
    }
    bg_key = (background_id or "").lower().replace("-", "_")
    title = title_map.get(bg_key, "The Beginning")
    tone = tone_map.get(bg_key, "gritty")
    scenario = prologue_scenario or f"A {species_id} with a {background_id} background faces an immediate crisis."

    return {
        "prologue_title": title,
        "opening_location_id": opening_location_id,
        "npc_cast": [
            {
                "name": "Contact",
                "role": "ally",
                "motivation": "Has information the player needs",
                "location_id": opening_location_id,
            },
            {
                "name": "Complication",
                "role": "antagonist",
                "motivation": "Wants something the player has",
                "location_id": opening_location_id,
            },
        ],
        "inciting_moment": scenario,
        "opening_narration": (
            f"The {setting_name} universe is a dangerous place. "
            "Every decision leaves a mark. This is where your story begins."
        ),
        "departure_trigger": "Resolve the immediate crisis to move forward.",
        "tone": tone,
        "origin_context": {
            "background_id": background_id,
            "species_id": species_id,
            "prologue_completed": False,
        },
    }


class PrologueScreenplayAgent:
    """Generates a PrologueScreenplay from background + choice effects.

    Call ``generate()`` after character creation to produce the opening
    scene blueprint. The result is stored in
    ``world_state_json["prologue_screenplay"]``.
    """

    def __init__(self, llm: AgentLLM | None = None) -> None:
        self._llm = llm

    def generate(
        self,
        background_id: str,
        species_id: str,
        choice_effects: list[dict[str, Any]] | None = None,
        setting_rules: Any | None = None,
        available_locations: list[str] | None = None,
        prologue_scenario: str | None = None,
    ) -> dict[str, Any]:
        """Generate a PrologueScreenplay dict.

        Args:
            background_id: Background identifier (e.g. "smuggler").
            species_id: Species identifier (e.g. "twi_lek").
            choice_effects: List of BackgroundChoiceEffect dicts from
                the character creation CYOA answers.
            setting_rules: Optional SettingRules instance for universe context.
            available_locations: Location IDs available in the current era pack.
            prologue_scenario: Seed text from EraBackground.prologue_scenario.
        Returns:
            PrologueScreenplay as a dict (validated via Pydantic).
        """
        from backend.app.world.era_pack_models import SettingRules
        sr: SettingRules = (
            setting_rules if isinstance(setting_rules, SettingRules) else SettingRules()
        )

        # Pick a sensible default opening location
        locs = available_locations or []
        opening_loc = (
            next((l for l in locs if "cantina" in l.lower()), None)
            or next((l for l in locs if "safe" in l.lower()), None)
            or (locs[0] if locs else "loc-cantina")
        )

        def fallback() -> dict[str, Any]:
            return _build_fallback_screenplay(
                background_id=background_id,
                species_id=species_id,
                prologue_scenario=prologue_scenario,
                setting_name=sr.setting_name,
                opening_location_id=opening_loc,
            )

        # Build compact effects summary for the prompt
        effects_lines: list[str] = []
        for eff in (choice_effects or []):
            if isinstance(eff, dict):
                parts = []
                if eff.get("alignment_nudge"):
                    parts.append(f"alignment={eff['alignment_nudge']}")
                if eff.get("psych_seed"):
                    parts.append(f"psych={eff['psych_seed']}")
                if eff.get("npc_seed"):
                    parts.append(f"npc={eff['npc_seed']}")
                if eff.get("quest_seed"):
                    parts.append(f"quest={eff['quest_seed']}")
                if parts:
                    q = eff.get("question_id", "?")
                    effects_lines.append(f"  {q}: {', '.join(parts)}")
        effects_summary = "\n".join(effects_lines) if effects_lines else "(no effects)"

        locs_str = ", ".join(locs[:10]) if locs else "loc-cantina"
        scenario_hint = (
            f"Background scenario seed: {prologue_scenario}" if prologue_scenario else ""
        )

        system = (
            f"You are {sr.biographer_role}, writing the opening scene blueprint for "
            f"a {sr.setting_name} narrative RPG prologue.\n"
            "Output ONLY valid JSON matching this exact structure:\n"
            "{\n"
            '  "prologue_title": "Short evocative chapter title",\n'
            f'  "opening_location_id": "one of: {locs_str}",\n'
            '  "npc_cast": [\n'
            '    {"name": "str", "role": "ally|antagonist|bystander", "motivation": "str", "location_id": "str or null"}\n'
            "  ],\n"
            '  "inciting_moment": "One sentence: the event that kicks off the story",\n'
            '  "opening_narration": "2-3 sentence atmospheric narration",\n'
            '  "departure_trigger": "Condition that ends the prologue",\n'
            '  "tone": "gritty|heroic|noir|melancholic|tense|paranoid",\n'
            '  "origin_context": {"background_id": "str", "species_id": "str", "prologue_completed": false}\n'
            "}\n"
            "Rules:\n"
            "- 2-4 NPCs in npc_cast\n"
            "- The inciting_moment must create immediate tension\n"
            "- opening_location_id must be one of the available locations\n"
            f"- Tone must fit {sr.setting_name} {sr.setting_genre}\n"
            f"- {scenario_hint}\n"
        )
        user = (
            f"Background: {background_id}\n"
            f"Species: {species_id}\n"
            f"Character creation choices:\n{effects_summary}\n"
            f"Era/setting: {sr.setting_name}"
        )

        try:
            validated = call_with_json_reliability(
                llm=self._llm,
                role="prologue",
                agent_name="PrologueScreenplayAgent.generate",
                campaign_id=None,
                system_prompt=system,
                user_prompt=user,
                schema_class=PrologueScreenplay,
                fallback_fn=fallback,
            )
            result = (
                validated.model_dump(mode="json")
                if isinstance(validated, PrologueScreenplay)
                else validated
            )
            # Ensure opening_location_id is valid
            if locs and result.get("opening_location_id") not in locs:
                result["opening_location_id"] = opening_loc
            return result
        except Exception as e:
            log_error_with_context(
                error=e,
                node_name="prologue",
                campaign_id=None,
                turn_number=None,
                agent_name="PrologueScreenplayAgent.generate",
                extra_context={
                    "background_id": background_id,
                    "species_id": species_id,
                },
            )
            logger.warning(
                "PrologueScreenplayAgent.generate failed, using fallback: %s", e
            )
            return fallback()
