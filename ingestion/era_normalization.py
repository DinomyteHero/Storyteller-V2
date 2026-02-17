"""Era normalization helpers for ingestion and UI-key canonicalization."""
from __future__ import annotations

import logging
import os

from ingestion.era_aliases import normalize_segment

logger = logging.getLogger(__name__)

UI_ERA_KEYS = {
    "ERA_AGNOSTIC",
    "OLD_REPUBLIC",
    "HIGH_REPUBLIC",
    "CLONE_WARS",
    "REBELLION",
    "NEW_REPUBLIC",
    "LEGACY",
    "CUSTOM",
}

_STOPWORDS = {"era", "the", "of"}

_UI_KEY_ALIASES = {
    # Legacy / common variants
    "lotf": "LEGACY",
    "legacy": "LEGACY",
    "legacy_of_the_force": "LEGACY",
    "legacy_era": "LEGACY",
    "new_jedi_order": "NEW_REPUBLIC",
    "njo": "NEW_REPUBLIC",
    "new_republic": "NEW_REPUBLIC",
    "new_republic_era": "NEW_REPUBLIC",
    "rebellion": "REBELLION",
    "rebellion_era": "REBELLION",
    "galactic_civil_war": "REBELLION",
    "clone_wars": "CLONE_WARS",
    "rise_of_the_empire": "CLONE_WARS",
    "rise_of_the_empire_era": "CLONE_WARS",
    "old_republic": "OLD_REPUBLIC",
    "old_galactic_republic": "OLD_REPUBLIC",
    "old_galactic_republic_era": "OLD_REPUBLIC",
    "high_republic": "HIGH_REPUBLIC",
    "era_agnostic": "ERA_AGNOSTIC",
    "agnostic": "ERA_AGNOSTIC",
}

_LEGACY_LABELS = {
    "ERA_AGNOSTIC": "ERA_AGNOSTIC",
    "OLD_REPUBLIC": "Old Republic",
    "HIGH_REPUBLIC": "High Republic",
    "CLONE_WARS": "Clone Wars",
    "REBELLION": "Rebellion",
    "NEW_REPUBLIC": "New Republic",
    "LEGACY": "LOTF",
    "CUSTOM": "CUSTOM",
}


def normalize_era_segment(text: str) -> str:
    """Normalize a segment for era matching (lowercase + underscores)."""
    return normalize_segment(text)


def era_variants(text: str) -> set[str]:
    """Generate normalized variants for era matching (strip stopwords, trailing '_era')."""
    base = normalize_era_segment(text)
    if not base:
        return set()
    variants = {base}
    if base.endswith("_era"):
        variants.add(base[: -len("_era")])
    tokens = [t for t in base.split("_") if t]
    if tokens and tokens[-1] == "era":
        variants.add("_".join(tokens[:-1]))
    if tokens:
        filtered = [t for t in tokens if t not in _STOPWORDS]
        if filtered:
            variants.add("_".join(filtered))
    return {v for v in variants if v}


def canonicalize_to_ui_era_key(value: str | None) -> str | None:
    """Map an era string to a UI era key. Returns None if unknown."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    upper = raw.upper()
    if upper in UI_ERA_KEYS:
        return upper
    for v in era_variants(raw):
        key = _UI_KEY_ALIASES.get(v)
        if key:
            return key
    return None


def canonicalize_to_legacy_era_label(value: str | None) -> str | None:
    """Map UI era key (or known variant) to legacy label used by ingestion outputs."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    upper = raw.upper()
    if upper in _LEGACY_LABELS:
        return _LEGACY_LABELS[upper]
    key = canonicalize_to_ui_era_key(raw)
    if key and key in _LEGACY_LABELS:
        return _LEGACY_LABELS[key]
    return None


def resolve_era_mode(cli_value: str | None) -> str:
    """Resolve era mode from CLI or env (STORYTELLER_ERA_MODE)."""
    if cli_value:
        mode = str(cli_value).strip().lower()
    else:
        mode = os.environ.get("STORYTELLER_ERA_MODE", "").strip().lower()
    if mode in ("ui", "folder"):
        return mode
    return "legacy"


def apply_era_mode(value: str | None, era_mode: str) -> str | None:
    """Apply era_mode to value; in ui mode, canonicalize to UI key when possible."""
    if value is None:
        return None
    if era_mode == "folder":
        return value
    if era_mode == "ui":
        mapped = canonicalize_to_ui_era_key(value)
        return mapped or value
    return value


def validate_era_for_retrieval(era_value: str | None, era_mode: str) -> tuple[bool, str]:
    """Validate that an era value stored during ingestion will match retrieval filters.

    Returns (is_valid, warning_message). If valid, warning_message is empty.
    """
    if not era_value:
        return True, ""
    if era_mode == "ui":
        mapped = canonicalize_to_ui_era_key(era_value)
        if mapped is None:
            return False, (
                f"Era value '{era_value}' (mode=ui) does not map to any canonical UI era key. "
                f"Valid keys: {sorted(UI_ERA_KEYS)}. Retrieval filters may not match."
            )
        return True, ""
    if era_mode == "folder":
        mapped = canonicalize_to_ui_era_key(era_value)
        if mapped is None:
            return False, (
                f"Era value '{era_value}' (mode=folder) does not match any canonical era. "
                f"Retrieval will require exact string match on '{era_value}'."
            )
        return True, ""
    # legacy mode: always valid (pass-through)
    return True, ""


def infer_era_from_input_root(file_path, input_root) -> str | None:
    """Infer era label from the first path segment under input_root (folder names become eras).

    Returns the raw folder segment (preserves spacing/case). Safe: returns None if file_path
    is not under input_root.
    """
    try:
        rel = file_path.relative_to(input_root)
    except Exception as e:
        logger.debug("Failed to infer era from relative path; falling back to resolved paths: %s", e)
        try:
            rel = file_path.resolve().relative_to(input_root.resolve())
        except Exception as exc:
            logger.debug("Failed to infer era from resolved paths: %s", exc)
            return None
    parts = getattr(rel, "parts", None) or ()
    if not parts:
        return None
    first = str(parts[0]).strip()
    return first or None
