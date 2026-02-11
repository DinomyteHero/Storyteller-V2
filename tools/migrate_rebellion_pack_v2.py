#!/usr/bin/env python3
"""
Rebellion Era Pack V2 Migration Script

Applies the latest backend schema to Rebellion era pack YAMLs:
- Enriches NPCs with voice fields (belief/wound/taboo/rhetorical_style/tell)
- Enriches locations with keywords, access_points, encounter_tables
- Creates/enriches rumors, events, quests, facts files
- Validates all references and bounds
- Generates "Manual Authoring Needed" report

Usage:
    python tools/migrate_rebellion_pack_v2.py [--dry-run] [--report-only]
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.world.era_pack_loader import load_era_pack
from app.world.era_pack_models import (
    ALLOWED_BYPASS_METHODS,
    ALLOWED_SCENE_TYPES,
    ALLOWED_SERVICES,
    EraAccessPoint,
    EraEncounterEntry,
    EraEvent,
    EraFact,
    EraLocation,
    EraNpcEntry,
    EraNpcTemplate,
    EraQuest,
    EraQuestStage,
    EraRumor,
    NpcAuthority,
    NpcKnowledge,
    NpcLevers,
    NpcSpawnRules,
)

# ══════════════════════════════════════════════════════════════════════════════
# ENRICHMENT MAPPINGS (deterministic, no LLM)
# ══════════════════════════════════════════════════════════════════════════════

LOCATION_TYPE_KEYWORDS = {
    "garrison": ["ID scanners", "durasteel corridors", "patrol boots", "sealed doors", "security lights"],
    "checkpoint": ["checkpoint scanners", "ID verification", "uniformed guards", "inspection zone", "clearance codes"],
    "cantina": ["stale smoke", "low music", "back booths", "credit chips", "watchful eyes"],
    "base": ["briefing boards", "hangar fuel", "quiet urgency", "patched uniforms", "coded comms"],
    "rebel_base": ["briefing boards", "hangar fuel", "quiet urgency", "patched uniforms", "coded comms"],
    "safehouse": ["hidden entrance", "coded knock", "whispered plans", "escape route", "cautious eyes"],
    "market": ["haggling voices", "mixed scents", "sensor sweeps", "currency exchange", "surveillance droids"],
    "spaceport": ["docking clamps", "customs booth", "departure boards", "starship fuel", "port authority"],
    "wilderness": ["open sky", "natural cover", "ambient sounds", "distant patrols", "unmarked trails"],
    "palace": ["polished floors", "armed guards", "wealth display", "power brokers", "surveillance cams"],
    "prison": ["durasteel cells", "guard rotations", "suppression fields", "interrogation rooms", "escape fantasies"],
    "flagship": ["bridge stations", "military precision", "tactical displays", "rank insignia", "command hierarchy"],
}

LOCATION_TYPE_SCENE_TYPES = {
    "garrison": ["dialogue", "stealth", "investigation"],
    "checkpoint": ["dialogue", "stealth"],
    "cantina": ["dialogue", "investigation"],
    "base": ["dialogue", "investigation"],
    "rebel_base": ["dialogue", "investigation"],
    "safehouse": ["dialogue", "investigation"],
    "market": ["dialogue", "investigation", "travel"],
    "spaceport": ["dialogue", "travel"],
    "wilderness": ["travel", "investigation", "combat"],
    "palace": ["dialogue", "stealth"],
    "prison": ["stealth", "combat", "investigation"],
    "flagship": ["dialogue", "combat"],
}

LOCATION_TYPE_ACCESS_POINTS = {
    "garrison": [
        {"id": "main_gate", "type": "door", "visibility": "public", "bypass_methods": ["credential", "bribe", "charm"]},
        {"id": "service_entrance", "type": "door", "visibility": "restricted", "bypass_methods": ["stealth", "hack", "disable"]},
    ],
    "checkpoint": [
        {"id": "main_checkpoint", "type": "gate", "visibility": "public", "bypass_methods": ["credential", "deception", "bribe"]},
        {"id": "bypass_route", "type": "path", "visibility": "hidden", "bypass_methods": ["sneak", "climb"]},
    ],
    "cantina": [
        {"id": "front_door", "type": "door", "visibility": "public", "bypass_methods": []},
        {"id": "back_room", "type": "door", "visibility": "restricted", "bypass_methods": ["bribe", "charm"]},
    ],
    "base": [
        {"id": "main_entrance", "type": "door", "visibility": "public", "bypass_methods": ["credential"]},
        {"id": "comms_hatch", "type": "hatch", "visibility": "hidden", "bypass_methods": ["hack", "stealth"]},
    ],
    "rebel_base": [
        {"id": "main_entrance", "type": "door", "visibility": "public", "bypass_methods": ["credential"]},
        {"id": "emergency_exit", "type": "hatch", "visibility": "secret", "bypass_methods": ["stealth"]},
    ],
    "safehouse": [
        {"id": "hidden_entrance", "type": "door", "visibility": "hidden", "bypass_methods": ["credential"]},
    ],
    "market": [
        {"id": "main_entrance", "type": "gate", "visibility": "public", "bypass_methods": []},
    ],
    "spaceport": [
        {"id": "main_terminal", "type": "door", "visibility": "public", "bypass_methods": []},
        {"id": "cargo_bay", "type": "door", "visibility": "restricted", "bypass_methods": ["credential", "bribe", "hack"]},
    ],
    "wilderness": [
        {"id": "trail", "type": "path", "visibility": "public", "bypass_methods": []},
    ],
    "palace": [
        {"id": "main_gate", "type": "gate", "visibility": "public", "bypass_methods": ["credential"]},
        {"id": "servant_entrance", "type": "door", "visibility": "restricted", "bypass_methods": ["deception", "sneak"]},
    ],
    "prison": [
        {"id": "main_entrance", "type": "door", "visibility": "public", "bypass_methods": ["credential", "intimidate"]},
        {"id": "ventilation_shaft", "type": "vent", "visibility": "hidden", "bypass_methods": ["sneak", "disable"]},
    ],
    "flagship": [
        {"id": "docking_bay", "type": "door", "visibility": "public", "bypass_methods": ["credential"]},
        {"id": "maintenance_hatch", "type": "hatch", "visibility": "restricted", "bypass_methods": ["hack", "stealth"]},
    ],
}

ROLE_VOICE_DEFAULTS = {
    "imperial": {
        "belief": "Order must be maintained at all costs.",
        "wound": "They learned that dissent is punished swiftly.",
        "taboo": "disloyalty",
        "rhetorical_style": "coldly_practical",
        "tell": "stands rigidly at attention",
    },
    "rebel": {
        "belief": "Freedom is worth any sacrifice.",
        "wound": "They've lost comrades to Imperial cruelty.",
        "taboo": "betraying the cause",
        "rhetorical_style": "earnest",
        "tell": "glances over shoulder habitually",
    },
    "smuggler": {
        "belief": "Survival requires choices, not principles.",
        "wound": "They learned trust can be expensive.",
        "taboo": "betrayal",
        "rhetorical_style": "blunt",
        "tell": "watches you carefully",
    },
    "officer": {
        "belief": "Efficiency and discipline bring success.",
        "wound": "They learned that failure has consequences.",
        "taboo": "incompetence",
        "rhetorical_style": "precise",
        "tell": "adjusts uniform unconsciously",
    },
    "pilot": {
        "belief": "Skill and nerve win battles.",
        "wound": "They've seen too many friends not come back.",
        "taboo": "cowardice",
        "rhetorical_style": "casual",
        "tell": "gestures like flying",
    },
    "default": {
        "belief": "Survival requires choices.",
        "wound": "They learned trust can be expensive.",
        "taboo": "betrayal",
        "rhetorical_style": "blunt",
        "tell": "watches you carefully",
    },
}

TAG_SPAWN_RULES = {
    "imperial": {"location_tags_any": ["imperial", "garrison", "checkpoint"], "min_alert": 20, "max_alert": 100},
    "rebel": {"location_tags_any": ["rebel", "base", "safehouse"], "min_alert": 0, "max_alert": 60},
    "underworld": {"location_tags_any": ["cantina", "market", "docks", "slums"], "min_alert": 0, "max_alert": 80},
    "smuggler": {"location_tags_any": ["cantina", "market", "spaceport"], "min_alert": 0, "max_alert": 70},
    "civilian": {"location_tags_any": ["market", "cantina", "settlement"], "min_alert": 0, "max_alert": 60},
}


# ══════════════════════════════════════════════════════════════════════════════
# YAML I/O
# ══════════════════════════════════════════════════════════════════════════════


def load_yaml(path: Path) -> Any:
    """Load YAML with deterministic ordering."""
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_yaml(path: Path, data: Any, backup: bool = True) -> None:
    """Save YAML with deterministic ordering and optional backup."""
    if backup and path.exists():
        backup_path = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup_path)
        print(f"  -> Backup: {backup_path.name}")

    with path.open("w", encoding="utf-8") as f:
        yaml.dump(
            data,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=120,
            indent=2,
        )
    print(f"  -> Wrote: {path.name}")


# ══════════════════════════════════════════════════════════════════════════════
# ENRICHMENT LOGIC
# ══════════════════════════════════════════════════════════════════════════════


def infer_location_type(loc: dict[str, Any]) -> str:
    """Infer location type from tags and name."""
    tags = set(str(t).lower() for t in loc.get("tags", []))
    name_lower = loc.get("name", "").lower()

    # Check tags first
    for tag in tags:
        if tag in LOCATION_TYPE_KEYWORDS:
            return tag

    # Check name keywords
    for keyword in ["garrison", "checkpoint", "cantina", "base", "safehouse", "market", "spaceport", "palace", "prison"]:
        if keyword in name_lower:
            return keyword

    # Default to market if neutral/settlement, otherwise cantina
    if "neutral" in tags or "settlement" in tags:
        return "market"
    return "cantina"


def enrich_location_keywords(loc: dict[str, Any]) -> list[str]:
    """Generate keywords if missing."""
    existing = loc.get("keywords", [])
    if existing and len(existing) >= 5:
        return existing

    loc_type = infer_location_type(loc)
    keywords = list(LOCATION_TYPE_KEYWORDS.get(loc_type, ["bustling activity", "ambient chatter", "tense atmosphere", "surveillance presence", "hidden agendas"]))

    # Add tags, region, planet, threat_level as supplemental keywords
    tags = loc.get("tags", [])
    if tags:
        keywords.extend(str(t) for t in tags[:3])
    if loc.get("region"):
        keywords.append(str(loc["region"]))
    if loc.get("planet"):
        keywords.append(str(loc["planet"]))
    if loc.get("threat_level"):
        keywords.append(str(loc["threat_level"]))

    # Deduplicate and limit to 5-12
    seen = set()
    unique_keywords = []
    for k in keywords:
        if k.lower() not in seen:
            seen.add(k.lower())
            unique_keywords.append(k)
    return unique_keywords[:12]


def enrich_location_scene_types(loc: dict[str, Any]) -> list[str]:
    """Infer scene_types if missing."""
    existing = loc.get("scene_types", [])
    if existing:
        return existing

    loc_type = infer_location_type(loc)
    return LOCATION_TYPE_SCENE_TYPES.get(loc_type, ["dialogue", "investigation"])


def enrich_location_access_points(loc: dict[str, Any]) -> list[dict[str, Any]]:
    """Add access_points if missing."""
    existing = loc.get("access_points", [])
    if existing:
        return existing

    loc_type = infer_location_type(loc)
    return LOCATION_TYPE_ACCESS_POINTS.get(loc_type, [{"id": "main_entrance", "type": "door", "visibility": "public", "bypass_methods": []}])


def build_encounter_table(loc: dict[str, Any], templates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build encounter_table by matching location tags to template tags."""
    existing = loc.get("encounter_table", [])
    if existing and sum(e.get("weight", 1) for e in existing) > 0:
        return existing

    loc_tags = set(str(t).lower() for t in loc.get("tags", []))
    template_map = {t["id"]: set(str(tag).lower() for tag in t.get("tags", [])) for t in templates}

    matches = []
    for tid, ttags in template_map.items():
        overlap = loc_tags & ttags
        if overlap:
            matches.append({"template_id": tid, "weight": len(overlap)})

    # Sort by weight descending
    matches.sort(key=lambda x: x["weight"], reverse=True)

    # Ensure at least 3 entries
    if len(matches) < 3:
        # Add fallback templates if available
        fallback_ids = ["rebel_operative", "stormtrooper_patrol", "smuggler", "cantina_patron"]
        for fid in fallback_ids:
            if fid in template_map and not any(m["template_id"] == fid for m in matches):
                matches.append({"template_id": fid, "weight": 1})
            if len(matches) >= 3:
                break

    return matches[:5]  # Limit to top 5


def infer_voice_from_tags_role(tags: list[str], role: str | None) -> dict[str, str]:
    """Infer voice fields from tags and role."""
    tags_lower = [str(t).lower() for t in tags]

    # Check tags for role hints
    for tag in tags_lower:
        if tag in ROLE_VOICE_DEFAULTS:
            return ROLE_VOICE_DEFAULTS[tag].copy()

    # Check role
    if role:
        role_lower = role.lower()
        for key in ROLE_VOICE_DEFAULTS:
            if key in role_lower:
                return ROLE_VOICE_DEFAULTS[key].copy()

    return ROLE_VOICE_DEFAULTS["default"].copy()


def enrich_npc_voice(npc: dict[str, Any]) -> dict[str, str] | None:
    """Add voice metadata if missing."""
    # Check if already present
    voice_dict = npc.get("voice")
    if voice_dict and isinstance(voice_dict, dict):
        if all(k in voice_dict for k in ["belief", "wound", "taboo", "rhetorical_style", "tell"]):
            return None  # Already complete

    tags = npc.get("tags", [])
    role = npc.get("role")
    voice = infer_voice_from_tags_role(tags, role)
    return voice


def infer_spawn_rules(tags: list[str]) -> dict[str, Any] | None:
    """Infer spawn rules from tags."""
    tags_lower = [str(t).lower() for t in tags]

    for tag in tags_lower:
        if tag in TAG_SPAWN_RULES:
            return TAG_SPAWN_RULES[tag].copy()

    # Default for templates
    return {"location_tags_any": [], "location_types_any": [], "min_alert": 0, "max_alert": 100}


def enrich_npc_spawn(npc: dict[str, Any]) -> dict[str, Any] | None:
    """Add spawn rules if missing (for templates/rotating)."""
    if npc.get("spawn"):
        return None  # Already present

    tags = npc.get("tags", [])
    return infer_spawn_rules(tags)


# ══════════════════════════════════════════════════════════════════════════════
# STARTER CONTENT GENERATION
# ══════════════════════════════════════════════════════════════════════════════


def generate_starter_rumors(factions: list[dict[str, Any]], locations: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Generate 5-10 starter rumors."""
    rumors = [
        {
            "id": "rumor_death_star_plans",
            "text": "The Rebellion has stolen something from the Empire—plans that could turn the tide.",
            "tags": ["rebellion", "empire", "death_star"],
            "scope": "global",
            "credibility": "rumor",
        },
        {
            "id": "rumor_imperial_crackdown",
            "text": "Imperial patrols have doubled in the Outer Rim. Someone important is hunting someone.",
            "tags": ["empire", "hunt", "outer_rim"],
            "scope": "global",
            "credibility": "likely",
        },
        {
            "id": "rumor_yavin_base",
            "text": "There's a secret Rebel base hidden in the jungles of Yavin 4.",
            "tags": ["rebellion", "yavin", "base"],
            "scope": "global",
            "credibility": "rumor",
        },
        {
            "id": "rumor_hutt_smuggling",
            "text": "Jabba's smuggling routes are moving Imperial supplies to the black market.",
            "tags": ["hutt", "smuggling", "black_market"],
            "scope": "global",
            "credibility": "likely",
        },
        {
            "id": "rumor_bounty_hunters",
            "text": "A bounty hunter guild is offering high credits for information on Rebel sympathizers.",
            "tags": ["bounty_hunter", "credits", "rebellion"],
            "scope": "global",
            "credibility": "confirmed",
        },
    ]
    return rumors


def generate_starter_events(locations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Generate 2-3 starter events."""
    events = [
        {
            "id": "event_imperial_inspection",
            "type": "hard",
            "triggers": {"heat_global": {"min": 50}},
            "location_selector": {"tags_any": ["imperial", "checkpoint"]},
            "effects": {"heat_by_location": "+10"},
            "broadcast_rules": {"visible_to": "all"},
        },
        {
            "id": "event_patrol_increase",
            "type": "soft",
            "triggers": {"heat_by_location": {"min": 40}},
            "location_selector": {"tags_any": ["garrison", "spaceport"]},
            "effects": {"security_level": "+10"},
            "broadcast_rules": {"visible_to": "present"},
        },
    ]
    return events


def generate_starter_quest() -> dict[str, Any]:
    """Generate a minimal starter quest."""
    quest = {
        "id": "quest_first_contact",
        "title": "First Contact",
        "description": "Make contact with the local Rebel cell and prove yourself.",
        "entry_conditions": {"turn": {"min": 3}},
        "stages": [
            {
                "stage_id": "locate_contact",
                "objective": "Find the Rebel contact in the local cantina",
                "success_conditions": {"npc_met": "rebel_contact"},
            },
            {
                "stage_id": "prove_loyalty",
                "objective": "Complete a task to prove your loyalty to the Rebellion",
                "success_conditions": {"action_taken": "assist_rebellion"},
            },
            {
                "stage_id": "report_back",
                "objective": "Return to the contact and report your success",
                "success_conditions": {"npc_met": "rebel_contact", "stage_completed": "prove_loyalty"},
            },
        ],
        "consequences": {"reputation_rebel_alliance": "+10"},
    }
    return quest


def generate_starter_facts(factions: list[dict[str, Any]], locations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Generate starter facts linking factions to locations."""
    facts = []

    # Link Empire to garrisons
    imperial_locs = [loc["id"] for loc in locations if "imperial" in [str(t).lower() for t in loc.get("tags", [])]]
    if imperial_locs:
        facts.append({
            "id": "fact_empire_controls_garrisons",
            "subject": "galactic_empire",
            "predicate": "controls",
            "object": imperial_locs[0],
            "confidence": 1.0,
        })

    # Link Rebellion to bases
    rebel_locs = [loc["id"] for loc in locations if "rebel" in [str(t).lower() for t in loc.get("tags", [])]]
    if rebel_locs:
        facts.append({
            "id": "fact_rebellion_hides_yavin",
            "subject": "rebel_alliance",
            "predicate": "hides_in",
            "object": rebel_locs[0],
            "confidence": 0.8,
        })

    return facts


# ══════════════════════════════════════════════════════════════════════════════
# MIGRATION ORCHESTRATION
# ══════════════════════════════════════════════════════════════════════════════


def migrate_pack(pack_dir: Path, dry_run: bool = False) -> dict[str, Any]:
    """Migrate the Rebellion era pack to V2 schema."""
    report = {
        "locations_enriched": 0,
        "npcs_voice_added": 0,
        "npcs_spawn_added": 0,
        "rumors_created": 0,
        "events_created": 0,
        "quests_created": 0,
        "facts_created": 0,
        "manual_review_needed": [],
    }

    print(f"\n{'='*80}")
    print(f"MIGRATING: {pack_dir.name}")
    print(f"{'='*80}\n")

    # Load existing files
    locations_path = pack_dir / "locations.yaml"
    npcs_path = pack_dir / "npcs.yaml"
    rumors_path = pack_dir / "rumors.yaml"
    events_path = pack_dir / "events.yaml"
    quests_path = pack_dir / "quests.yaml"
    facts_path = pack_dir / "facts.yaml"
    factions_path = pack_dir / "factions.yaml"
    era_path = pack_dir / "era.yaml"

    locations_data = load_yaml(locations_path)
    npcs_data = load_yaml(npcs_path)
    rumors_data = load_yaml(rumors_path) if rumors_path.exists() else {"rumors": []}
    events_data = load_yaml(events_path) if events_path.exists() else {"events": []}
    quests_data = load_yaml(quests_path) if quests_path.exists() else {"quests": []}
    facts_data = load_yaml(facts_path) if facts_path.exists() else {"facts": []}
    factions_data = load_yaml(factions_path) if factions_path.exists() else {"factions": []}
    era_data = load_yaml(era_path)

    # Enrich locations
    print("-> Enriching locations...")
    templates = npcs_data.get("npcs", {}).get("templates", [])
    for loc in locations_data.get("locations", []):
        changed = False

        # Keywords
        new_keywords = enrich_location_keywords(loc)
        if new_keywords != loc.get("keywords", []):
            loc["keywords"] = new_keywords
            changed = True

        # Scene types
        new_scene_types = enrich_location_scene_types(loc)
        if new_scene_types != loc.get("scene_types", []):
            loc["scene_types"] = new_scene_types
            changed = True

        # Access points
        new_access_points = enrich_location_access_points(loc)
        if not loc.get("access_points"):
            loc["access_points"] = new_access_points
            changed = True

        # Encounter table
        new_encounter_table = build_encounter_table(loc, templates)
        if new_encounter_table:
            existing_weight = sum(e.get("weight", 1) for e in loc.get("encounter_table", []))
            if existing_weight == 0:
                loc["encounter_table"] = new_encounter_table
                changed = True

        if changed:
            report["locations_enriched"] += 1

    # Enrich NPCs (anchors + rotating)
    print("-> Enriching NPCs (anchors + rotating)...")
    for npc_list_name in ["anchors", "rotating"]:
        npc_list = npcs_data.get("npcs", {}).get(npc_list_name, [])
        for npc in npc_list:
            # Voice
            new_voice = enrich_npc_voice(npc)
            if new_voice:
                npc["voice"] = new_voice
                report["npcs_voice_added"] += 1
                report["manual_review_needed"].append(f"NPC {npc['id']}: voice fields auto-generated, review recommended")

            # Spawn (for rotating)
            if npc_list_name == "rotating":
                new_spawn = enrich_npc_spawn(npc)
                if new_spawn:
                    npc["spawn"] = new_spawn
                    report["npcs_spawn_added"] += 1

    # Enrich NPC templates
    print("-> Enriching NPC templates...")
    for template in templates:
        # Voice
        new_voice = enrich_npc_voice(template)
        if new_voice:
            template["voice"] = new_voice
            report["npcs_voice_added"] += 1
            report["manual_review_needed"].append(f"Template {template['id']}: voice fields auto-generated, review recommended")

        # Spawn
        new_spawn = enrich_npc_spawn(template)
        if new_spawn and not template.get("spawn"):
            template["spawn"] = new_spawn
            report["npcs_spawn_added"] += 1

    # Generate starter content if missing
    if not rumors_data.get("rumors"):
        print("-> Generating starter rumors...")
        rumors_data["rumors"] = generate_starter_rumors(factions_data.get("factions", []), locations_data.get("locations", []))
        report["rumors_created"] = len(rumors_data["rumors"])

    if not events_data.get("events"):
        print("-> Generating starter events...")
        events_data["events"] = generate_starter_events(locations_data.get("locations", []))
        report["events_created"] = len(events_data["events"])

    if not quests_data.get("quests"):
        print("-> Generating starter quest...")
        quests_data["quests"] = [generate_starter_quest()]
        report["quests_created"] = len(quests_data["quests"])

    if not facts_data.get("facts"):
        print("-> Generating starter facts...")
        facts_data["facts"] = generate_starter_facts(factions_data.get("factions", []), locations_data.get("locations", []))
        report["facts_created"] = len(facts_data["facts"])

    # Ensure era.yaml file_index is complete
    if "file_index" not in era_data:
        era_data["file_index"] = {}
    era_data["file_index"].update({
        "era": "era.yaml",
        "locations": "locations.yaml",
        "npcs": "npcs.yaml",
        "factions": "factions.yaml",
        "backgrounds": "backgrounds.yaml",
        "namebanks": "namebanks.yaml",
        "meters": "meters.yaml",
        "rumors": "rumors.yaml",
        "events": "events.yaml",
        "quests": "quests.yaml",
        "facts": "facts.yaml",
    })

    # Write files
    if not dry_run:
        print("\n-> Writing enriched files...")
        save_yaml(locations_path, locations_data)
        save_yaml(npcs_path, npcs_data)
        save_yaml(rumors_path, rumors_data)
        save_yaml(events_path, events_data)
        save_yaml(quests_path, quests_data)
        save_yaml(facts_path, facts_data)
        save_yaml(era_path, era_data)

    return report


def validate_pack(pack_dir: Path) -> list[str]:
    """Validate the migrated pack using Pydantic models."""
    print(f"\n{'='*80}")
    print(f"VALIDATING: {pack_dir.name}")
    print(f"{'='*80}\n")

    errors = []
    try:
        # Load by era name (directory name), not path
        pack = load_era_pack(pack_dir.name)
        print(f"+ Pack loaded successfully")
        print(f"  - Locations: {len(pack.locations)}")
        print(f"  - NPCs (anchors): {len(pack.npcs.anchors)}")
        print(f"  - NPCs (rotating): {len(pack.npcs.rotating)}")
        print(f"  - NPCs (templates): {len(pack.npcs.templates)}")
        print(f"  - Rumors: {len(pack.rumors)}")
        print(f"  - Events: {len(pack.events)}")
        print(f"  - Quests: {len(pack.quests)}")
        print(f"  - Facts: {len(pack.facts)}")

        # Check locations have required fields
        for loc in pack.locations:
            if not loc.keywords or len(loc.keywords) < 5:
                errors.append(f"Location {loc.id}: insufficient keywords (need 5+, have {len(loc.keywords)})")
            if not loc.scene_types:
                errors.append(f"Location {loc.id}: missing scene_types")
            if not loc.access_points:
                errors.append(f"Location {loc.id}: missing access_points")
            if not loc.encounter_table:
                errors.append(f"Location {loc.id}: missing encounter_table")

        # Check NPCs have voice fields
        for npc in pack.all_npcs():
            if not npc.voice:
                errors.append(f"NPC {npc.id}: missing voice field")

        # Check templates have voice + spawn
        for template in pack.npcs.templates:
            if not template.voice:
                errors.append(f"Template {template.id}: missing voice field")
            if not template.spawn:
                errors.append(f"Template {template.id}: missing spawn rules")

    except Exception as e:
        errors.append(f"Pack validation failed: {e}")

    if errors:
        print(f"\n- Validation errors found:")
        for err in errors:
            print(f"  - {err}")
    else:
        print(f"\n+ Validation passed")

    return errors


def print_report(report: dict[str, Any]) -> None:
    """Print migration report."""
    print(f"\n{'='*80}")
    print(f"MIGRATION REPORT")
    print(f"{'='*80}\n")
    print(f"Locations enriched:      {report['locations_enriched']}")
    print(f"NPCs voice added:        {report['npcs_voice_added']}")
    print(f"NPCs spawn added:        {report['npcs_spawn_added']}")
    print(f"Rumors created:          {report['rumors_created']}")
    print(f"Events created:          {report['events_created']}")
    print(f"Quests created:          {report['quests_created']}")
    print(f"Facts created:           {report['facts_created']}")

    if report["manual_review_needed"]:
        print(f"\n{'='*80}")
        print(f"MANUAL AUTHORING NEEDED ({len(report['manual_review_needed'])} items)")
        print(f"{'='*80}\n")
        for item in report["manual_review_needed"]:
            print(f"  - {item}")


def main():
    parser = argparse.ArgumentParser(description="Migrate Rebellion era pack to V2 schema")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing files")
    parser.add_argument("--report-only", action="store_true", help="Only print current state report")
    args = parser.parse_args()

    pack_dir = Path(__file__).parent.parent / "data" / "static" / "era_packs" / "rebellion"

    if not pack_dir.exists():
        print(f"ERROR: Pack directory not found: {pack_dir}")
        sys.exit(1)

    if args.report_only:
        validate_pack(pack_dir)
        return

    # Run migration
    report = migrate_pack(pack_dir, dry_run=args.dry_run)

    # Validate
    errors = validate_pack(pack_dir)

    # Print report
    print_report(report)

    if errors:
        print(f"\n! Migration completed with validation errors (see above)")
        sys.exit(1)
    else:
        print(f"\n+ Migration completed successfully")


if __name__ == "__main__":
    main()
