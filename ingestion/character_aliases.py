"""Deterministic character extraction from text via user-editable alias mapping.

Loads data/character_aliases.yml (or path from CHARACTER_ALIASES_PATH env).
Maps display names/aliases to canonical IDs using word-boundary regex.
If alias file is missing or invalid: fallback to empty list (do not guess).
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

DEFAULT_ALIAS_PATH = "./data/character_aliases.yml"
ENV_ALIAS_PATH = "CHARACTER_ALIASES_PATH"

_alias_cache: list[tuple[re.Pattern, str]] | None = None


def _get_alias_path() -> Path:
    """Resolve alias file path from env or default."""
    raw = os.environ.get(ENV_ALIAS_PATH, "").strip()
    if raw:
        return Path(raw)
    root = Path(__file__).resolve().parents[1]
    return root / "data" / "character_aliases.yml"


def _compile_pattern(alias: str) -> re.Pattern:
    """Build case-insensitive regex with word boundaries to avoid partial matches (e.g. Lukewarm)."""
    # Escape regex metacharacters in the alias
    escaped = re.escape(alias)
    # Replace spaces with \s+ to allow flexible whitespace between words.
    # re.escape turns " " into "\\ " (backslash-space); replace that sequence.
    escaped = escaped.replace("\\ ", "\\s+")
    pattern = rf"\b{escaped}\b"
    return re.compile(pattern, re.IGNORECASE)


def _load_aliases() -> list[tuple[re.Pattern, str]]:
    """Load alias file and compile patterns. Returns [(pattern, canonical_id), ...]."""
    global _alias_cache
    if _alias_cache is not None:
        return _alias_cache

    path = _get_alias_path()
    if not path.exists():
        logger.debug("Character alias file not found at %s; using empty character list.", path)
        return []

    try:
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Failed to load character aliases from %s: %s; using empty list.", path, e)
        return []

    if not isinstance(data, dict):
        logger.warning("Character aliases file must be a mapping; got %s. Using empty list.", type(data).__name__)
        return []

    result: list[tuple[re.Pattern, str]] = []
    for canonical_id, aliases in data.items():
        if not isinstance(canonical_id, str) or not canonical_id.strip():
            continue
        if not isinstance(aliases, (list, tuple)):
            continue
        for a in aliases:
            if isinstance(a, str) and a.strip():
                try:
                    pat = _compile_pattern(a.strip())
                    result.append((pat, canonical_id.strip()))
                except re.error as e:
                    logger.warning("Invalid alias pattern for %r: %s; skipping.", a, e)

    _alias_cache = result
    return result


def get_canonical_ids() -> List[str]:
    """Return list of canonical character IDs from alias file."""
    patterns = _load_aliases()
    seen: set[str] = set()
    ids: list[str] = []
    for _pat, cid in patterns:
        if cid not in seen:
            seen.add(cid)
            ids.append(cid)
    return ids


def extract_characters(text: str) -> List[str]:
    """
    Extract canonical character IDs from text using the alias mapping.

    Uses word-boundary matching (case-insensitive) so "Luke" matches but "Lukewarm" does not.
    Returns unique canonical IDs in the order first seen.

    If alias file is missing or invalid, returns [].
    """
    if not text or not text.strip():
        return []

    patterns = _load_aliases()
    if not patterns:
        return []

    seen: set[str] = set()
    order: list[str] = []
    for pat, canonical_id in patterns:
        if canonical_id in seen:
            continue
        if pat.search(text):
            seen.add(canonical_id)
            order.append(canonical_id)

    return order


def reload_aliases() -> None:
    """Clear cached aliases so next extract_characters reloads from disk."""
    global _alias_cache
    _alias_cache = None
