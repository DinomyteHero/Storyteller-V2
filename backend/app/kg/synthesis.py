"""Cross-book synthesis: merge and synthesize knowledge across all books.

Generates composite character profiles, location dossiers, and detects
contradictions in the extracted knowledge graph.
"""
from __future__ import annotations

import json
import logging

from backend.app.core.agents.base import AgentLLM
from backend.app.core.json_reliability import call_with_json_reliability
from backend.app.kg.store import KGStore
from backend.app.kg.predicates import PREDICATE_LABELS

logger = logging.getLogger(__name__)

_PROFILE_SYSTEM_PROMPT = """\
You are a Star Wars lore compiler. Given a character's known relationships, \
faction memberships, and chapter appearances, write a concise character arc summary.

Output ONLY valid JSON: {"summary": "<200-word character arc summary>"}

Rules:
- Only state facts supported by the provided data.
- Focus on relationships, motivations, and story progression.
- No speculation beyond what the data implies.
- No markdown, no extra text. ONLY the JSON object."""

_DOSSIER_SYSTEM_PROMPT = """\
You are a Star Wars lore compiler. Given a location's known properties, \
controlling factions, notable characters, and events, write a concise location dossier.

Output ONLY valid JSON: {"summary": "<150-word location dossier>"}

Rules:
- Only state facts supported by the provided data.
- Focus on atmosphere, strategic importance, and key activities.
- No speculation beyond what the data implies.
- No markdown, no extra text. ONLY the JSON object."""


def synthesize_character_profiles(
    store: KGStore,
    llm: AgentLLM | None,
    era: str,
) -> int:
    """Build composite character profiles from all book extractions.

    For each CHARACTER entity with enough data (>= 2 triples), generates a
    CHARACTER_ARC summary via LLM.

    Returns number of profiles generated.
    """
    characters = store.get_entities_by_type("CHARACTER", era=era)
    count = 0

    for char in characters:
        entity_id = char["id"]
        triples = store.get_triples_for_entity(entity_id, direction="both", era=era)
        if len(triples) < 2:
            continue

        # Check if summary already exists
        existing = store.get_summaries(summary_type="CHARACTER_ARC", entity_id=entity_id, era=era)
        if existing:
            continue

        properties = json.loads(char.get("properties_json", "{}"))
        source_books = json.loads(char.get("source_books_json", "[]"))

        # Build context for the LLM
        rel_lines = []
        for t in triples[:20]:
            pred_label = PREDICATE_LABELS.get(t["predicate"], t["predicate"].lower())
            if "object_name" in t:
                rel_lines.append(f"- {char['canonical_name']} {pred_label} {t['object_name']}")
            elif "subject_name" in t:
                rel_lines.append(f"- {t['subject_name']} {pred_label} {char['canonical_name']}")

        context = (
            f"Character: {char['canonical_name']}\n"
            f"Properties: {json.dumps(properties)}\n"
            f"Appears in: {', '.join(source_books[:10])}\n"
            f"Relationships:\n" + "\n".join(rel_lines)
        )

        if llm is None:
            # Deterministic fallback: concatenate facts
            summary = f"{char['canonical_name']} appears in {len(source_books)} sources. "
            summary += " ".join(rel_lines[:5])
        else:
            try:
                result = call_with_json_reliability(
                    llm=llm,
                    role="kg_extractor",
                    agent_name="KGSynthesizer",
                    campaign_id=None,
                    system_prompt=_PROFILE_SYSTEM_PROMPT,
                    user_prompt=context,
                    fallback_fn=lambda: {"summary": f"{char['canonical_name']}: data available but synthesis failed."},
                    max_retries=2,
                )
                summary = result.get("summary", "") if isinstance(result, dict) else str(result)
            except Exception:
                logger.exception("Character profile synthesis failed for %s", entity_id)
                summary = f"{char['canonical_name']}: synthesis failed."

        store.add_summary(
            summary_type="CHARACTER_ARC",
            summary_text=summary,
            era=era,
            entity_id=entity_id,
            metadata={"source_books": source_books, "triple_count": len(triples)},
        )
        count += 1

    return count


def synthesize_location_dossiers(
    store: KGStore,
    llm: AgentLLM | None,
    era: str,
) -> int:
    """Build location dossiers from all mentions across books.

    Returns number of dossiers generated.
    """
    locations = store.get_entities_by_type("LOCATION", era=era)
    count = 0

    for loc in locations:
        entity_id = loc["id"]
        triples = store.get_triples_for_entity(entity_id, direction="both", era=era)

        # Check if dossier already exists
        existing = store.get_summaries(summary_type="LOCATION_DOSSIER", entity_id=entity_id, era=era)
        if existing:
            continue

        properties = json.loads(loc.get("properties_json", "{}"))
        source_books = json.loads(loc.get("source_books_json", "[]"))

        # Build context
        rel_lines = []
        for t in triples[:15]:
            pred_label = PREDICATE_LABELS.get(t["predicate"], t["predicate"].lower())
            if "object_name" in t:
                rel_lines.append(f"- {loc['canonical_name']} {pred_label} {t['object_name']}")
            elif "subject_name" in t:
                rel_lines.append(f"- {t['subject_name']} {pred_label} {loc['canonical_name']}")

        context = (
            f"Location: {loc['canonical_name']}\n"
            f"Properties: {json.dumps(properties)}\n"
            f"Appears in: {', '.join(source_books[:10])}\n"
            f"Associations:\n" + "\n".join(rel_lines) if rel_lines else "(no associations)"
        )

        if llm is None:
            summary = f"{loc['canonical_name']}: {json.dumps(properties)}"
        else:
            try:
                result = call_with_json_reliability(
                    llm=llm,
                    role="kg_extractor",
                    agent_name="KGSynthesizer",
                    campaign_id=None,
                    system_prompt=_DOSSIER_SYSTEM_PROMPT,
                    user_prompt=context,
                    fallback_fn=lambda: {"summary": f"{loc['canonical_name']}: data available but synthesis failed."},
                    max_retries=2,
                )
                summary = result.get("summary", "") if isinstance(result, dict) else str(result)
            except Exception:
                logger.exception("Location dossier synthesis failed for %s", entity_id)
                summary = f"{loc['canonical_name']}: synthesis failed."

        store.add_summary(
            summary_type="LOCATION_DOSSIER",
            summary_text=summary,
            era=era,
            entity_id=entity_id,
            metadata={"source_books": source_books, "properties": properties},
        )
        count += 1

    return count


def detect_contradictions(store: KGStore, era: str) -> list[dict]:
    """Find contradictions in the KG.

    Checks:
    - Character with multiple conflicting faction memberships
    - Location with conflicting controlling factions

    Returns list of {entity_id, field, values, source_books}.
    """
    contradictions = []

    # Check characters with multiple MEMBER_OF triples to different factions
    characters = store.get_entities_by_type("CHARACTER", era=era)
    for char in characters:
        triples = store.get_triples_for_entity(char["id"], direction="outgoing", era=era)
        member_of = [t for t in triples if t["predicate"] == "MEMBER_OF"]
        if len(member_of) > 1:
            factions = list({t.get("object_name", t["object_id"]) for t in member_of})
            if len(factions) > 1:
                contradictions.append({
                    "entity_id": char["id"],
                    "entity_name": char["canonical_name"],
                    "field": "faction_membership",
                    "values": factions,
                    "note": "Character belongs to multiple factions (may be intentional for double agents)",
                })

    # Check locations with conflicting controlling_faction in properties
    locations = store.get_entities_by_type("LOCATION", era=era)
    for loc in locations:
        triples = store.get_triples_for_entity(loc["id"], direction="both", era=era)
        controls = [t for t in triples if t["predicate"] == "CONTROLS"]
        if len(controls) > 1:
            controllers = list({
                t.get("subject_name", t["subject_id"]) for t in controls
            })
            if len(controllers) > 1:
                contradictions.append({
                    "entity_id": loc["id"],
                    "entity_name": loc["canonical_name"],
                    "field": "controlling_faction",
                    "values": controllers,
                    "note": "Location controlled by multiple factions (may be contested)",
                })

    return contradictions
