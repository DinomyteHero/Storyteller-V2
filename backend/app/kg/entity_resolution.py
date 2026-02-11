"""Entity resolution for Knowledge Graph extraction.

Deduplicates entity names across chapters and books by resolving to canonical IDs
using character_aliases.yml and fuzzy matching.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path

logger = logging.getLogger(__name__)

_ALIASES_PATH = Path("./data/character_aliases.yml")


def build_alias_lookup(aliases_path: str | Path | None = None) -> dict[str, str]:
    """Load character_aliases.yml and build a lowercase alias -> canonical_id mapping.

    Returns:
        Dict like {"luke": "luke_skywalker", "luke skywalker": "luke_skywalker", ...}
    """
    path = Path(aliases_path) if aliases_path else _ALIASES_PATH
    if not path.exists():
        logger.warning("Character aliases file not found at %s", path)
        return {}
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            return {}
        lookup: dict[str, str] = {}
        for canonical_id, aliases in data.items():
            canonical_id = str(canonical_id).strip()
            # Also add the canonical_id itself (with underscores replaced)
            lookup[canonical_id.lower()] = canonical_id
            lookup[canonical_id.replace("_", " ").lower()] = canonical_id
            if not isinstance(aliases, list):
                continue
            for alias in aliases:
                alias_lower = str(alias).strip().lower()
                if alias_lower:
                    lookup[alias_lower] = canonical_id
        return lookup
    except Exception:
        logger.exception("Failed to load character aliases from %s", path)
        return {}


def slugify(name: str) -> str:
    """Generate a slug ID from an entity name.

    Examples:
        "Luke Skywalker" -> "luke_skywalker"
        "Mos Eisley Cantina" -> "mos_eisley_cantina"
        "AT-AT Walker" -> "at_at_walker"
    """
    # Normalize unicode
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    # Lowercase
    name = name.lower()
    # Replace hyphens and spaces with underscores
    name = re.sub(r"[-\s]+", "_", name)
    # Remove non-alphanumeric (keep underscores)
    name = re.sub(r"[^a-z0-9_]", "", name)
    # Collapse multiple underscores
    name = re.sub(r"_+", "_", name)
    return name.strip("_")


def resolve_entity_id(
    name: str,
    entity_type: str,
    alias_lookup: dict[str, str],
    existing_entities: dict[str, str] | None = None,
) -> str:
    """Resolve an entity name to a canonical ID.

    Priority:
    1. Exact match in character_aliases.yml (for CHARACTER type)
    2. Exact match in existing_entities cache
    3. Fuzzy match (Levenshtein <= 2) against existing entities
    4. Generate new slug: slugify(name)

    Args:
        name: Raw entity name from LLM extraction.
        entity_type: Entity type (CHARACTER, LOCATION, etc.).
        alias_lookup: Pre-built lowercase alias -> canonical_id mapping.
        existing_entities: Cache of name_lower -> entity_id for already-seen entities.

    Returns:
        Canonical entity ID string.
    """
    name_clean = name.strip()
    name_lower = name_clean.lower()
    existing_entities = existing_entities or {}

    # 1. Alias lookup (works for any entity type but primarily for characters)
    if name_lower in alias_lookup:
        return alias_lookup[name_lower]

    # 2. Exact match in existing entity cache
    if name_lower in existing_entities:
        return existing_entities[name_lower]

    # 3. Fuzzy match against existing entities (Levenshtein <= 2)
    slug = slugify(name_clean)
    for cached_name, cached_id in existing_entities.items():
        if _levenshtein(name_lower, cached_name) <= 2:
            return cached_id
    # Also check slug against existing cache values
    for cached_name, cached_id in existing_entities.items():
        if slugify(cached_name) == slug:
            return cached_id

    # 4. Generate new slug
    return slug


def merge_entity_properties(existing: dict, new: dict) -> dict:
    """Merge properties from a new extraction into existing entity properties.

    Strategy: union lists, keep most specific scalar (non-empty wins).
    """
    merged = dict(existing)
    for key, value in new.items():
        if key not in merged or merged[key] is None:
            merged[key] = value
            continue
        old = merged[key]
        if isinstance(old, list) and isinstance(value, list):
            # Union preserving order
            merged[key] = list(dict.fromkeys(old + value))
        elif not old and value:
            # New value is more specific
            merged[key] = value
        # Otherwise keep existing (first-seen wins for scalars)
    return merged


def _levenshtein(s1: str, s2: str) -> int:
    """Compute Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Cost is 0 if characters match, 1 otherwise
            cost = 0 if c1 == c2 else 1
            curr_row.append(min(
                curr_row[j] + 1,        # insertion
                prev_row[j + 1] + 1,    # deletion
                prev_row[j] + cost,      # substitution
            ))
        prev_row = curr_row
    return prev_row[-1]
