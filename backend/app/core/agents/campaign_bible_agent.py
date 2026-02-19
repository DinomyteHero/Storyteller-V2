"""CampaignBibleAgent: generates the campaign screenplay bible at setup time.

Runs ONCE at campaign creation. Produces CampaignBibleOutput — a bespoke screenplay
bible containing locations, NPC cast, companions, factions, and quest arcs tailored to
the player's concept and chosen Legends timeline date.

Replaces the static era pack YAML content (companions.yaml, npcs.yaml, factions.yaml,
locations.yaml, quests.yaml, etc.) that had to be hand-authored for every era.

Cloud LLM override (recommended for quality):
    STORYTELLER_BIBLE_PROVIDER=anthropic
    STORYTELLER_BIBLE_MODEL=claude-opus-4-6
    STORYTELLER_BIBLE_API_KEY=<your-key>
Local fallback: qwen3:8b (generates a reasonable but less polished bible).
"""
from __future__ import annotations

import logging
from typing import Any

from backend.app.core.agents.base import AgentLLM
from backend.app.core.json_reliability import call_with_json_reliability
from backend.app.core.error_handling import log_error_with_context
from shared.schemas import (
    CampaignBibleOutput,
    CampaignBibleLocation,
    CampaignBibleNPC,
    CampaignBibleCompanion,
    CampaignBibleFaction,
    CampaignBibleArc,
)

logger = logging.getLogger(__name__)

# Canonical starting location archetypes — always available as fallback starting points.
# The bible generates rich named versions of these same IDs.
CANONICAL_START_LOCATIONS = [
    "loc-cantina",
    "loc-docking-bay",
    "loc-safe-house",
    "loc-marketplace",
]


def _default_bible(
    *,
    time_period: str | None,
    player_concept: str,
    starting_location: str,
    setting_rules: Any | None,
) -> dict[str, Any]:
    """Deterministic fallback bible when LLM is unavailable."""
    from backend.app.world.era_pack_models import SettingRules

    sr: SettingRules = (
        setting_rules if isinstance(setting_rules, SettingRules) else SettingRules()
    )
    species_list = sr.common_species or ["Human", "Twi'lek", "Rodian"]
    factions = sr.example_factions or ["Rebellion", "Empire", "Criminal Syndicate"]

    era_label = (time_period or "unknown era").upper()

    return CampaignBibleOutput(
        campaign_title=f"Shadows of the {era_label.replace('_', ' ').title()}",
        campaign_theme="gritty survival",
        galactic_situation=(
            f"The galaxy teeters on a knife's edge during the {era_label} era. "
            "Powerful factions compete for dominance while ordinary beings struggle to survive. "
            "Opportunity and danger walk the same streets."
        ),
        opening_crawl=(
            f"In the dark corners of the galaxy, the {era_label} era grinds on. "
            "Those who wish to survive must be clever, resourceful, and willing to take risks. "
            "Our story begins in the shadows — where fortunes are made and lives are lost. "
            "The question is not whether you will be tested, but how you will answer."
        ),
        locations=[
            CampaignBibleLocation(
                id="loc-cantina",
                name="The Broken Coil Cantina",
                planet="Nar Shaddaa",
                description="A dimly lit den of dubious patrons where information flows as freely as cheap spirits.",
                services=["cantina", "intel"],
                threat_level="low",
                faction_control=factions[2] if len(factions) > 2 else "",
            ),
            CampaignBibleLocation(
                id="loc-docking-bay",
                name="Docking Bay 94",
                planet="Nar Shaddaa",
                description="A cavernous bay thick with exhaust fumes, where ships of every description wait — and so do their owners.",
                services=["transport"],
                threat_level="moderate",
                faction_control="",
            ),
            CampaignBibleLocation(
                id="loc-safe-house",
                name="The Rat's Nest",
                planet="Nar Shaddaa",
                description="A cramped but secure hideout above a noodle shop, used by those who need to disappear.",
                services=["safehouse"],
                threat_level="low",
                faction_control="",
            ),
            CampaignBibleLocation(
                id="loc-marketplace",
                name="The Corellian Bazaar",
                planet="Nar Shaddaa",
                description="A sprawling open-air market where anything can be bought — for the right price.",
                services=["market"],
                threat_level="low",
                faction_control=factions[2] if len(factions) > 2 else "",
            ),
            CampaignBibleLocation(
                id="loc-imperial-outpost",
                name="Imperial Garrison Post",
                planet="Nar Shaddaa",
                description="A fortified checkpoint manned by Imperial troops, a grim reminder of who controls the sector.",
                services=[],
                threat_level="high",
                faction_control=factions[1] if len(factions) > 1 else "Empire",
            ),
        ],
        npc_cast=[
            CampaignBibleNPC(
                id="npc-001",
                name="Draven Koss",
                role="Villain",
                species=species_list[0] if species_list else "Human",
                faction=factions[1] if len(factions) > 1 else "",
                personality="Cold and methodical, Draven rules through fear and leverage. He never raises his voice.",
                secret_agenda="Seeks to consolidate control over the sector's black market supply chains.",
                voice_style="clipped, precise, no wasted words",
            ),
            CampaignBibleNPC(
                id="npc-002",
                name="Vekk Tano",
                role="Rival",
                species=species_list[1] if len(species_list) > 1 else "Human",
                faction="",
                personality="Ambitious and relentless, Vekk sees you as an obstacle to be outmaneuvered.",
                secret_agenda="Wants the same prize you do and will cut corners to get there first.",
                voice_style="fast-talking, competitive, always measuring you up",
            ),
            CampaignBibleNPC(
                id="npc-003",
                name="Nura Besh",
                role="Merchant",
                species=species_list[1] if len(species_list) > 1 else "Human",
                faction="",
                personality="Warm on the surface, calculating underneath. She always knows the value of what she has.",
                secret_agenda="Funnels goods through underground networks while maintaining a legitimate front.",
                voice_style="honeyed, business-casual, always angling for a deal",
            ),
            CampaignBibleNPC(
                id="npc-004",
                name="Gorrak Mun",
                role="Merchant",
                species=species_list[2] if len(species_list) > 2 else "Human",
                faction="",
                personality="Gruff and grudging, but fair. Holds grudges for decades.",
                secret_agenda="Sitting on information about Draven Koss that he hasn't decided whether to sell.",
                voice_style="grumbling, clipped, distrusts everyone equally",
            ),
            CampaignBibleNPC(
                id="npc-005",
                name="Whisper",
                role="Informant",
                species="Bothan",
                faction="",
                personality="Speaks quietly and only when paid. Knows something about everyone in this sector.",
                secret_agenda="Sells the same intel to multiple buyers, betting no one compares notes.",
                voice_style="murmuring, conspiratorial, eyes always scanning the room",
            ),
            CampaignBibleNPC(
                id="npc-006",
                name="Zeel Kaat",
                role="Informant",
                species="Devaronian",
                faction="",
                personality="Charming liar, professional fence-sitter. Has worked for everyone at some point.",
                secret_agenda="Playing multiple factions against each other for maximum profit.",
                voice_style="smooth, self-deprecating humor, never fully commits to anything",
            ),
            CampaignBibleNPC(
                id="npc-007",
                name="TK-4471",
                role="Guard",
                species="Human",
                faction=factions[1] if len(factions) > 1 else "Empire",
                personality="Bored and underpaid. Will look the other way for the right sum.",
                secret_agenda="Planning to desert and needs enough credits to disappear.",
                voice_style="flat, bureaucratic, sighs a lot",
            ),
            CampaignBibleNPC(
                id="npc-008",
                name="Hera Solus",
                role="Local",
                species="Mirialan",
                faction="",
                personality="Keeps her head down and her ears open. Has lived here long enough to know everyone's business.",
                secret_agenda="Sheltering someone the authorities are looking for.",
                voice_style="cautious, observant, reveals things sideways",
            ),
            CampaignBibleNPC(
                id="npc-009",
                name="Renn Voss",
                role="Pilot",
                species="Human",
                faction="",
                personality="Quick hands, quicker deals. Renn can get anyone anywhere — for a price.",
                secret_agenda="Owes a dangerous debt to a crime lord and is running out of time.",
                voice_style="nervous energy, talks too fast when stressed",
            ),
            CampaignBibleNPC(
                id="npc-010",
                name="Grumthar",
                role="Barkeep",
                species="Ithorian",
                faction="",
                personality="Placid and patient, Grumthar has heard everything and forgotten nothing.",
                secret_agenda="Passes choice intel to whoever keeps him and his family safe.",
                voice_style="slow, deliberate, translated through a vocalizer",
            ),
        ],
        companions=[
            CampaignBibleCompanion(
                id="comp-001",
                name="Sera Dask",
                species="Human",
                role="Soldier",
                motivation="Looking for purpose after leaving a cause she no longer believes in.",
                personality="Blunt and reliable. She says what she means and does what she says.",
                recruitment_hook="She's in the cantina, nursing a drink and a grudge. She'll join anyone heading toward trouble.",
                voice_style="direct, dry humor, soldier's pragmatism",
            ),
            CampaignBibleCompanion(
                id="comp-002",
                name="Pix",
                species="Jawa",
                role="Mechanic",
                motivation="Fascinated by technology and the stories machines carry.",
                personality="Excitable and unpredictable, but gifted with anything mechanical.",
                recruitment_hook="Found tinkering with a broken speeder behind the docking bay. Will work for spare parts.",
                voice_style="rapid excited chirping (translated), enthusiasm that outpaces comprehension",
            ),
            CampaignBibleCompanion(
                id="comp-003",
                name="Sarik Vey",
                species="Chiss",
                role="Scout",
                motivation="Gathering intelligence on a faction that cost her people something irreplaceable.",
                personality="Composed and analytical. Offers solutions, not sympathy.",
                recruitment_hook="She approaches you — she's been watching and she thinks you can help her.",
                voice_style="precise, formal, asks clarifying questions before acting",
            ),
            CampaignBibleCompanion(
                id="comp-004",
                name="Brak",
                species="Wookiee",
                role="Guardian",
                motivation="Protecting a debt of honor owed to someone you remind them of.",
                personality="Fierce in a fight, gentle with the vulnerable. Strong opinions expressed through roars.",
                recruitment_hook="Steps in during a confrontation that was about to go badly. Hard to say no after that.",
                voice_style="expressive roars and gestures (no translation needed to understand the feelings)",
            ),
        ],
        active_factions=[
            CampaignBibleFaction(
                name=factions[0] if factions else "The Alliance",
                location="loc-safe-house",
                current_goal="Establish a new network in this sector without drawing Imperial attention.",
                resources=4,
                is_hostile=False,
            ),
            CampaignBibleFaction(
                name=factions[1] if len(factions) > 1 else "The Empire",
                location="loc-imperial-outpost",
                current_goal="Tighten surveillance following recent disruptions to supply lines.",
                resources=9,
                is_hostile=True,
            ),
            CampaignBibleFaction(
                name=factions[2] if len(factions) > 2 else "The Syndicate",
                location="loc-docking-bay",
                current_goal="Consolidate control over the docking bay traffic and the smuggling routes beyond.",
                resources=6,
                is_hostile=False,
            ),
        ],
        quest_arcs=[
            CampaignBibleArc(
                id="arc-001",
                title="The Hidden Price",
                hook="A simple job turns out to be anything but — someone powerful is using you as a pawn.",
                stakes="If you don't unravel the deception, you'll take the fall for something you didn't do.",
                resolution_paths=[
                    "Expose the true culprit by collecting enough evidence to flip the situation.",
                    "Strike a deal with the faction using you — become a real asset instead of a disposable one.",
                    "Burn it all down and disappear before the consequences catch up.",
                ],
            ),
            CampaignBibleArc(
                id="arc-002",
                title="Old Debts",
                hook="Someone from your past resurfaces — and they're not happy.",
                stakes="Your history is someone else's leverage. Either settle it or it will be used against you.",
                resolution_paths=[
                    "Face the past directly and deal with what you owe.",
                    "Find a way to neutralize the threat before it escalates.",
                    "Recruit allies and turn the confrontation into a negotiation of power.",
                ],
            ),
            CampaignBibleArc(
                id="arc-003",
                title="The Long Game",
                hook="A faction offers you resources and protection — in exchange for one favor.",
                stakes="The favor is never what it seems. The price grows with each step in.",
                resolution_paths=[
                    "Complete the faction's agenda and live with the consequences.",
                    "Turn the faction's resources against them at the moment of maximum leverage.",
                    "Find a third party who benefits from both factions losing.",
                ],
            ),
        ],
        opening_hook=(
            f"You arrived in this sector chasing a lead — "
            f"now you're standing in {starting_location.replace('loc-', '').replace('-', ' ')} "
            f"with less than you expected and more trouble than you anticipated."
        ),
    ).model_dump(mode="json")


class CampaignBibleAgent:
    """Generates the campaign screenplay bible at setup time.

    One call at campaign creation. Replaces static era YAML content with
    player-tailored campaign content: locations, NPC cast, companions, factions,
    and quest arcs.

    Use cloud LLM for quality (set STORYTELLER_BIBLE_PROVIDER=anthropic).
    Falls back to local qwen3:8b, then to a deterministic default.
    """

    def __init__(self, llm: AgentLLM | None = None) -> None:
        self._llm = llm

    def build(
        self,
        player_concept: str,
        time_period: str | None = None,
        character_sheet: dict[str, Any] | None = None,
        setting_rules: Any | None = None,
        themes: list[str] | None = None,
        era_metadata: dict[str, Any] | None = None,
        returning_legacy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate the campaign bible. Returns a dict matching CampaignBibleOutput schema.

        Args:
            player_concept: Raw player concept string (e.g., "Joran Vex -- former scout, betrayed by empire").
            time_period: Era identifier (e.g., "rebellion", "dark_times").
            character_sheet: Generated character sheet from BiographerAgent.
            setting_rules: SettingRules from the era pack (universe-specific prompt config).
            themes: Optional thematic keywords from the setup request.
            era_metadata: Optional era.yaml metadata dict (summary, tone, key_conflicts).
            returning_legacy: Optional prior-campaign legacy context for continuity.
        """
        from backend.app.world.era_pack_models import SettingRules

        sr: SettingRules = (
            setting_rules if isinstance(setting_rules, SettingRules) else SettingRules()
        )
        sheet = character_sheet or {}
        starting_location = sheet.get("starting_location", "loc-cantina")
        char_name = sheet.get("name", "the player character")
        char_background = sheet.get("background", "")

        def fallback() -> dict[str, Any]:
            return _default_bible(
                time_period=time_period,
                player_concept=player_concept,
                starting_location=starting_location,
                setting_rules=sr,
            )

        # --- Build the prompt ---
        species_list = ", ".join(sr.common_species)
        factions_list = ", ".join(sr.example_factions)
        era_label = (time_period or "unknown era").upper().replace("_", " ")

        # Era context for the prompt
        era_summary = ""
        if era_metadata and isinstance(era_metadata, dict):
            meta = era_metadata.get("metadata") or era_metadata
            era_summary = (
                f"Era summary: {meta.get('summary', '')}\n"
                f"Tone: {meta.get('tone', '')}\n"
                f"Key conflicts: {'; '.join(meta.get('key_conflicts', []))}"
            )

        themes_text = (
            f"Player-requested themes: {', '.join(themes)}" if themes else ""
        )
        legacy_text = ""
        if isinstance(returning_legacy, dict) and returning_legacy:
            legacy_name = str(returning_legacy.get("character_name") or char_name)
            rel = returning_legacy.get("key_relationships") or []
            threads = returning_legacy.get("unresolved_threads") or []
            emotional_state = str(returning_legacy.get("emotional_state") or "")
            rel_text = ", ".join(
                str(r.get("name") or "")
                for r in rel[:4]
                if isinstance(r, dict) and str(r.get("name") or "").strip()
            )
            thread_text = "; ".join(str(t).strip() for t in threads[:5] if str(t).strip())
            legacy_text = (
                "RETURNING CHARACTER CONTEXT:\n"
                f"{legacy_name} is continuing their story from a previous campaign.\n"
                f"Key relationships: {rel_text or 'none listed'}\n"
                f"Unresolved threads: {thread_text or 'none listed'}\n"
                f"Emotional state: {emotional_state or 'unspecified'}\n\n"
                "INSTRUCTION: Weave at least 2 unresolved threads into quest arcs. "
                "Reference at least 1 key relationship as an NPC, mention, or echo. "
                "Let emotional state influence opening tone.\n"
            )

        system = f"""You are the Campaign Bible Writer for a {sr.setting_name} narrative RPG.
Your output is the SCREENPLAY BIBLE for a complete campaign — generated once at campaign start.
It defines the world, cast, and story arcs tailored to THIS player's specific adventure.

Setting: {sr.setting_name} ({sr.setting_genre})
Era: {era_label}
{era_summary}

NPC species options: {species_list}
Major factions for context: {factions_list}

OUTPUT RULES:
- Output ONLY valid JSON matching the schema below. No markdown, no explanation.
- All names, places, and factions must be {sr.setting_name}-appropriate.
- The starting_location id from the character sheet MUST appear in your locations array with that exact id.
- Generate content specific to THIS player's concept — avoid generic placeholder names.
- The NPC cast must include roles: exactly 1 Villain, 1 Rival, 2 Merchant, 2 Informant, 4 generic (Guard/Local/Pilot/Barkeep/Mechanic/Stranger).

JSON SCHEMA:
{{
  "campaign_title": "string — evocative campaign title",
  "campaign_theme": "string — 2-3 words, e.g. 'gritty redemption'",
  "galactic_situation": "string — 2-3 sentences on current galactic state in this era",
  "opening_crawl": "string — {sr.setting_name}-style opening crawl, 3-4 sentences",
  "locations": [
    {{
      "id": "string — canonical loc id matching start pool (e.g. loc-cantina, loc-docking-bay)",
      "name": "string — evocative proper name",
      "planet": "string — planet name",
      "description": "string — 1-2 sentence atmospheric description",
      "services": ["string — e.g. cantina, intel, transport, safehouse, market"],
      "threat_level": "string — low | moderate | high",
      "faction_control": "string — controlling faction name or empty"
    }}
  ],
  "npc_cast": [
    {{
      "id": "string — e.g. npc-001",
      "name": "string",
      "role": "string — Villain|Rival|Merchant|Informant|Guard|Local|Pilot|Barkeep|Mechanic|Stranger",
      "species": "string",
      "faction": "string",
      "personality": "string — 1-2 sentences",
      "secret_agenda": "string — hidden motivation",
      "voice_style": "string — short voice descriptor"
    }}
  ],
  "companions": [
    {{
      "id": "string — e.g. comp-001",
      "name": "string",
      "species": "string",
      "role": "string — e.g. Pilot, Soldier, Slicer, Medic, Scout",
      "motivation": "string — what drives them",
      "personality": "string — 1-2 sentences",
      "recruitment_hook": "string — how/where the player first meets them",
      "voice_style": "string — short voice descriptor"
    }}
  ],
  "active_factions": [
    {{
      "name": "string",
      "location": "string — location id from your locations array",
      "current_goal": "string — what this faction is actively pursuing",
      "resources": integer (1-10),
      "is_hostile": boolean
    }}
  ],
  "quest_arcs": [
    {{
      "id": "string — e.g. arc-001",
      "title": "string",
      "hook": "string — the inciting situation that draws the player in",
      "stakes": "string — what is at risk",
      "resolution_paths": ["string", "string", "string"]
    }}
  ],
  "opening_hook": "string — 1 sentence: the immediate situation the player finds themselves in"
}}"""

        user = (
            f"Player concept: {player_concept}\n"
            f"Character: {char_name}\n"
            f"Background: {char_background}\n"
            f"Starting location id: {starting_location}\n"
            f"Era: {era_label}\n"
            f"{themes_text}\n\n"
            f"{legacy_text}\n"
            "Generate the full campaign bible. "
            "Make every name, location, and faction specific to this player's story. "
            "The starting location id must appear in the locations array with that exact id value."
        )

        try:
            validated = call_with_json_reliability(
                llm=self._llm,
                role="bible",
                agent_name="CampaignBibleAgent.build",
                campaign_id=None,
                system_prompt=system,
                user_prompt=user,
                schema_class=CampaignBibleOutput,
                fallback_fn=fallback,
            )
            data = (
                validated.model_dump(mode="json")
                if isinstance(validated, CampaignBibleOutput)
                else validated
            )
            # Guarantee the starting location is present in the bible
            location_ids = {loc.get("id", "") for loc in (data.get("locations") or [])}
            if starting_location and starting_location not in location_ids:
                logger.warning(
                    "CampaignBibleAgent: starting_location %r missing from generated locations; injecting fallback.",
                    starting_location,
                )
                data.setdefault("locations", []).insert(
                    0,
                    CampaignBibleLocation(
                        id=starting_location,
                        name=starting_location.replace("loc-", "").replace("-", " ").title(),
                        planet="Unknown",
                        description="A place where stories begin.",
                        services=["cantina"],
                        threat_level="low",
                    ).model_dump(mode="json"),
                )
            return data
        except Exception as e:
            log_error_with_context(
                error=e,
                node_name="campaign_bible",
                campaign_id=None,
                turn_number=None,
                agent_name="CampaignBibleAgent.build",
                extra_context={"time_period": time_period, "player_concept": player_concept[:100]},
            )
            logger.warning("CampaignBibleAgent.build failed; using deterministic fallback.")
            return fallback()
