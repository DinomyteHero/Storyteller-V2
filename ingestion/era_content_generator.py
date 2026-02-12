"""Generate era pack YAML content from ingested lore corpus.

Hybrid pipeline: deterministic extraction + optional LLM synthesis.
Outputs quest, companion, NPC, and location YAML for human review.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ── Genre keyword banks (reused from style_pack_builder) ──────────
GENRE_KEYWORDS = {
    "political_thriller": {"senate", "politics", "diplomat", "council", "chancellor"},
    "military_tactical": {"fleet", "squad", "battle", "strategy", "command"},
    "noir_detective": {"investigate", "clue", "informant", "shadow", "alley"},
    "space_western": {"outpost", "frontier", "cantina", "bounty", "dust"},
    "mythic_quest": {"prophecy", "destiny", "artifact", "pilgrimage", "trial"},
    "espionage": {"spy", "agent", "infiltrate", "intelligence", "covert"},
    "heist": {"vault", "plan", "crew", "security", "score"},
}

# ── Companion archetypes for diversity ────────────────────────────
COMPANION_ARCHETYPES = [
    {"role": "soldier", "role_in_party": "companion", "voice_style": "blunt"},
    {"role": "diplomat", "role_in_party": "specialist", "voice_style": "socratic"},
    {"role": "scoundrel", "role_in_party": "specialist", "voice_style": "sardonic"},
    {"role": "medic", "role_in_party": "companion", "voice_style": "empathetic"},
    {"role": "technician", "role_in_party": "specialist", "voice_style": "analytical"},
    {"role": "scout", "role_in_party": "specialist", "voice_style": "laconic"},
    {"role": "force_sensitive", "role_in_party": "mentor", "voice_style": "cryptic"},
]

# ── Quest templates by genre ─────────────────────────────────────
QUEST_TEMPLATES = {
    "rescue": {
        "description_template": "A {target} has been captured by {antagonist}. Mount a rescue before it's too late.",
        "stages": ["receive_intel", "locate_captive", "plan_approach", "execute_rescue", "exfiltrate"],
    },
    "espionage": {
        "description_template": "An intelligence source offers {prize} in exchange for {cost}. Verify the source and extract the data.",
        "stages": ["receive_contact", "verify_source", "make_exchange", "escape_pursuit", "deliver_intel"],
    },
    "sabotage": {
        "description_template": "A {target_facility} threatens {ally] operations. Destroy it, but consider the cost to civilians.",
        "stages": ["briefing", "reconnaissance", "recruit_support", "execute_operation", "escape"],
    },
    "smuggling": {
        "description_template": "Critical supplies are trapped behind a blockade. Find a way to move the cargo before {antagonist} seizes it.",
        "stages": ["find_smuggler", "locate_cargo", "handle_opposition", "deliver_cargo"],
    },
    "diplomacy": {
        "description_template": "Two factions teeter on the edge of conflict. Broker peace — or choose a side.",
        "stages": ["learn_dispute", "meet_faction_a", "meet_faction_b", "negotiate_or_fight", "report_outcome"],
    },
    "mystery": {
        "description_template": "Someone is dead and the truth is buried. Investigate the scene, question suspects, and expose the killer.",
        "stages": ["discover_crime", "examine_scene", "interrogate_suspects", "confront_culprit", "decide_fate"],
    },
    "exploration": {
        "description_template": "An ancient site holds secrets worth dying for. Navigate its dangers and decide what to do with what you find.",
        "stages": ["hear_rumor", "travel_to_site", "navigate_dangers", "discover_secret", "decide_fate"],
    },
    "loyalty": {
        "description_template": "A companion's past catches up with them. Help them face it — or let the past die.",
        "stages": ["receive_distress", "investigate_past", "confront_threat", "make_choice", "aftermath"],
    },
}


@dataclass
class GeneratedContent:
    """Container for generated era pack content."""
    quests: list[dict] = field(default_factory=list)
    companions: list[dict] = field(default_factory=list)
    npcs: list[dict] = field(default_factory=list)
    locations: list[dict] = field(default_factory=list)
    manifest: dict = field(default_factory=dict)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "unknown"


def _retrieve_lore_context(era: str, query: str, top_k: int = 10, db_path: str | None = None) -> list[dict]:
    """Retrieve lore chunks from LanceDB for context."""
    try:
        from backend.app.rag.lore_retriever import retrieve_lore
        return retrieve_lore(query, top_k=top_k, era=era, db_path=db_path)
    except Exception as e:
        logger.warning("Failed to retrieve lore context: %s", e)
        return []


def _extract_entities_from_chunks(chunks: list[dict]) -> dict[str, list[str]]:
    """Extract entity mentions from lore chunks using simple NER heuristics."""
    characters: set[str] = set()
    locations: set[str] = set()
    factions: set[str] = set()

    # Simple heuristic: look for capitalized multi-word names
    name_pattern = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b")

    for chunk in chunks:
        text = chunk.get("text", "")
        matches = name_pattern.findall(text)
        for m in matches:
            words = m.split()
            if len(words) == 2:
                characters.add(m)
            elif len(words) >= 3:
                # Longer names are more likely locations or factions
                if any(w.lower() in ("planet", "system", "city", "base", "temple", "palace") for w in words):
                    locations.add(m)
                elif any(w.lower() in ("alliance", "empire", "guild", "order", "syndicate", "cartel") for w in words):
                    factions.add(m)
                else:
                    characters.add(m)

    return {
        "characters": sorted(characters)[:20],
        "locations": sorted(locations)[:15],
        "factions": sorted(factions)[:10],
    }


def _detect_genre(chunks: list[dict]) -> list[str]:
    """Detect dominant genres from lore chunks via keyword frequency."""
    scores: dict[str, int] = {g: 0 for g in GENRE_KEYWORDS}
    for chunk in chunks:
        words = set(re.findall(r"[a-z]+", chunk.get("text", "").lower()))
        for genre, keys in GENRE_KEYWORDS.items():
            scores[genre] += len(words & keys)
    return [g for g, s in sorted(scores.items(), key=lambda x: -x[1]) if s > 0][:3]


def _generate_quest_deterministic(
    quest_id: str,
    template_key: str,
    era: str,
    turn_min: int = 5,
    turn_max: int = 40,
    context_hints: list[str] | None = None,
) -> dict:
    """Generate a quest definition from a template."""
    template = QUEST_TEMPLATES.get(template_key)
    if not template:
        template = QUEST_TEMPLATES["rescue"]

    stages = []
    for i, stage_id in enumerate(template["stages"]):
        stage: dict[str, Any] = {
            "stage_id": stage_id,
            "objective": f"[AUTHOR: Write objective for stage '{stage_id}']",
            "success_conditions": {"action_taken": stage_id},
        }
        if i > 0:
            stage["success_conditions"]["stage_completed"] = template["stages"][i - 1]
        stages.append(stage)

    quest = {
        "id": quest_id,
        "title": f"[AUTHOR: Write title for {template_key} quest]",
        "description": template["description_template"],
        "entry_conditions": {"turn": {"min": turn_min, "max": turn_max}},
        "stages": stages,
        "consequences": {"reputation_rebel_alliance": "+10"},
    }

    if context_hints:
        quest["_generation_context"] = context_hints[:3]

    return quest


def _generate_companion_deterministic(
    comp_id: str,
    archetype: dict,
    era: str,
    species: str = "Human",
) -> dict:
    """Generate a companion definition scaffold."""
    role = archetype["role"]
    return {
        "id": comp_id,
        "name": f"[AUTHOR: Name for {role}]",
        "species": species,
        "gender": "[AUTHOR: gender]",
        "archetype": f"[AUTHOR: {role} archetype description]",
        "faction_id": "[AUTHOR: faction_id]",
        "role_in_party": archetype["role_in_party"],
        "voice_tags": [archetype["voice_style"], "[AUTHOR: add 2 more tags]"],
        "motivation": f"[AUTHOR: Write motivation for {role}]",
        "speech_quirk": f"[AUTHOR: Write speech quirk for {role}]",
        "voice": {
            "belief": f"[AUTHOR: Core belief for {role}]",
            "wound": f"[AUTHOR: Formative wound for {role}]",
            "taboo": f"[AUTHOR: Personal taboo for {role}]",
            "rhetorical_style": archetype["voice_style"],
            "tell": f"[AUTHOR: Physical/verbal mannerism for {role}]",
        },
        "traits": {
            "idealist_pragmatic": 0,
            "merciful_ruthless": 0,
            "lawful_rebellious": 0,
        },
        "default_affinity": 0,
        "recruitment": {
            "unlock_conditions": f"[AUTHOR: How player meets {role}]",
            "first_meeting_location": "[AUTHOR: location_id]",
        },
        "tags": [role, "[AUTHOR: add tags]"],
        "enables_affordances": ["[AUTHOR: list affordances]"],
        "blocks_affordances": [],
        "influence": {
            "starts_at": 0,
            "min": -100,
            "max": 100,
            "triggers": [
                {"intent": "threaten", "delta": -3},
                {"intent": "help", "delta": 2},
            ],
        },
        "banter": {
            "frequency": "normal",
            "style": archetype["voice_style"],
            "triggers": [role, "[AUTHOR: add banter triggers]"],
        },
        "personal_quest_id": None,
        "metadata": {
            "loyalty_hook": f"[AUTHOR: loyalty hook for {role}]",
            "recruitment_context": f"[AUTHOR: recruitment scene for {role}]",
            "banter_style": archetype["voice_style"],
            "faction_interest": ["[AUTHOR: faction interests]"],
        },
    }


def _llm_enrich_quest(quest: dict, lore_context: str, *, role: str = "ingestion_tagger") -> dict:
    """Use LLM to fill in [AUTHOR:] placeholders with creative content."""
    try:
        from backend.app.core.agents.base import AgentLLM
        llm = AgentLLM(role)
        sys_prompt = (
            "You are a senior game narrative designer for a Star Wars RPG. "
            "Given a quest template with [AUTHOR:] placeholders and lore context, "
            "fill in all placeholders with compelling, era-appropriate content. "
            "Output valid YAML. Preserve the structure exactly."
        )
        user_prompt = f"LORE CONTEXT:\n{lore_context[:3000]}\n\nQUEST TEMPLATE:\n{yaml.dump(quest, default_flow_style=False)}"
        raw = llm.complete(sys_prompt, user_prompt, json_mode=False)
        if raw:
            text = str(raw).strip()
            # Try to parse as YAML
            if text.startswith("{") or text.startswith("-"):
                parsed = yaml.safe_load(text)
                if isinstance(parsed, dict) and "id" in parsed:
                    return parsed
    except Exception as e:
        logger.warning("LLM quest enrichment failed: %s", e)
    return quest


def _llm_enrich_companion(companion: dict, lore_context: str, *, role: str = "ingestion_tagger") -> dict:
    """Use LLM to fill in [AUTHOR:] placeholders with creative content."""
    try:
        from backend.app.core.agents.base import AgentLLM
        llm = AgentLLM(role)
        sys_prompt = (
            "You are a senior game narrative designer for a Star Wars RPG. "
            "Given a companion template with [AUTHOR:] placeholders and lore context, "
            "fill in all placeholders with a compelling, era-appropriate character. "
            "Give them a memorable name, distinct voice, and personal stakes. "
            "Output valid YAML. Preserve the structure exactly."
        )
        user_prompt = f"LORE CONTEXT:\n{lore_context[:3000]}\n\nCOMPANION TEMPLATE:\n{yaml.dump(companion, default_flow_style=False)}"
        raw = llm.complete(sys_prompt, user_prompt, json_mode=False)
        if raw:
            text = str(raw).strip()
            if text.startswith("{") or text.startswith("-"):
                parsed = yaml.safe_load(text)
                if isinstance(parsed, dict) and "id" in parsed:
                    return parsed
    except Exception as e:
        logger.warning("LLM companion enrichment failed: %s", e)
    return companion


def generate_era_content(
    *,
    era: str,
    output_dir: Path,
    num_quests: int = 6,
    num_companions: int = 4,
    use_llm: bool = False,
    llm_role: str = "ingestion_tagger",
    db_path: str | None = None,
    dry_run: bool = False,
) -> GeneratedContent:
    """Generate era pack content scaffolds from ingested lore.

    Args:
        era: Era identifier (e.g. "REBELLION", "LEGACY")
        output_dir: Where to write the generated YAML files
        num_quests: Number of quests to generate
        num_companions: Number of companions to generate
        use_llm: Whether to use LLM for enriching placeholders
        llm_role: LLM role for enrichment
        db_path: Path to LanceDB (uses default if not specified)
        dry_run: Preview without writing files

    Returns:
        GeneratedContent with all generated items
    """
    result = GeneratedContent()
    era_slug = _slug(era)

    # ── Retrieve lore context ─────────────────────────────────────
    lore_chunks = _retrieve_lore_context(era, f"{era} characters locations factions", top_k=20, db_path=db_path)
    entities = _extract_entities_from_chunks(lore_chunks)
    genres = _detect_genre(lore_chunks)
    lore_text = "\n".join(c.get("text", "")[:500] for c in lore_chunks[:10])

    logger.info(
        "Era content generation: era=%s, chunks=%d, characters=%d, locations=%d, genres=%s",
        era, len(lore_chunks), len(entities["characters"]), len(entities["locations"]), genres,
    )

    # ── Generate quests ───────────────────────────────────────────
    template_keys = list(QUEST_TEMPLATES.keys())
    for i in range(num_quests):
        template_key = template_keys[i % len(template_keys)]
        quest_id = f"gen_quest_{era_slug}_{template_key}_{i + 1}"
        turn_min = 3 + (i * 7)
        turn_max = turn_min + 25

        quest = _generate_quest_deterministic(
            quest_id=quest_id,
            template_key=template_key,
            era=era,
            turn_min=turn_min,
            turn_max=turn_max,
            context_hints=entities["characters"][:3],
        )

        if use_llm and lore_text:
            quest = _llm_enrich_quest(quest, lore_text, role=llm_role)

        result.quests.append(quest)

    # ── Generate companions ───────────────────────────────────────
    species_pool = ["Human", "Twi'lek", "Rodian", "Zabrak", "Bothan", "Chiss", "Wookiee"]
    for i in range(num_companions):
        archetype = COMPANION_ARCHETYPES[i % len(COMPANION_ARCHETYPES)]
        comp_id = f"gen_comp_{era_slug}_{archetype['role']}_{i + 1}"
        species = species_pool[i % len(species_pool)]

        companion = _generate_companion_deterministic(
            comp_id=comp_id,
            archetype=archetype,
            era=era,
            species=species,
        )

        if use_llm and lore_text:
            companion = _llm_enrich_companion(companion, lore_text, role=llm_role)

        result.companions.append(companion)

    # ── Build manifest ────────────────────────────────────────────
    result.manifest = {
        "era": era,
        "lore_chunks_used": len(lore_chunks),
        "entities_detected": {k: len(v) for k, v in entities.items()},
        "genres_detected": genres,
        "quests_generated": len(result.quests),
        "companions_generated": len(result.companions),
        "llm_used": use_llm,
    }

    # ── Write output ──────────────────────────────────────────────
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

        quests_path = output_dir / "generated_quests.yaml"
        quests_path.write_text(
            yaml.dump({"quests": result.quests}, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        companions_path = output_dir / "generated_companions.yaml"
        companions_path.write_text(
            yaml.dump({"companions": result.companions}, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        manifest_path = output_dir / "_generation_manifest.json"
        manifest_path.write_text(json.dumps(result.manifest, indent=2), encoding="utf-8")

        logger.info("Generated content written to %s", output_dir)

    return result
