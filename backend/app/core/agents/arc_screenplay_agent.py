"""ArcScreenplayAgent: generates a per-arc narrative blueprint (Phase 2.1).

Uses the era pack + player concept + origin_context to produce an ArcScreenplay
that the Director and ArcWeaver use as a loose structural guide. Player choices
always take precedence over the screenplay.

Pattern mirrors CampaignArchitect: AgentLLM("arc_screenplay") +
call_with_json_reliability() + deterministic fallback.

Enabled when ENABLE_CLOUD_BLUEPRINT=true (default: off for deterministic play).
"""
from __future__ import annotations

import logging
import os
from typing import Any

from backend.app.core.agents.base import AgentLLM
from backend.app.core.json_reliability import call_with_json_reliability
from backend.app.core.error_handling import log_error_with_context
from shared.schemas import ArcScreenplay, ArcAct

logger = logging.getLogger(__name__)

ENABLE_CLOUD_BLUEPRINT = os.environ.get("ENABLE_CLOUD_BLUEPRINT", "false").lower() in ("true", "1", "yes")


def _build_fallback_screenplay(
    background_id: str | None,
    player_concept: str,
    era_pack_title: str,
    setting_name: str,
    origin_context: dict[str, Any],
) -> dict[str, Any]:
    """Deterministic fallback ArcScreenplay — used when LLM unavailable or disabled."""
    bg = background_id or "adventurer"
    tone_map: dict[str, str] = {
        "smuggler": "gritty",
        "bounty_hunter": "noir",
        "force_sensitive_exile": "melancholic",
        "imperial_officer": "tense",
        "rebel_operative": "heroic",
        "imperial_defector": "paranoid",
    }
    tone = tone_map.get((bg or "").lower().replace("-", "_"), "gritty")

    return {
        "title": f"Arc 1: {era_pack_title or 'New Horizons'}",
        "tone": tone,
        "opening_crawl": (
            f"In the {setting_name}, destinies are forged in shadow and sacrifice. "
            f"A {bg} must navigate a galaxy that offers no easy answers, "
            "where every choice echoes across the stars."
        ),
        "act_structure": {
            "act_1": {
                "summary": "Establish the world and the player's place in it. "
                           "Introduce the central conflict and key players.",
                "key_scenes": [
                    "Inciting incident draws the character into larger events",
                    "First encounter with a key ally or antagonist",
                ],
                "must_include_npcs": [],
                "must_include_locations": [],
            },
            "act_2": {
                "summary": "Complications mount. Alliances are tested. "
                           "The cost of involvement becomes clear.",
                "key_scenes": [
                    "Midpoint reversal: a plan fails or a betrayal occurs",
                    "Character must make a difficult moral choice",
                ],
                "must_include_npcs": [],
                "must_include_locations": [],
            },
            "act_3": {
                "summary": "The climax approaches. Consequences of earlier choices cascade. "
                           "Resolution leaves threads for the next arc.",
                "key_scenes": [
                    "Final confrontation with the arc's central conflict",
                    "Denouement: what has changed and what remains unresolved",
                ],
                "must_include_npcs": [],
                "must_include_locations": [],
            },
        },
        "cast": [],
        "locations": [],
        "quests": [],
        "moments": [],
        "climax_question": f"What price will the {bg} pay to achieve their goal?",
        "resolution_hooks": [
            "A loose thread connects to a larger conspiracy",
            "An NPC fate remains uncertain",
        ],
    }


class ArcScreenplayAgent:
    """Generates an ArcScreenplay from era pack + player concept.

    Only active when ``ENABLE_CLOUD_BLUEPRINT=true``. Otherwise falls back
    to a deterministic screenplay skeleton that the Director can build on.
    """

    def __init__(self, llm: AgentLLM | None = None) -> None:
        self._llm = llm

    def generate(
        self,
        era_pack: Any | None = None,
        player_concept: str = "",
        background_id: str | None = None,
        origin_context: dict[str, Any] | None = None,
        setting_rules: Any | None = None,
    ) -> dict[str, Any]:
        """Generate an ArcScreenplay dict.

        Args:
            era_pack: EraPack instance from the content repository.
            player_concept: The player concept string (from BiographerAgent input).
            background_id: Background ID selected during character creation.
            origin_context: Origin context from prologue completion (or None).
            setting_rules: Optional SettingRules instance.
        Returns:
            ArcScreenplay as a dict (validated via Pydantic).
        """
        from backend.app.world.era_pack_models import SettingRules
        sr: SettingRules = (
            setting_rules if isinstance(setting_rules, SettingRules)
            else (era_pack.setting_rules if era_pack and hasattr(era_pack, "setting_rules") else SettingRules())
        )

        # Era pack metadata
        metadata = era_pack.metadata if era_pack and hasattr(era_pack, "metadata") else {}
        if isinstance(metadata, dict):
            era_title = metadata.get("display_name", "")
            time_period = metadata.get("time_period", "")
        else:
            era_title = getattr(metadata, "display_name", "") or ""
            time_period = getattr(metadata, "time_period", "") or ""

        origin = origin_context or {}

        def fallback() -> dict[str, Any]:
            return _build_fallback_screenplay(
                background_id=background_id or origin.get("background_id"),
                player_concept=player_concept,
                era_pack_title=era_title,
                setting_name=sr.setting_name,
                origin_context=origin,
            )

        if not ENABLE_CLOUD_BLUEPRINT:
            return fallback()

        # Sample quest/location IDs for grounding
        locs = [
            loc.id for loc in (getattr(era_pack, "locations", None) or [])[:5]
        ] if era_pack else []
        quests = [
            q.id for q in (getattr(era_pack, "quests", None) or [])[:5]
        ] if era_pack else []
        moments_list = [
            m.id for m in (getattr(era_pack, "moments", None) or [])[:5]
        ] if era_pack else []

        prologue_summary = ""
        if origin:
            prologue_summary = (
                f"Prologue title: {origin.get('prologue_title', '')}\n"
                f"Inciting moment: {origin.get('inciting_moment', '')}\n"
                f"Tone: {origin.get('tone', '')}\n"
                f"NPCs encountered: {', '.join(origin.get('npc_names_encountered', []))}"
            )

        system = (
            f"You are {sr.architect_role}. Generate a 3-act arc screenplay for a "
            f"{sr.setting_genre} narrative RPG campaign.\n"
            "Output ONLY valid JSON matching:\n"
            "{\n"
            '  "title": "Arc title",\n'
            '  "tone": "gritty|heroic|noir|political|etc",\n'
            '  "opening_crawl": "2-4 sentence Star-Wars-style opening text",\n'
            '  "act_structure": {\n'
            '    "act_1": {"summary":"","key_scenes":[],"must_include_npcs":[],"must_include_locations":[]},\n'
            '    "act_2": {...},\n'
            '    "act_3": {...}\n'
            '  },\n'
            '  "cast": [{"name":"","role":"","motivation":""}],\n'
            f'  "locations": {locs[:3] or []},\n'
            f'  "quests": {quests[:3] or []},\n'
            f'  "moments": {moments_list[:3] or []},\n'
            '  "climax_question": "The central dramatic question",\n'
            '  "resolution_hooks": ["seed 1", "seed 2"]\n'
            "}\n"
            "Rules:\n"
            "- 2-4 cast members, each with distinct motivation\n"
            "- opening_crawl must establish stakes immediately\n"
            f"- Setting: {sr.setting_name} ({time_period}), genre: {sr.setting_genre}\n"
        )
        user = (
            f"Background: {background_id or 'unknown'}\n"
            f"Player concept: {player_concept or '(none)'}\n"
            f"Prologue context:\n{prologue_summary or '(no prologue)'}"
        )

        try:
            validated = call_with_json_reliability(
                llm=self._llm,
                role="arc_screenplay",
                agent_name="ArcScreenplayAgent.generate",
                campaign_id=None,
                system_prompt=system,
                user_prompt=user,
                schema_class=ArcScreenplay,
                fallback_fn=fallback,
            )
            return (
                validated.model_dump(mode="json")
                if isinstance(validated, ArcScreenplay)
                else validated
            )
        except Exception as e:
            log_error_with_context(
                error=e,
                node_name="arc_screenplay",
                campaign_id=None,
                turn_number=None,
                agent_name="ArcScreenplayAgent.generate",
                extra_context={"background_id": background_id, "era_title": era_title},
            )
            logger.warning("ArcScreenplayAgent.generate failed, using fallback: %s", e)
            return fallback()
