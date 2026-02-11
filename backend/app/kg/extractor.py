"""Core KG extraction logic: LLM-based entity/relationship extraction from chunks.

Uses the project's JSON reliability pattern (validate+retry+fallback) to
extract structured knowledge from novel text chunks.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from backend.app.core.agents.base import AgentLLM
from backend.app.core.json_reliability import call_with_json_reliability
from backend.app.kg.entity_resolution import resolve_entity_id, slugify
from backend.app.kg.predicates import VALID_PREDICATES, ENTITY_TYPES
from backend.app.kg.store import KGStore

logger = logging.getLogger(__name__)

# ── Prompt templates ──────────────────────────────────────────────────

EXTRACTION_SYSTEM_PROMPT = """\
You are a knowledge extraction system for Star Wars Legends novels.
Given text from a novel, extract structured knowledge as JSON.

Output ONLY valid JSON matching this schema:
{
  "entities": [
    {
      "name": "<full canonical name>",
      "entity_type": "<CHARACTER|LOCATION|FACTION|SHIP|ARTIFACT|EVENT>",
      "properties": {}
    }
  ],
  "relationships": [
    {
      "subject": "<entity name>",
      "predicate": "<relationship type from allowed list>",
      "object": "<entity name>",
      "context": "<1 sentence explaining this relationship>"
    }
  ],
  "chapter_summary": "<100-word synopsis of events in this passage>",
  "key_events": [
    {
      "name": "<event name>",
      "participants": ["<entity names>"],
      "location": "<where it happened>",
      "outcome": "<what happened>"
    }
  ]
}

Allowed relationship predicates: TRAINED_BY, TRAINS, FATHER_OF, MOTHER_OF, CHILD_OF, \
SIBLING_OF, MARRIED_TO, FRIEND_OF, RIVAL_OF, ENEMY_OF, APPRENTICE_OF, MASTER_OF, \
SERVES, COMMANDS, BETRAYED_BY, BETRAYS, RESCUED_BY, RESCUES, MEMBER_OF, LEADS, \
FOUNDED, LOCATED_ON, LOCATED_AT, HOMEWORLD_OF, CONTROLS, STATIONED_AT, TRAVELED_TO, \
PARTICIPATED_IN, INITIATED, CONCLUDED, ALLIED_WITH, OPPOSES, NEUTRAL_TO, SUBGROUP_OF, \
OWNS, PILOTS, BUILT.

For CHARACTER entities include: species, force_sensitive (boolean), faction, role.
For LOCATION entities include: location_type (planet/station/ship/building), region, controlling_faction.
For FACTION entities include: faction_type (government/military/criminal/religious), alignment (light/dark/neutral).

Rules:
- Extract ONLY facts explicitly stated or strongly implied in the text.
- Do NOT invent relationships or facts not present.
- Use the most complete version of each name (e.g., "Luke Skywalker" not just "Luke").
- If a character is referenced by a title/alias, still use their full name.
- Keep chapter_summary under 100 words.
- No markdown, no extra text. ONLY the JSON object.

Example output (abbreviated):
{"entities":[{"name":"Mara Jade","entity_type":"CHARACTER","properties":{"species":"Human","force_sensitive":true,"faction":"Empire","role":"Emperor's Hand"}},{"name":"Coruscant","entity_type":"LOCATION","properties":{"location_type":"planet","region":"Core Worlds","controlling_faction":"Galactic Empire"}}],"relationships":[{"subject":"Mara Jade","predicate":"SERVES","object":"Emperor Palpatine","context":"Mara Jade serves as the Emperor's Hand, carrying out his secret orders."}],"chapter_summary":"Mara Jade receives orders from the Emperor to eliminate a target on Coruscant.","key_events":[{"name":"Assassination Mission","participants":["Mara Jade"],"location":"Coruscant","outcome":"Mara receives her mission briefing and prepares to depart."}]}"""


def _build_user_prompt(
    book_title: str,
    chapter_title: str,
    era: str,
    known_characters: list[str],
    chunk_texts: list[str],
) -> str:
    """Build the user prompt for extraction."""
    chars_block = ", ".join(known_characters[:50]) if known_characters else "(none provided)"
    combined_text = "\n\n---\n\n".join(chunk_texts)
    return (
        f"Book: {book_title}\n"
        f"Chapter/Section: {chapter_title}\n"
        f"Era: {era}\n\n"
        f"Known characters in this era (use these canonical names when matching):\n"
        f"{chars_block}\n\n"
        f"Text to analyze:\n---\n{combined_text}\n---\n\n"
        f"Extract all entities, relationships, events, and provide a chapter summary. "
        f"Output ONLY valid JSON."
    )


# ── Result dataclass ──────────────────────────────────────────────────

@dataclass
class ExtractionResult:
    """Result of extracting knowledge from a batch of chunks."""
    entities: list[dict] = field(default_factory=list)
    triples: list[dict] = field(default_factory=list)
    chapter_summary: str = ""
    key_events: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ── Core extraction function ──────────────────────────────────────────

def extract_from_chunks(
    chunks: list[dict],
    book_title: str,
    chapter_title: str,
    era: str,
    llm: AgentLLM,
    alias_lookup: dict[str, str],
    known_characters: list[str] | None = None,
) -> ExtractionResult:
    """Extract entities, triples, and summaries from a batch of chunks.

    Uses json_mode with the project's JSON reliability pattern.

    Args:
        chunks: List of chunk dicts with 'text' key.
        book_title: Source book title.
        chapter_title: Chapter/section title.
        era: Era label (e.g., 'rebellion').
        llm: AgentLLM instance for the kg_extractor role.
        alias_lookup: Pre-built alias -> canonical_id mapping.
        known_characters: List of known character names for the prompt.

    Returns:
        ExtractionResult with entities, triples, chapter_summary.
    """
    chunk_texts = [c["text"] for c in chunks if c.get("text")]
    if not chunk_texts:
        return ExtractionResult(warnings=["No text in chunks"])

    known_characters = known_characters or []
    user_prompt = _build_user_prompt(book_title, chapter_title, era, known_characters, chunk_texts)
    warnings: list[str] = []

    def _fallback() -> dict:
        return {
            "entities": [],
            "relationships": [],
            "chapter_summary": "",
            "key_events": [],
        }

    try:
        raw_data = call_with_json_reliability(
            llm=llm,
            role="kg_extractor",
            agent_name="KGExtractor",
            campaign_id=None,
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            schema_class=None,  # raw dict validation
            validator_fn=_validate_extraction,
            fallback_fn=_fallback,
            max_retries=2,
            warnings=warnings,
        )
    except Exception:
        logger.exception("KG extraction failed for %s / %s", book_title, chapter_title)
        return ExtractionResult(warnings=["LLM extraction failed"])

    # Parse and normalize the raw data
    result = _normalize_extraction(raw_data, era, alias_lookup, book_title)
    result.warnings.extend(warnings)
    return result


def _validate_extraction(data: Any) -> tuple[bool, str]:
    """Validate raw extraction output structure."""
    if not isinstance(data, dict):
        return False, "Expected dict, got " + type(data).__name__
    if "entities" not in data:
        return False, "Missing 'entities' key"
    if not isinstance(data.get("entities"), list):
        return False, "'entities' must be a list"
    if not isinstance(data.get("relationships", []), list):
        return False, "'relationships' must be a list"
    return True, ""


def _normalize_extraction(
    raw: dict,
    era: str,
    alias_lookup: dict[str, str],
    book_title: str,
) -> ExtractionResult:
    """Normalize raw LLM output into ExtractionResult with resolved entity IDs."""
    entities: list[dict] = []
    triples: list[dict] = []
    warnings: list[str] = []

    # Build an entity name -> resolved_id cache for this batch
    entity_cache: dict[str, str] = {}

    # Process entities
    for raw_ent in raw.get("entities", []):
        if not isinstance(raw_ent, dict):
            continue
        name = str(raw_ent.get("name", "")).strip()
        if not name:
            continue
        entity_type = str(raw_ent.get("entity_type", "CHARACTER")).upper()
        if entity_type not in ENTITY_TYPES:
            entity_type = "CHARACTER"  # default

        entity_id = resolve_entity_id(name, entity_type, alias_lookup, entity_cache)
        entity_cache[name.lower()] = entity_id

        properties = raw_ent.get("properties", {})
        if not isinstance(properties, dict):
            properties = {}

        entities.append({
            "id": entity_id,
            "entity_type": entity_type,
            "canonical_name": name,
            "era": era,
            "properties": properties,
            "source_book": book_title,
        })

    # Process relationships
    for raw_rel in raw.get("relationships", []):
        if not isinstance(raw_rel, dict):
            continue
        subject_name = str(raw_rel.get("subject", "")).strip()
        predicate = str(raw_rel.get("predicate", "")).upper().strip()
        object_name = str(raw_rel.get("object", "")).strip()

        if not subject_name or not object_name or not predicate:
            continue

        # Normalize predicate
        if predicate not in VALID_PREDICATES:
            # Try to find closest match
            closest = _closest_predicate(predicate)
            if closest:
                predicate = closest
            else:
                warnings.append(f"Unknown predicate '{predicate}' for {subject_name} -> {object_name}")
                continue

        # Resolve entity IDs
        subject_id = resolve_entity_id(subject_name, "CHARACTER", alias_lookup, entity_cache)
        entity_cache[subject_name.lower()] = subject_id
        object_id = resolve_entity_id(object_name, "CHARACTER", alias_lookup, entity_cache)
        entity_cache[object_name.lower()] = object_id

        context = str(raw_rel.get("context", ""))

        triples.append({
            "subject_id": subject_id,
            "predicate": predicate,
            "object_id": object_id,
            "era": era,
            "source_book": book_title,
            "context": context,
        })

    # Process key_events as EVENT entities + participation triples
    for raw_event in raw.get("key_events", []):
        if not isinstance(raw_event, dict):
            continue
        event_name = str(raw_event.get("name", "")).strip()
        if not event_name:
            continue
        event_id = resolve_entity_id(event_name, "EVENT", alias_lookup, entity_cache)
        entity_cache[event_name.lower()] = event_id

        location = str(raw_event.get("location", ""))
        outcome = str(raw_event.get("outcome", ""))
        participants = raw_event.get("participants", [])
        if not isinstance(participants, list):
            participants = []

        entities.append({
            "id": event_id,
            "entity_type": "EVENT",
            "canonical_name": event_name,
            "era": era,
            "properties": {
                "location": location,
                "outcome": outcome,
                "participants": [str(p) for p in participants],
            },
            "source_book": book_title,
        })

        # Create PARTICIPATED_IN triples for each participant
        for participant in participants:
            p_name = str(participant).strip()
            if not p_name:
                continue
            p_id = resolve_entity_id(p_name, "CHARACTER", alias_lookup, entity_cache)
            entity_cache[p_name.lower()] = p_id
            triples.append({
                "subject_id": p_id,
                "predicate": "PARTICIPATED_IN",
                "object_id": event_id,
                "era": era,
                "source_book": book_title,
            })

    chapter_summary = str(raw.get("chapter_summary", ""))

    return ExtractionResult(
        entities=entities,
        triples=triples,
        chapter_summary=chapter_summary,
        key_events=raw.get("key_events", []),
        warnings=warnings,
    )


def store_extraction_result(
    result: ExtractionResult,
    store: KGStore,
    book_title: str,
    chapter_title: str,
    era: str,
    chapter_index: int = 0,
    source_chunk_ids: list[str] | None = None,
) -> None:
    """Persist extraction results to the KGStore."""
    chunk_id = source_chunk_ids[0] if source_chunk_ids else None

    # Build set of known entity IDs from this extraction
    known_ids = {ent["id"] for ent in result.entities}

    for ent in result.entities:
        store.upsert_entity(
            entity_id=ent["id"],
            entity_type=ent["entity_type"],
            canonical_name=ent["canonical_name"],
            era=ent["era"],
            properties=ent.get("properties"),
            source_book=ent.get("source_book", book_title),
        )

    # Ensure all triple endpoints exist as entities before inserting triples
    for triple in result.triples:
        for endpoint_id in (triple["subject_id"], triple["object_id"]):
            if endpoint_id not in known_ids and store.get_entity(endpoint_id) is None:
                # Create a stub entity so the foreign key is satisfied
                store.upsert_entity(
                    entity_id=endpoint_id,
                    entity_type="CHARACTER",  # default assumption
                    canonical_name=endpoint_id.replace("_", " ").title(),
                    era=era,
                    source_book=book_title,
                    confidence=0.5,  # low confidence for stub entities
                )
                known_ids.add(endpoint_id)

    for triple in result.triples:
        store.upsert_triple(
            subject_id=triple["subject_id"],
            predicate=triple["predicate"],
            object_id=triple["object_id"],
            era=triple["era"],
            source_book=triple.get("source_book", book_title),
            source_chunk_id=chunk_id,
            properties={"context": triple.get("context", "")},
        )

    if result.chapter_summary:
        store.add_summary(
            summary_type="CHAPTER",
            summary_text=result.chapter_summary,
            era=era,
            book_title=book_title,
            chapter_title=chapter_title,
            chapter_index=chapter_index,
        )


def _closest_predicate(candidate: str) -> str | None:
    """Find the closest valid predicate by simple substring matching."""
    candidate_clean = candidate.replace(" ", "_").replace("-", "_").upper()
    if candidate_clean in VALID_PREDICATES:
        return candidate_clean
    # Try partial matches
    for pred in VALID_PREDICATES:
        if candidate_clean in pred or pred in candidate_clean:
            return pred
    return None
