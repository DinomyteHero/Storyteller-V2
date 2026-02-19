"""EraForgeAgent: LLM-powered era pack auto-generator.

Three-phase pipeline:
1. suggest_periods(setting_prompt) → propose 3-5 time periods for a setting
2. generate_pack(period_metadata) → generate full EraPack JSON → stored in DB
3. refine_canon_characters(canon_chars, background_context) → adjust proximity by narrative geography

Cloud LLM override (recommended for quality):
    STORYTELLER_ERA_FORGE_PROVIDER=anthropic
    STORYTELLER_ERA_FORGE_MODEL=claude-sonnet-4-6
    STORYTELLER_ERA_FORGE_API_KEY=<your-key>
Local fallback: qwen3:8b (generates reasonable but less polished packs).
"""
from __future__ import annotations

import logging
from typing import Any

from backend.app.core.agents.base import AgentLLM
from backend.app.core.json_reliability import call_with_json_reliability
from backend.app.core.error_handling import log_error_with_context

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Deterministic fallbacks
# ---------------------------------------------------------------------------


def _default_periods(setting_prompt: str) -> dict[str, Any]:
    """Deterministic fallback for period discovery when LLM is unavailable."""
    import re
    from backend.app.core.text_utils import normalize_identifier

    # normalize_identifier handles dash→underscore and lowercasing;
    # we also need to collapse spaces and special chars into underscores.
    raw = normalize_identifier(setting_prompt)
    setting_id = re.sub(r"[^a-z0-9_]+", "_", raw).strip("_")
    setting_name = setting_prompt.strip() or "Unknown Setting"

    from backend.app.api.eraforge_models import EraForgeSuggestOutput, EraForgePeriodProposal  # noqa: E402

    return EraForgeSuggestOutput(
        setting_id=setting_id,
        setting_name=setting_name,
        setting_genre="fantasy",
        periods=[
            EraForgePeriodProposal(
                period_id=f"{setting_id}_golden_age",
                display_name="The Golden Age",
                time_period="The early prosperous era",
                summary=f"A time of growth and expansion in {setting_name}. Alliances are forged, cities rise, and heroes emerge from humble beginnings.",
                tone="hopeful, adventurous",
                key_conflicts=["territorial expansion", "emerging threats", "political alliances"],
            ),
            EraForgePeriodProposal(
                period_id=f"{setting_id}_war_era",
                display_name="The Great Conflict",
                time_period="The central war period",
                summary=f"War has engulfed {setting_name}. Factions clash, loyalties are tested, and survival demands difficult choices.",
                tone="gritty, tense, morally grey",
                key_conflicts=["open warfare", "betrayal and espionage", "civilian survival"],
            ),
            EraForgePeriodProposal(
                period_id=f"{setting_id}_aftermath",
                display_name="The Aftermath",
                time_period="The post-conflict reconstruction",
                summary=f"The dust settles across {setting_name}. Power vacuums invite ambitious players, and old wounds fester beneath a fragile peace.",
                tone="political intrigue, rebuilding",
                key_conflicts=["power struggles", "justice vs vengeance", "reconstruction"],
            ),
        ],
    ).model_dump(mode="json")


def _default_pack(
    *,
    setting_id: str,
    setting_name: str,
    setting_genre: str,
    period_id: str,
    display_name: str,
    time_period: str,
    summary: str,
    tone: str,
    key_conflicts: list[str],
) -> dict[str, Any]:
    """Deterministic fallback: minimal but valid EraPack when LLM is unavailable."""
    era_id = f"{setting_id}__{period_id}"
    genre = (setting_genre or "fantasy").strip().lower()

    # Genre-appropriate bypass methods
    if genre in ("science fiction", "sci-fi", "cyberpunk"):
        bypass = ["hack", "stealth", "bribe", "intimidate", "charm"]
    elif genre in ("fantasy", "high fantasy", "dark fantasy"):
        bypass = ["magic", "persuasion", "stealth", "intimidate", "pick_lock"]
    else:
        bypass = ["charm", "stealth", "bribe", "intimidate", "deception"]

    # Genre-appropriate species
    if genre in ("science fiction", "sci-fi"):
        species_list = ["Human", "Android", "Alien"]
    elif genre in ("fantasy", "high fantasy", "dark fantasy"):
        species_list = ["Human", "Elf", "Dwarf"]
    else:
        species_list = ["Human"]

    factions = ["The Loyalists", "The Reformers", "The Outcasts"]

    return {
        "era_id": era_id,
        "schema_version": 1,
        "setting_name": setting_name,
        "metadata": {
            "display_name": display_name,
            "summary": summary,
            "tone": tone,
            "key_conflicts": key_conflicts,
            "source": "eraforge_fallback",
            "setting_genre": setting_genre,
        },
        "setting_rules": {
            "setting_name": setting_name,
            "setting_genre": setting_genre,
            "biographer_role": f"a biographer for a {setting_name} narrative RPG",
            "architect_role": f"the World Architect for a {setting_name} narrative RPG",
            "director_role": f"the Director for an interactive {setting_name} story engine",
            "suggestion_style": f"a {setting_name}-style narrative game",
            "common_species": species_list,
            "example_factions": factions,
            "historical_lore_label": f"established {setting_name} lore",
            "bypass_methods": bypass,
            "fallback_background": f"A wanderer in the world of {setting_name}.",
        },
        "backgrounds": [
            {
                "id": f"bg-{setting_id}-warrior",
                "name": "Warrior",
                "description": f"A trained fighter in {setting_name}, hardened by conflict and duty.",
                "starting_stats": {"Combat": 4, "Stealth": 1, "Charisma": 2, "Tech": 1, "General": 2},
                "questions": [
                    {
                        "id": "q-warrior-origin",
                        "title": "Where did you learn to fight?",
                        "choices": [
                            {
                                "label": "Military Academy",
                                "concept": "Trained in formal tactics and discipline.",
                                "tone": "DISCIPLINED",
                                "effects": {"stat_bonus": {"Combat": 1}, "faction_hint": factions[0]},
                            },
                            {
                                "label": "The Streets",
                                "concept": "Survival was the best teacher.",
                                "tone": "GRITTY",
                                "effects": {"stat_bonus": {"Stealth": 1}, "faction_hint": factions[2]},
                            },
                        ],
                    },
                ],
            },
            {
                "id": f"bg-{setting_id}-scholar",
                "name": "Scholar",
                "description": f"A seeker of knowledge in {setting_name}, driven by curiosity and intellect.",
                "starting_stats": {"Combat": 1, "Stealth": 1, "Charisma": 3, "Tech": 3, "General": 2},
                "questions": [
                    {
                        "id": "q-scholar-specialty",
                        "title": "What is your area of expertise?",
                        "choices": [
                            {
                                "label": "History and Lore",
                                "concept": "The past holds the key to the future.",
                                "tone": "CONTEMPLATIVE",
                                "effects": {"stat_bonus": {"General": 1}, "thread_seed": "ancient_secrets"},
                            },
                            {
                                "label": "Political Strategy",
                                "concept": "Knowledge is power — especially in the right hands.",
                                "tone": "CALCULATING",
                                "effects": {"stat_bonus": {"Charisma": 1}, "faction_hint": factions[1]},
                            },
                        ],
                    },
                ],
            },
        ],
        "species": [
            {
                "id": f"sp-{species_list[0].lower().replace(' ', '_')}",
                "name": species_list[0],
                "description": f"The most common species in {setting_name}. Versatile and adaptable.",
                "stat_bonus": {},
                "typical_traits": ["adaptable", "ambitious"],
                "narrative_hooks": [f"Most of {setting_name}'s history was shaped by their hands."],
            },
            *(
                [
                    {
                        "id": f"sp-{sp.lower().replace(' ', '_')}",
                        "name": sp,
                        "description": f"A notable species in {setting_name}.",
                        "stat_bonus": {},
                        "typical_traits": ["distinctive"],
                        "narrative_hooks": [f"The {sp} have their own role in {setting_name}."],
                    }
                    for sp in species_list[1:]
                ]
            ),
        ],
        "canon_characters": [],
        "legends_timeline" if genre in ("science fiction", "sci-fi", "science fantasy") else "setting_timeline": {
            "canonical_year": time_period,
            "notable_events": [
                {"year": time_period, "event": summary},
            ],
        },
        "start_location_pool": ["loc-town-center", "loc-tavern"],
        "locations": [],
        "factions": [],
        "companions": [],
        "quests": [],
    }


# ---------------------------------------------------------------------------
# EraForgeAgent
# ---------------------------------------------------------------------------


class EraForgeAgent:
    """Generates era packs from scratch via LLM.

    Three-phase pipeline:
    1. suggest_periods() — propose time periods for a user-described setting
    2. generate_pack() — generate a full EraPack-compatible JSON structure
    3. refine_canon_characters() — adjust canon character proximity after background selection
    """

    def __init__(self, llm: AgentLLM | None = None) -> None:
        self._llm = llm

    # -------------------------------------------------------------------
    # Phase 1: Period Discovery
    # -------------------------------------------------------------------

    def suggest_periods(self, setting_prompt: str) -> dict[str, Any]:
        """Propose 3-5 time periods for the given setting. Returns EraForgeSuggestOutput dict."""
        from backend.app.api.eraforge_models import EraForgeSuggestOutput  # noqa: E402

        def fallback() -> dict[str, Any]:
            return _default_periods(setting_prompt)

        system = """You are a world-building expert for narrative RPGs. Given a fictional or historical setting, propose 3-5 time periods that would make compelling RPG campaigns.

Each period should represent a distinct narrative era with unique conflicts, tone, and story opportunities. Think of what makes each period *playable* — political intrigue, warfare, exploration, survival, moral dilemmas.

OUTPUT RULES:
- Output ONLY valid JSON matching the schema below. No markdown, no explanation.
- period_id must be a lowercase, underscore-separated identifier (e.g. "war_of_five_kings").
- Each period needs a compelling 2-3 sentence summary.
- Tone should be 2-4 descriptive words (e.g. "political intrigue, brutal warfare").
- key_conflicts should be 2-4 short phrases describing the main tensions.

JSON SCHEMA:
{
  "setting_id": "string — normalized identifier (e.g. 'game_of_thrones')",
  "setting_name": "string — display name (e.g. 'Game of Thrones')",
  "setting_genre": "string — genre (e.g. 'fantasy', 'science fiction', 'historical')",
  "periods": [
    {
      "period_id": "string — normalized identifier",
      "display_name": "string — human-readable name",
      "time_period": "string — date/era label",
      "summary": "string — 2-3 sentence summary",
      "tone": "string — 2-4 descriptive words",
      "key_conflicts": ["string", "string"]
    }
  ]
}"""

        user = (
            f"Setting: {setting_prompt}\n\n"
            "Propose 3-5 compelling time periods for this setting that would work as RPG campaign starting points. "
            "Each period should have distinct conflicts, tone, and story hooks that make it unique and playable."
        )

        try:
            validated = call_with_json_reliability(
                llm=self._llm,
                role="era_forge",
                agent_name="EraForgeAgent.suggest_periods",
                campaign_id=None,
                system_prompt=system,
                user_prompt=user,
                schema_class=EraForgeSuggestOutput,
                fallback_fn=fallback,
            )
            if isinstance(validated, EraForgeSuggestOutput):
                return validated.model_dump(mode="json")
            return validated
        except Exception as e:
            log_error_with_context(
                error=e,
                node_name="era_forge",
                campaign_id=None,
                turn_number=None,
                agent_name="EraForgeAgent.suggest_periods",
                extra_context={"setting_prompt": setting_prompt[:200]},
            )
            logger.warning("EraForgeAgent.suggest_periods failed; using deterministic fallback.")
            return fallback()

    # -------------------------------------------------------------------
    # Phase 2: Pack Generation
    # -------------------------------------------------------------------

    def generate_pack(
        self,
        *,
        setting_id: str,
        setting_name: str,
        setting_genre: str = "fantasy",
        period_id: str,
        display_name: str,
        time_period: str,
        summary: str,
        tone: str = "",
        key_conflicts: list[str] | None = None,
        source_prompt: str = "",
    ) -> dict[str, Any]:
        """Generate a full EraPack-compatible JSON structure. Returns a dict suitable for EraPack.model_validate()."""

        conflicts = key_conflicts or []

        def fallback() -> dict[str, Any]:
            return _default_pack(
                setting_id=setting_id,
                setting_name=setting_name,
                setting_genre=setting_genre,
                period_id=period_id,
                display_name=display_name,
                time_period=time_period,
                summary=summary,
                tone=tone,
                key_conflicts=conflicts,
            )

        system = f"""You are the Era Pack Generator for a multi-universe narrative RPG engine.
Your output creates the foundational character-creation content for a campaign set in {setting_name} during the "{display_name}" period.

Setting: {setting_name} ({setting_genre})
Period: {display_name}
Time: {time_period}
Tone: {tone or 'unspecified'}
Key Conflicts: {'; '.join(conflicts) if conflicts else 'unspecified'}
Summary: {summary}

CRITICAL RULES:
- All content MUST be appropriate for {setting_name}. No cross-setting contamination.
- Stat system uses exactly these 5 stats: Combat, Stealth, Charisma, Tech, General (each 0-10).
- bypass_methods must be setting-appropriate (no "force" outside Star Wars, no "magic" in sci-fi settings, etc.).
- Backgrounds must have meaningful CYOA question trees with effects (stat_bonus, faction_hint, location_hint, thread_seed).
- Canon characters should be well-known figures from the setting with appropriate proximity tiers.
- Species should reflect the setting (fantasy: races; sci-fi: species; historical: ethnicities/cultures).

OUTPUT RULES:
- Output ONLY valid JSON matching the schema below. No markdown, no explanation.
- Backgrounds: 4-6 distinct character archetypes with 2-3 CYOA questions each.
- Species: 3-7 playable species/races.
- Canon characters: 5-10 recognizable figures with proximity and location assignments.
- Setting rules must be complete and universe-appropriate.

JSON SCHEMA:
{{
  "era_id": "string — format: {{setting_id}}__{{period_id}}",
  "schema_version": 1,
  "setting_name": "string",
  "metadata": {{
    "display_name": "string",
    "summary": "string",
    "tone": "string",
    "key_conflicts": ["string"],
    "source": "eraforge_generated",
    "setting_genre": "string"
  }},
  "setting_rules": {{
    "setting_name": "string — display name of the setting",
    "setting_genre": "string — genre descriptor",
    "biographer_role": "string — e.g. 'a biographer for a Game of Thrones narrative RPG'",
    "architect_role": "string — e.g. 'the World Architect for a Game of Thrones narrative RPG'",
    "director_role": "string — e.g. 'the Director for an interactive Game of Thrones story engine'",
    "suggestion_style": "string — e.g. 'a Game of Thrones-style narrative game'",
    "common_species": ["string — 3-7 species/races"],
    "example_factions": ["string — 3-5 major factions"],
    "historical_lore_label": "string",
    "bypass_methods": ["string — setting-appropriate methods from: violence, sneak, stealth, climb, navigate, bribe, charm, intimidate, deception, credential, hack, slice, disable, logic_puzzle, magic, persuasion, arcane_lock, pick_lock, netrun, cyberware"],
    "fallback_background": "string"
  }},
  "backgrounds": [
    {{
      "id": "string — e.g. bg-got-knight",
      "name": "string",
      "description": "string — 1-2 sentences",
      "starting_stats": {{"Combat": int, "Stealth": int, "Charisma": int, "Tech": int, "General": int}},
      "questions": [
        {{
          "id": "string",
          "title": "string — the question",
          "choices": [
            {{
              "label": "string — short label",
              "concept": "string — 1 sentence elaboration",
              "tone": "string — e.g. HEROIC, GRITTY, CUNNING",
              "effects": {{
                "stat_bonus": {{"stat_name": int}},
                "faction_hint": "string (optional)",
                "location_hint": "string (optional)",
                "thread_seed": "string (optional)"
              }}
            }}
          ]
        }}
      ]
    }}
  ],
  "species": [
    {{
      "id": "string",
      "name": "string",
      "description": "string",
      "stat_bonus": {{}},
      "typical_traits": ["string"],
      "narrative_hooks": ["string"]
    }}
  ],
  "canon_characters": [
    {{
      "name": "string — recognizable character name",
      "proximity": "string — cameo|interaction|extended",
      "locations": ["string — location ids or region names where they can appear"],
      "exclusion_events": ["string — events during which they are unavailable (optional)"],
      "role": "string (optional) — e.g. king, warrior, spy",
      "faction_id": "string (optional)",
      "voice_tags": ["string (optional)"],
      "traits": ["string (optional)"],
      "motivation": "string (optional)"
    }}
  ],
  "setting_timeline": {{
    "canonical_year": "string",
    "notable_events": [
      {{"year": "string", "event": "string"}}
    ]
  }},
  "start_location_pool": ["string — 2-4 generic location type ids"],
  "locations": [],
  "factions": [],
  "companions": [],
  "quests": []
}}"""

        user = (
            f"Generate the era pack for {setting_name}: {display_name} ({time_period}).\n"
            f"Summary: {summary}\n"
            f"Tone: {tone}\n"
            f"Key conflicts: {'; '.join(conflicts)}\n\n"
            "Create rich, setting-authentic backgrounds with meaningful CYOA trees, "
            "appropriate species, and recognizable canon characters with correct proximity tiers. "
            "Make every name, faction, and detail specific to this setting and period."
        )

        def validator_fn(data: Any) -> tuple[bool, str]:
            """Validate that the generated pack has essential content."""
            d = data if isinstance(data, dict) else (data.model_dump(mode="json") if hasattr(data, "model_dump") else {})
            bgs = d.get("backgrounds") or []
            if len(bgs) < 2:
                return False, f"Need at least 2 backgrounds, got {len(bgs)}"
            sps = d.get("species") or []
            if len(sps) < 1:
                return False, f"Need at least 1 species, got {len(sps)}"
            sr = d.get("setting_rules")
            if not sr or not isinstance(sr, dict):
                return False, "Missing setting_rules"
            return True, ""

        try:
            validated = call_with_json_reliability(
                llm=self._llm,
                role="era_forge",
                agent_name="EraForgeAgent.generate_pack",
                campaign_id=None,
                system_prompt=system,
                user_prompt=user,
                validator_fn=validator_fn,
                fallback_fn=fallback,
            )
            data = validated if isinstance(validated, dict) else (validated.model_dump(mode="json") if hasattr(validated, "model_dump") else validated)

            # Lenient EraPack validation — log warnings but don't crash
            try:
                from backend.app.world.era_pack_models import EraPack
                EraPack.model_validate(data)
                logger.info("EraForgeAgent.generate_pack: EraPack validation passed.")
            except Exception as ve:
                logger.warning("EraForgeAgent.generate_pack: EraPack validation warning (lenient): %s", ve)

            return data
        except Exception as e:
            log_error_with_context(
                error=e,
                node_name="era_forge",
                campaign_id=None,
                turn_number=None,
                agent_name="EraForgeAgent.generate_pack",
                extra_context={
                    "setting_id": setting_id,
                    "period_id": period_id,
                },
            )
            logger.warning("EraForgeAgent.generate_pack failed; using deterministic fallback.")
            return fallback()

    # -------------------------------------------------------------------
    # Phase 3: Canon Character Refinement
    # -------------------------------------------------------------------

    def refine_canon_characters(
        self,
        canon_characters: list[dict[str, Any]],
        *,
        background_id: str,
        background_name: str = "",
        background_description: str = "",
        location_hints: list[str] | None = None,
        faction_hints: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Adjust canon character proximity based on the player's chosen background.

        Returns the refined canon_characters list (same format, potentially different proximity values).
        Fallback: return original characters unchanged.
        """
        if not canon_characters:
            return []

        loc_hints = location_hints or []
        fac_hints = faction_hints or []

        def fallback() -> list[dict[str, Any]]:
            return list(canon_characters)

        # Build compact character summary for the prompt
        char_summaries = []
        for cc in canon_characters:
            name = cc.get("name", "Unknown")
            prox = cc.get("proximity", "cameo")
            locs = cc.get("locations", [])
            role = cc.get("role", "")
            faction = cc.get("faction_id", "")
            char_summaries.append(
                f"  - {name}: proximity={prox}, locations={locs}, role={role}, faction={faction}"
            )
        chars_text = "\n".join(char_summaries)

        system = """You are a narrative proximity analyst for a RPG story engine.

Given canon characters and a player's chosen background (which implies geographic position and faction alignment), adjust each character's proximity tier based on narrative realism.

Proximity tiers:
- "cameo": visible flavor only, player sees them from afar
- "interaction": brief direct interaction allowed, fate canon-protected
- "extended": sustained multi-turn scene partner (close allies, mentors, rivals)
- "exclusion": player is redirected away (character is elsewhere or in conflict scenes)

RULES:
- Characters geographically far from the player's starting area should be "cameo" or "exclusion".
- Characters in the same faction or location as the player can be "interaction" or "extended".
- Major antagonists opposing the player's faction should generally be "cameo" (seen but not directly engaged early).
- Mentors/allies within the player's faction can be elevated to "extended".
- Only change proximity if the background genuinely affects narrative distance. Keep unchanged otherwise.

OUTPUT RULES:
- Output ONLY a valid JSON array of objects. No markdown, no explanation.
- Each object must have at minimum: "name", "proximity", "locations".
- Preserve all other fields from the original character entries."""

        user = (
            f"Player background: {background_name or background_id}\n"
            f"Background description: {background_description}\n"
            f"Location hints: {', '.join(loc_hints) if loc_hints else 'none'}\n"
            f"Faction hints: {', '.join(fac_hints) if fac_hints else 'none'}\n\n"
            f"Current canon characters:\n{chars_text}\n\n"
            "Adjust proximity tiers based on this background's narrative geography and faction alignment. "
            "Return the full list with any proximity changes applied."
        )

        try:
            if self._llm is None:
                logger.info("EraForgeAgent.refine_canon_characters: No LLM available, returning original characters.")
                return fallback()

            raw = self._llm.complete(system, user, json_mode=True, raw_json_mode=True)
            from backend.app.core.agents.base import ensure_json
            import json

            js = ensure_json(raw)
            if not js:
                logger.warning("EraForgeAgent.refine_canon_characters: No valid JSON in response.")
                return fallback()

            parsed = json.loads(js)

            # Handle both list and dict-with-list responses
            if isinstance(parsed, dict):
                parsed = parsed.get("canon_characters") or parsed.get("characters") or []
            if not isinstance(parsed, list):
                logger.warning("EraForgeAgent.refine_canon_characters: Response not a list.")
                return fallback()

            # Validate each entry has required fields
            refined = []
            for item in parsed:
                if not isinstance(item, dict) or "name" not in item:
                    continue
                # Ensure proximity is valid
                prox = str(item.get("proximity", "cameo")).strip().lower()
                if prox not in ("cameo", "interaction", "extended", "exclusion"):
                    prox = "cameo"
                item["proximity"] = prox
                refined.append(item)

            if not refined:
                logger.warning("EraForgeAgent.refine_canon_characters: Empty refined list, using fallback.")
                return fallback()

            logger.info(
                "EraForgeAgent.refine_canon_characters: refined %d characters.",
                len(refined),
            )
            return refined

        except Exception as e:
            log_error_with_context(
                error=e,
                node_name="era_forge",
                campaign_id=None,
                turn_number=None,
                agent_name="EraForgeAgent.refine_canon_characters",
                extra_context={"background_id": background_id},
            )
            logger.warning("EraForgeAgent.refine_canon_characters failed; returning original characters.")
            return fallback()
