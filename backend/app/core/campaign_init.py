"""Campaign world generation: per-campaign locations, NPCs, and quest hooks.

V3.0: Supports Historical/Sandbox campaign modes and optional cloud blueprint.

Runs once at campaign creation to generate a unique world from era pack
base content + RAG-retrieved lore from ingested novels.

Campaign Modes (HOI4-style):
  Historical: Canon events are immutable. Generated content fits within
    established lore. Player choices affect personal story, not galactic history.
  Sandbox: Player choices can reshape the galaxy. Generated content may
    diverge from canon. Factions can be altered by player actions.

Cloud Blueprint (opt-in via ENABLE_CLOUD_BLUEPRINT=1):
  When enabled, uses a cloud LLM (Anthropic/OpenAI) for the strategic
  campaign blueprint — the conflict web, NPC relationship graph, and
  thematic throughline. Local models still handle per-turn execution.
  Default: OFF (local Ollama only).
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
from typing import Any

from backend.app.constants import get_scale_profile
from backend.app.core.agents.base import AgentLLM
from backend.app.core.json_repair import ensure_json
from backend.app.core.warnings import add_warning

logger = logging.getLogger(__name__)

# ── Campaign mode types ──────────────────────────────────────────────
VALID_CAMPAIGN_MODES = ("historical", "sandbox")

# Default counts for generated content
DEFAULT_GENERATED_LOCATIONS = 5
DEFAULT_GENERATED_NPCS = 10
DEFAULT_GENERATED_QUESTS = 4


def _derive_campaign_seed(campaign_id: str) -> int:
    """Derive a deterministic seed from campaign_id for reproducible generation."""
    digest = hashlib.sha256(campaign_id.encode("utf-8")).hexdigest()[:16]
    return int(digest, 16)


def _retrieve_era_lore(era: str | None, starting_location: str | None, top_k: int = 15) -> list[dict]:
    """Retrieve lore chunks for the campaign's era to seed world generation."""
    if not era:
        return []
    try:
        from backend.app.rag.lore_retriever import retrieve_lore
        query = f"{era} world locations characters factions quests"
        if starting_location:
            query += f" {starting_location.replace('loc-', '').replace('-', ' ')}"
        chunks = retrieve_lore(
            query,
            top_k=top_k,
            era=era,
            doc_types=["novel", "sourcebook"],
        )
        return chunks
    except Exception as e:
        logger.warning("Failed to retrieve lore for campaign init: %s", e)
        return []


def _build_generation_prompt(
    era: str | None,
    era_pack: Any | None,
    lore_context: str,
    existing_locations: list[str],
    existing_npcs: list[str],
    existing_factions: list[dict],
    player_concept: str,
    starting_location: str,
    campaign_mode: str = "historical",
    num_locations: int = DEFAULT_GENERATED_LOCATIONS,
    num_npcs: int = DEFAULT_GENERATED_NPCS,
    num_quests: int = DEFAULT_GENERATED_QUESTS,
) -> tuple[str, str]:
    """Build system and user prompts for campaign world generation."""
    era_label = era or "unknown"
    faction_names = [f.get("name", "") for f in existing_factions if isinstance(f, dict)]

    # Mode-specific preamble
    if campaign_mode == "sandbox":
        mode_instruction = (
            "CAMPAIGN MODE: SANDBOX. The player's choices can reshape galactic history. "
            "Generated content should include leverage points where player actions could "
            "alter major events. Factions may have vulnerabilities the player can exploit. "
            "Canon events are starting conditions, not certainties.\n\n"
        )
    else:
        mode_instruction = (
            "CAMPAIGN MODE: HISTORICAL. Canon events in this era are immutable. "
            "Generated content must fit within established Star Wars Legends lore. "
            "NPCs and quests should exist in the margins of canon history — not contradict it. "
            "The player can fail missions and face real consequences, but galactic-scale "
            "events proceed as established.\n\n"
        )

    system_prompt = (
        "You are a world-builder for a narrative RPG game. Generate unique campaign content "
        "that enriches the base world with new locations, NPCs, and quest hooks.\n\n"
        + mode_instruction
        "Output ONLY a valid JSON object with this exact structure:\n"
        "{\n"
        '  "locations": [\n'
        '    {"id": "gen-loc-NAME", "name": "Location Name", "description": "1-2 sentences", '
        '"tags": ["tag1", "tag2"], "threat_level": "low|moderate|high", '
        '"planet": "Planet Name", "scene_types": ["dialogue", "combat"], '
        '"services": [], "travel_links": ["existing-loc-id"]}\n'
        "  ],\n"
        '  "npcs": [\n'
        '    {"id": "gen-npc-NAME", "name": "NPC Name", "role": "Role", '
        '"faction_id": "faction_id_or_null", "default_location_id": "location-id", '
        '"traits": ["trait1", "trait2"], "motivation": "What drives them", '
        '"secret": "Hidden agenda or null", "species": "Species", '
        '"voice": {"belief": "Core belief", "wound": "Past trauma", '
        '"rhetorical_style": "How they speak"}}\n'
        "  ],\n"
        '  "quests": [\n'
        '    {"id": "gen-quest-NAME", "title": "Quest Title", '
        '"description": "What the quest is about", '
        '"entry_location": "location-id", "key_npc": "npc-id", '
        '"stages": [{"id": "stage-1", "description": "What happens"}]}\n'
        "  ]\n"
        "}\n\n"
        "RULES:\n"
        f"- Generate exactly {num_locations} locations, {num_npcs} NPCs, and {num_quests} quest hooks.\n"
        "- Location IDs must start with 'gen-loc-'. NPC IDs must start with 'gen-npc-'. Quest IDs must start with 'gen-quest-'.\n"
        "- NPCs should have varied roles: merchants, informants, allies, rivals, mysterious figures.\n"
        "- Each NPC must have a 'voice' object with 'belief', 'wound', and 'rhetorical_style'.\n"
        "- Quest hooks should involve player choices and moral dilemmas.\n"
        "- Locations should include at least one travel_link to an existing location.\n"
        "- Content must be thematically consistent with the era and setting.\n"
        "- Use ONE simple, memorable name per NPC. No titles or honorifics.\n"
        "- Valid scene_types: dialogue, combat, stealth, travel, investigation.\n"
        "- Valid threat_levels: low, moderate, high, extreme.\n"
    )

    user_prompt = (
        f"ERA: {era_label}\n"
        f"PLAYER CONCEPT: {player_concept or 'A traveler seeking adventure'}\n"
        f"STARTING LOCATION: {starting_location}\n"
        f"EXISTING LOCATIONS: {', '.join(existing_locations[:10]) if existing_locations else 'none'}\n"
        f"EXISTING FACTIONS: {', '.join(faction_names[:5]) if faction_names else 'none'}\n"
        f"EXISTING NPCs: {', '.join(existing_npcs[:10]) if existing_npcs else 'none'}\n"
    )

    if lore_context:
        user_prompt += f"\nLORE CONTEXT (from ingested novels — use for inspiration):\n{lore_context}\n"

    user_prompt += (
        "\nGenerate campaign-specific content that complements the existing world. "
        "Create locations the player can discover, NPCs they can interact with, "
        "and quest hooks that create dramatic tension."
    )

    return system_prompt, user_prompt


def _deterministic_locations(
    rng: random.Random,
    era: str | None,
    existing_locations: list[str],
    planet: str | None = None,
    count: int = DEFAULT_GENERATED_LOCATIONS,
) -> list[dict[str, Any]]:
    """Generate deterministic fallback locations when LLM is unavailable."""
    location_templates = [
        {"suffix": "hidden-cantina", "name": "The Hidden Cantina", "tags": ["cantina", "underworld"], "threat": "low", "scenes": ["dialogue"], "services": ["cantina"]},
        {"suffix": "abandoned-outpost", "name": "Abandoned Outpost", "tags": ["ruins", "exploration"], "threat": "moderate", "scenes": ["investigation", "combat"], "services": []},
        {"suffix": "black-market", "name": "Black Market Bazaar", "tags": ["market", "underworld"], "threat": "moderate", "scenes": ["dialogue", "stealth"], "services": ["black_market"]},
        {"suffix": "docking-bay-7", "name": "Docking Bay 7", "tags": ["spaceport", "travel"], "threat": "low", "scenes": ["dialogue", "travel"], "services": ["docking"]},
        {"suffix": "safe-house", "name": "The Safe House", "tags": ["hideout", "safe"], "threat": "low", "scenes": ["dialogue"], "services": []},
        {"suffix": "fighting-pit", "name": "The Fighting Pit", "tags": ["arena", "underworld"], "threat": "high", "scenes": ["combat", "dialogue"], "services": []},
        {"suffix": "old-temple", "name": "Ruined Temple", "tags": ["ruins", "mystical"], "threat": "moderate", "scenes": ["investigation", "combat"], "services": []},
        {"suffix": "comm-tower", "name": "Communications Tower", "tags": ["tech", "strategic"], "threat": "moderate", "scenes": ["stealth", "investigation"], "services": []},
    ]
    rng.shuffle(location_templates)
    locations = []
    travel_target = existing_locations[0] if existing_locations else "loc-cantina"
    for i, tmpl in enumerate(location_templates[:count]):
        locations.append({
            "id": f"gen-loc-{tmpl['suffix']}",
            "name": tmpl["name"],
            "description": f"A {tmpl['tags'][0]} area discovered during the campaign.",
            "tags": tmpl["tags"],
            "threat_level": tmpl["threat"],
            "planet": planet or "",
            "scene_types": tmpl["scenes"],
            "services": tmpl["services"],
            "travel_links": [{"to_location_id": travel_target}],
        })
    return locations


def _deterministic_npcs(
    rng: random.Random,
    generated_locations: list[dict],
    count: int = DEFAULT_GENERATED_NPCS,
) -> list[dict[str, Any]]:
    """Generate deterministic fallback NPCs when LLM is unavailable."""
    npc_templates = [
        {"name": "Rask", "role": "Informant", "traits": ["observant", "cautious"], "species": "Human", "motivation": "Survive by trading secrets"},
        {"name": "Vex", "role": "Merchant", "traits": ["shrewd", "charming"], "species": "Rodian", "motivation": "Profit above all"},
        {"name": "Kira", "role": "Rebel Contact", "traits": ["idealistic", "determined"], "species": "Human", "motivation": "Fight for freedom"},
        {"name": "Torr", "role": "Bounty Hunter", "traits": ["ruthless", "efficient"], "species": "Trandoshan", "motivation": "Complete the contract"},
        {"name": "Senna", "role": "Healer", "traits": ["compassionate", "wise"], "species": "Twi'lek", "motivation": "Help those in need"},
        {"name": "Greel", "role": "Mechanic", "traits": ["resourceful", "grumpy"], "species": "Human", "motivation": "Keep things running"},
        {"name": "Nyx", "role": "Spy", "traits": ["deceptive", "intelligent"], "species": "Human", "motivation": "Gather intelligence"},
        {"name": "Brak", "role": "Enforcer", "traits": ["intimidating", "loyal"], "species": "Wookiee", "motivation": "Protect the boss"},
        {"name": "Zeela", "role": "Smuggler", "traits": ["daring", "witty"], "species": "Human", "motivation": "One last big score"},
        {"name": "Ossik", "role": "Scholar", "traits": ["curious", "eccentric"], "species": "Ithorian", "motivation": "Preserve ancient knowledge"},
        {"name": "Thal", "role": "Guard Captain", "traits": ["strict", "honorable"], "species": "Human", "motivation": "Maintain order"},
        {"name": "Mira", "role": "Pilot", "traits": ["reckless", "skilled"], "species": "Human", "motivation": "Freedom of the stars"},
    ]
    rng.shuffle(npc_templates)
    loc_ids = [loc["id"] for loc in generated_locations] if generated_locations else ["gen-loc-hidden-cantina"]
    npcs = []
    for i, tmpl in enumerate(npc_templates[:count]):
        loc = loc_ids[i % len(loc_ids)]
        npc_id = f"gen-npc-{tmpl['name'].lower().replace(' ', '-')}"
        npcs.append({
            "id": npc_id,
            "name": tmpl["name"],
            "role": tmpl["role"],
            "faction_id": None,
            "default_location_id": loc,
            "traits": tmpl["traits"],
            "motivation": tmpl["motivation"],
            "secret": None,
            "species": tmpl["species"],
            "voice": {
                "belief": f"The world rewards those who {tmpl['traits'][0]}.",
                "wound": "A past they don't talk about.",
                "rhetorical_style": f"{tmpl['traits'][0]}, direct",
            },
        })
    return npcs


def _deterministic_quests(
    rng: random.Random,
    generated_npcs: list[dict],
    generated_locations: list[dict],
    count: int = DEFAULT_GENERATED_QUESTS,
) -> list[dict[str, Any]]:
    """Generate deterministic fallback quest hooks when LLM is unavailable."""
    quest_templates = [
        {"title": "The Missing Shipment", "desc": "A valuable cargo has gone missing. Someone knows where it went.", "stages": ["Find the informant", "Track the shipment", "Recover or negotiate"]},
        {"title": "Old Debts", "desc": "A figure from the past has come calling with a debt that can't be paid in credits.", "stages": ["Meet the creditor", "Choose: pay or refuse", "Deal with consequences"]},
        {"title": "Whispers in the Dark", "desc": "Strange rumors point to something hidden beneath the surface.", "stages": ["Investigate the rumors", "Find the hidden entrance", "Discover the truth"]},
        {"title": "The Double Agent", "desc": "Someone in the local network is feeding information to the enemy.", "stages": ["Gather evidence", "Identify the traitor", "Confront or expose"]},
        {"title": "A Desperate Plea", "desc": "A stranger begs for help. Their story doesn't quite add up.", "stages": ["Hear their case", "Verify the story", "Decide who to help"]},
        {"title": "The Arena Challenge", "desc": "A fighting pit offers glory and credits — but the real prize is information.", "stages": ["Enter the tournament", "Win or survive", "Claim the prize"]},
    ]
    rng.shuffle(quest_templates)
    quests = []
    for i, tmpl in enumerate(quest_templates[:count]):
        npc = generated_npcs[i % len(generated_npcs)] if generated_npcs else {"id": "gen-npc-rask", "name": "Rask"}
        loc = generated_locations[i % len(generated_locations)] if generated_locations else {"id": "gen-loc-hidden-cantina"}
        quests.append({
            "id": f"gen-quest-{i+1}",
            "title": tmpl["title"],
            "description": tmpl["desc"],
            "entry_location": loc["id"],
            "key_npc": npc["id"],
            "stages": [
                {"id": f"stage-{j+1}", "description": s}
                for j, s in enumerate(tmpl["stages"])
            ],
        })
    return quests


def _parse_llm_world(raw: str) -> dict[str, Any] | None:
    """Parse LLM output into world generation data."""
    cleaned = ensure_json(raw)
    if not cleaned:
        return None
    try:
        data = json.loads(cleaned)
        if not isinstance(data, dict):
            return None
        # Validate minimal structure
        if not isinstance(data.get("locations"), list):
            data["locations"] = []
        if not isinstance(data.get("npcs"), list):
            data["npcs"] = []
        if not isinstance(data.get("quests"), list):
            data["quests"] = []
        return data
    except (json.JSONDecodeError, TypeError):
        return None


def _normalize_generated_location(loc: dict) -> dict[str, Any]:
    """Normalize a generated location dict to match EraLocation-compatible schema."""
    loc_id = loc.get("id", "")
    if not loc_id.startswith("gen-loc-"):
        loc_id = f"gen-loc-{loc_id}"
    travel_links = loc.get("travel_links", [])
    normalized_links = []
    for link in travel_links:
        if isinstance(link, str):
            normalized_links.append({"to_location_id": link})
        elif isinstance(link, dict):
            normalized_links.append(link)
    return {
        "id": loc_id,
        "name": loc.get("name", "Unknown Location"),
        "description": loc.get("description", ""),
        "tags": loc.get("tags", []),
        "threat_level": loc.get("threat_level", "moderate"),
        "planet": loc.get("planet", ""),
        "scene_types": [s for s in loc.get("scene_types", ["dialogue"]) if s in ("dialogue", "combat", "stealth", "travel", "investigation")],
        "services": loc.get("services", []),
        "travel_links": normalized_links,
        "origin": "generated",
    }


def _normalize_generated_npc(npc: dict) -> dict[str, Any]:
    """Normalize a generated NPC dict to match EraNpcEntry-compatible schema."""
    npc_id = npc.get("id", "")
    if not npc_id.startswith("gen-npc-"):
        npc_id = f"gen-npc-{npc_id}"
    voice = npc.get("voice") or {}
    return {
        "id": npc_id,
        "name": npc.get("name", "Wanderer"),
        "role": npc.get("role", "NPC"),
        "faction_id": npc.get("faction_id"),
        "default_location_id": npc.get("default_location_id", ""),
        "traits": npc.get("traits", []),
        "motivation": npc.get("motivation", ""),
        "secret": npc.get("secret"),
        "species": npc.get("species", ""),
        "voice": {
            "belief": voice.get("belief", ""),
            "wound": voice.get("wound", ""),
            "rhetorical_style": voice.get("rhetorical_style", ""),
        },
        "origin": "generated",
    }


def _normalize_generated_quest(quest: dict) -> dict[str, Any]:
    """Normalize a generated quest dict."""
    quest_id = quest.get("id", "")
    if not quest_id.startswith("gen-quest-"):
        quest_id = f"gen-quest-{quest_id}"
    stages = quest.get("stages", [])
    normalized_stages = []
    for i, stage in enumerate(stages):
        if isinstance(stage, str):
            normalized_stages.append({"id": f"stage-{i+1}", "description": stage})
        elif isinstance(stage, dict):
            normalized_stages.append(stage)
    return {
        "id": quest_id,
        "title": quest.get("title", "Unknown Quest"),
        "description": quest.get("description", ""),
        "entry_location": quest.get("entry_location", ""),
        "key_npc": quest.get("key_npc", ""),
        "stages": normalized_stages,
        "origin": "generated",
    }


def _try_cloud_blueprint(
    era: str | None,
    era_pack: Any | None,
    player_concept: str,
    existing_factions: list[dict],
    campaign_mode: str,
    warnings: list[str] | None = None,
) -> dict[str, Any] | None:
    """Optionally call a cloud LLM for strategic campaign planning.

    Only runs when ENABLE_CLOUD_BLUEPRINT=1. Returns a blueprint dict
    with conflict_web, thematic_throughline, and npc_relationship_hints,
    or None if disabled/failed.
    """
    try:
        from backend.app.config import ENABLE_CLOUD_BLUEPRINT
        if not ENABLE_CLOUD_BLUEPRINT:
            return None
    except ImportError:
        return None

    from backend.app.core.era_transition import get_era_definition, get_canon_constraints

    era_def = get_era_definition(era) if era else None
    canon = get_canon_constraints(era or "", campaign_mode)

    system = (
        "You are a master game designer planning a narrative RPG campaign. "
        "Output ONLY valid JSON with keys: conflict_web (array of faction conflict pairs), "
        "thematic_throughline (string: the campaign's central theme/question), "
        "npc_relationship_hints (array of objects: {npc_role, connected_to, relationship_type}), "
        "dramatic_tension (string: what makes this campaign interesting).\n\n"
        f"Campaign mode: {campaign_mode.upper()}. "
        f"{canon.get('mode_instruction', '')}"
    )
    faction_names = [f.get("name", "") for f in existing_factions if isinstance(f, dict)]
    user = (
        f"Era: {era_def.display_name if era_def else era or 'unknown'} ({era_def.time_period if era_def else 'unknown'})\n"
        f"Era summary: {era_def.summary if era_def else 'N/A'}\n"
        f"Player concept: {player_concept or 'A traveler'}\n"
        f"Active factions: {', '.join(faction_names) if faction_names else 'none'}\n\n"
        "Design the strategic backbone for this campaign: what conflicts drive the story, "
        "what theme binds it together, and how NPCs connect to each other."
    )

    try:
        from backend.app.core.llm_provider import create_provider
        from backend.app.core.agents.base import AgentLLM

        # Try to get a cloud provider (anthropic or openai)
        llm = AgentLLM("architect")
        client = llm._get_client()

        # Check if we have a fallback cloud provider configured
        fallback = llm._try_fallback_client()
        if fallback is None:
            # No cloud provider configured — use local
            logger.debug("Cloud blueprint enabled but no cloud provider configured, skipping")
            return None

        raw = fallback.complete(user, system, json_mode=True)
        cleaned = ensure_json(raw)
        if cleaned:
            blueprint = json.loads(cleaned)
            if isinstance(blueprint, dict):
                logger.info("CampaignInit: Cloud blueprint generated successfully")
                return blueprint
    except Exception as e:
        logger.warning("CampaignInit: Cloud blueprint failed (non-fatal): %s", e)
        add_warning(warnings, "Cloud campaign blueprint unavailable, using local generation.")

    return None


def initialize_campaign_world(
    campaign_id: str,
    era: str | None,
    era_pack: Any | None,
    player_concept: str,
    starting_location: str,
    existing_factions: list[dict],
    skeleton: dict[str, Any],
    campaign_mode: str = "historical",
    campaign_scale: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Generate per-campaign world content: locations, NPCs, and quest hooks.

    Returns a dict with keys: generated_locations, generated_npcs, generated_quests,
    campaign_mode, campaign_scale, and optionally campaign_blueprint (if cloud blueprint enabled).
    Uses LLM when available, falls back to deterministic generation.

    The ``campaign_scale`` parameter (small/medium/large/epic) controls how many
    locations, NPCs, and quests are generated.  Defaults to "medium" (the previous
    hardcoded behaviour).
    """
    # Validate campaign mode
    if campaign_mode not in VALID_CAMPAIGN_MODES:
        logger.warning("Invalid campaign_mode '%s', defaulting to 'historical'", campaign_mode)
        campaign_mode = "historical"

    # Resolve scale profile
    scale_profile = get_scale_profile(campaign_scale)
    effective_scale = campaign_scale if campaign_scale in ("small", "medium", "large", "epic") else "medium"

    seed = _derive_campaign_seed(campaign_id)
    rng = random.Random(seed)

    # Gather existing content from era pack
    existing_locations = []
    existing_npc_names = []
    planet = None
    if era_pack:
        existing_locations = [loc.id for loc in (era_pack.locations or [])]
        all_npcs = list(era_pack.npcs.anchors or []) + list(era_pack.npcs.rotating or [])
        existing_npc_names = [n.name for n in all_npcs]
        # Determine planet from starting location
        loc_obj = era_pack.location_by_id(starting_location) if hasattr(era_pack, "location_by_id") else None
        if loc_obj and loc_obj.planet:
            planet = loc_obj.planet

    # Also include NPC names from skeleton
    npc_cast = skeleton.get("npc_cast") or []
    existing_npc_names.extend(n.get("name", "") for n in npc_cast if n.get("name"))

    # Optional: cloud blueprint for strategic planning
    blueprint = _try_cloud_blueprint(
        era=era, era_pack=era_pack, player_concept=player_concept,
        existing_factions=existing_factions, campaign_mode=campaign_mode,
        warnings=warnings,
    )

    # Retrieve lore context from ingested novels
    lore_chunks = _retrieve_era_lore(era, starting_location)
    lore_context = ""
    if lore_chunks:
        lore_texts = [c.get("text", "")[:300] for c in lore_chunks[:10]]
        lore_context = "\n---\n".join(t for t in lore_texts if t)

    # If blueprint exists, append it to lore context for richer generation
    if blueprint:
        blueprint_hint = (
            f"\nCAMPAIGN BLUEPRINT (strategic backbone):\n"
            f"Theme: {blueprint.get('thematic_throughline', 'N/A')}\n"
            f"Dramatic tension: {blueprint.get('dramatic_tension', 'N/A')}\n"
        )
        lore_context += blueprint_hint

    # Try LLM generation
    generated = None
    try:
        llm = AgentLLM("architect")
        system_prompt, user_prompt = _build_generation_prompt(
            era=era,
            era_pack=era_pack,
            lore_context=lore_context,
            existing_locations=existing_locations,
            existing_npcs=existing_npc_names,
            existing_factions=existing_factions,
            player_concept=player_concept,
            starting_location=starting_location,
            campaign_mode=campaign_mode,
            num_locations=scale_profile.generated_locations,
            num_npcs=scale_profile.generated_npcs,
            num_quests=scale_profile.generated_quests,
        )
        raw = llm.complete(system_prompt, user_prompt, json_mode=True)
        generated = _parse_llm_world(raw)
        if generated:
            logger.info(
                "CampaignInit: LLM generated %d locations, %d NPCs, %d quests for campaign %s (mode=%s)",
                len(generated.get("locations", [])),
                len(generated.get("npcs", [])),
                len(generated.get("quests", [])),
                campaign_id,
                campaign_mode,
            )
    except Exception as e:
        logger.warning("CampaignInit: LLM generation failed, using deterministic fallback: %s", e)
        add_warning(warnings, "Campaign world generation fell back to deterministic mode.")

    # Use LLM results or fall back to deterministic
    if generated and generated.get("locations"):
        gen_locations = [_normalize_generated_location(loc) for loc in generated["locations"]]
    else:
        gen_locations = _deterministic_locations(rng, era, existing_locations, planet, count=scale_profile.generated_locations)

    if generated and generated.get("npcs"):
        gen_npcs = [_normalize_generated_npc(npc) for npc in generated["npcs"]]
    else:
        gen_npcs = _deterministic_npcs(rng, gen_locations, count=scale_profile.generated_npcs)

    if generated and generated.get("quests"):
        gen_quests = [_normalize_generated_quest(q) for q in generated["quests"]]
    else:
        gen_quests = _deterministic_quests(rng, gen_npcs, gen_locations, count=scale_profile.generated_quests)

    # Ensure generated NPCs reference valid locations
    all_loc_ids = set(existing_locations) | {loc["id"] for loc in gen_locations}
    for npc in gen_npcs:
        if npc.get("default_location_id") and npc["default_location_id"] not in all_loc_ids:
            # Reassign to a random generated location
            npc["default_location_id"] = gen_locations[0]["id"] if gen_locations else starting_location

    result: dict[str, Any] = {
        "generated_locations": gen_locations,
        "generated_npcs": gen_npcs,
        "generated_quests": gen_quests,
        "campaign_mode": campaign_mode,
        "campaign_scale": effective_scale,
        "world_generation": {
            "source": "llm" if (generated and generated.get("locations")) else "deterministic",
            "seed": seed,
            "lore_chunks_used": len(lore_chunks),
            "campaign_mode": campaign_mode,
            "campaign_scale": effective_scale,
        },
    }
    if blueprint:
        result["campaign_blueprint"] = blueprint
    return result
