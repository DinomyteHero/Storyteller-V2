"""OriginScreenplayAgent: generates a playable backstory blueprint.

The origin story is a short (3-turn) interactive sequence that lets the
player experience their character's background before the prologue begins.
Think Dragon Age: Origins — you play through a defining moment from your
character's past.

Pattern mirrors PrologueScreenplayAgent: AgentLLM("origin") +
call_with_json_reliability() + deterministic fallback.
"""
from __future__ import annotations

import logging
from typing import Any

from backend.app.core.agents.base import AgentLLM
from backend.app.core.json_reliability import call_with_json_reliability
from backend.app.core.error_handling import log_error_with_context
from shared.schemas import OriginScreenplay

logger = logging.getLogger(__name__)


def _build_fallback_origin(
    background_id: str,
    species_id: str,
    background_name: str,
    prologue_scenario: str | None,
    setting_name: str,
) -> dict[str, Any]:
    """Deterministic fallback when LLM is unavailable."""
    title_map: dict[str, str] = {
        "smuggler": "The Run That Changed Everything",
        "bounty_hunter": "The Mark You Couldn't Forget",
        "force_sensitive_exile": "The Day the Temple Fell",
        "imperial_officer": "The Order That Broke You",
        "rebel_operative": "Your First Mission",
        "imperial_defector": "The Line You Wouldn't Cross",
        "mandalorian_exile": "The Day You Lost Your Clan",
        "outlaw_tech": "The Invention That Went Wrong",
    }
    tone_map: dict[str, str] = {
        "smuggler": "tense",
        "bounty_hunter": "intimate",
        "force_sensitive_exile": "bittersweet",
        "imperial_officer": "tense",
        "rebel_operative": "hopeful",
        "imperial_defector": "tense",
        "mandalorian_exile": "bittersweet",
        "outlaw_tech": "intimate",
    }
    bg_key = (background_id or "").lower().replace("-", "_")
    title = title_map.get(bg_key, "Before It All Began")
    tone = tone_map.get(bg_key, "intimate")
    bg_display = background_name or background_id.replace("_", " ").title()

    scenario = prologue_scenario or (
        f"A defining moment in the life of a {species_id} {bg_display}."
    )

    return {
        "origin_title": title,
        "setting_description": (
            f"Before the main adventure, there was a moment that defined who you are. "
            f"As a {bg_display} in the {setting_name} universe, "
            f"this is the story of how you became who you are today."
        ),
        "opening_scene": (
            f"The memory is sharp, even now. {scenario} "
            f"This is where your story truly begins — not with the adventure ahead, "
            f"but with the choice that set everything in motion."
        ),
        "dilemma": (
            f"You face a decision that will reveal who you truly are. "
            f"There is no right answer — only the one you can live with."
        ),
        "resolution_hook": (
            "This moment echoes forward, shaping every choice you'll make in the days ahead."
        ),
        "npc_cast": [
            {
                "name": "A Figure From Your Past",
                "role": "mentor",
                "relationship_to_player": "ally",
            }
        ],
        "tone": tone,
        "background_id": background_id,
        "species_id": species_id,
    }


class OriginScreenplayAgent:
    """Generates an OriginScreenplay from background + choice effects.

    Call ``generate()`` after character creation (before prologue) to produce
    the playable backstory blueprint. The result is stored in
    ``world_state_json["origin_screenplay"]``.
    """

    def __init__(self, llm: AgentLLM | None = None) -> None:
        self._llm = llm

    def generate(
        self,
        background_id: str,
        species_id: str,
        background_name: str = "",
        choice_effects: list[dict[str, Any]] | None = None,
        setting_rules: Any | None = None,
        prologue_scenario: str | None = None,
        thread_seeds: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate an OriginScreenplay dict.

        Args:
            background_id: Background identifier (e.g. "smuggler").
            species_id: Species identifier (e.g. "twi_lek").
            background_name: Display name (e.g. "Smuggler").
            choice_effects: List of BackgroundChoiceEffect dicts from CYOA.
            setting_rules: Optional SettingRules for universe context.
            prologue_scenario: Seed text from EraBackground.prologue_scenario.
            thread_seeds: Narrative thread seeds from the background.
        Returns:
            OriginScreenplay as a dict (validated via Pydantic).
        """
        from backend.app.world.era_pack_models import SettingRules

        sr: SettingRules = (
            setting_rules if isinstance(setting_rules, SettingRules) else SettingRules()
        )

        bg_display = background_name or background_id.replace("_", " ").title()

        def fallback() -> dict[str, Any]:
            return _build_fallback_origin(
                background_id=background_id,
                species_id=species_id,
                background_name=bg_display,
                prologue_scenario=prologue_scenario,
                setting_name=sr.setting_name,
            )

        # Build compact effects summary
        effects_lines: list[str] = []
        for eff in choice_effects or []:
            if isinstance(eff, dict):
                parts = []
                if eff.get("alignment_nudge"):
                    parts.append(f"alignment={eff['alignment_nudge']}")
                if eff.get("psych_seed"):
                    parts.append(f"psych={eff['psych_seed']}")
                if eff.get("npc_seed"):
                    parts.append(f"npc={eff['npc_seed']}")
                if parts:
                    q = eff.get("question_id", "?")
                    effects_lines.append(f"  {q}: {', '.join(parts)}")
        effects_summary = "\n".join(effects_lines) if effects_lines else "(no effects)"

        threads_hint = ""
        if thread_seeds:
            threads_hint = (
                "Narrative thread seeds (weave these into the origin):\n"
                + "\n".join(f"- {t}" for t in thread_seeds[:5])
            )

        scenario_hint = (
            f"Background scenario seed: {prologue_scenario}" if prologue_scenario else ""
        )

        system = (
            f"You are {sr.biographer_role}, writing a PLAYABLE BACKSTORY for a "
            f"{sr.setting_name} interactive fiction RPG.\n\n"
            "This is an ORIGIN STORY — a short (3-turn) interactive flashback that "
            "lets the player experience a defining moment from their character's past. "
            "Think Dragon Age: Origins or Mass Effect backstory missions.\n\n"
            "Output ONLY valid JSON matching this exact structure:\n"
            "{\n"
            '  "origin_title": "Short evocative chapter title",\n'
            '  "setting_description": "2-3 sentences: where/when this takes place",\n'
            '  "opening_scene": "3-4 sentence atmospheric opening narration",\n'
            '  "dilemma": "1-2 sentences: the moral/tactical dilemma the player faces",\n'
            '  "resolution_hook": "1 sentence: how this connects to the main story",\n'
            '  "npc_cast": [\n'
            '    {"name": "Proper Name", "role": "mentor|rival|victim|authority|companion", '
            '"relationship_to_player": "ally|rival|authority|neutral"}\n'
            "  ],\n"
            '  "tone": "intimate|tense|bittersweet|hopeful",\n'
            f'  "background_id": "{background_id}",\n'
            f'  "species_id": "{species_id}"\n'
            "}\n\n"
            "Rules:\n"
            "- The origin must feel PERSONAL — this is about the character, not the world\n"
            "- 1-3 NPCs in npc_cast, each with proper names fitting the setting\n"
            "- The dilemma must have no clear right answer — it reveals character\n"
            "- opening_scene should immediately immerse the player in the moment\n"
            "- resolution_hook must connect to the main campaign ahead\n"
            f"- Tone and details must fit {sr.setting_name} {sr.setting_genre}\n"
            f"- {scenario_hint}\n"
            f"- {threads_hint}\n"
        )

        user = (
            f"Background: {background_id} ({bg_display})\n"
            f"Species: {species_id}\n"
            f"Character creation choices:\n{effects_summary}\n"
            f"Era/setting: {sr.setting_name}"
        )

        try:
            validated = call_with_json_reliability(
                llm=self._llm,
                role="origin",
                agent_name="OriginScreenplayAgent.generate",
                campaign_id=None,
                system_prompt=system,
                user_prompt=user,
                schema_class=OriginScreenplay,
                fallback_fn=fallback,
            )
            result = (
                validated.model_dump(mode="json")
                if isinstance(validated, OriginScreenplay)
                else validated
            )
            return result
        except Exception as e:
            log_error_with_context(
                error=e,
                node_name="origin",
                campaign_id=None,
                turn_number=None,
                agent_name="OriginScreenplayAgent.generate",
                extra_context={
                    "background_id": background_id,
                    "species_id": species_id,
                },
            )
            logger.warning(
                "OriginScreenplayAgent.generate failed, using fallback: %s", e
            )
            return fallback()
