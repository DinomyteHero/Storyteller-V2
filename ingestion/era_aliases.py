"""Era alias helpers for ingestion and classification."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)


# Default aliases for common folder naming conventions
DEFAULT_ERA_ALIASES: Dict[str, str] = {
    "before_the_republic": "Old Republic",
    "rise_of_the_empire_era": "Clone Wars",
    "rise_of_the_empire": "Clone Wars",
    "new_jedi_order_era": "New Republic",
    "new_jedi_order": "New Republic",
    "legacy_era": "LOTF",
    "legacy_of_the_force": "LOTF",
    "rebellion_era": "Rebellion",
    "rebellion": "Rebellion",
    "galactic_civil_war": "Rebellion",
    "gcw": "Rebellion",
    "new_republic_era": "New Republic",
    "old_galactic_republic_era": "Old Republic",
    "old_galactic_republic": "Old Republic",
}


def normalize_segment(text: str) -> str:
    """Normalize a path segment to a lowercase underscore token."""
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def normalize_aliases(aliases: Dict[str, str] | None) -> Dict[str, str]:
    """Normalize alias keys and clean values."""
    if not aliases:
        return {}
    out: Dict[str, str] = {}
    for key, value in aliases.items():
        if not key or not value:
            continue
        out[normalize_segment(str(key))] = str(value).strip()
    return out


def load_era_aliases(path: str | None) -> Dict[str, str]:
    """Load era aliases from a JSON file. Returns normalized dict or empty."""
    if not path:
        return {}
    p = Path(path).expanduser()
    if not p.exists():
        logger.warning("Era alias file not found: %s", p)
        return {}
    try:
        raw = p.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception as exc:
        logger.warning("Failed to read era alias file %s: %s", p, exc)
        return {}
    if not isinstance(data, dict):
        logger.warning("Era alias file must be a JSON object: %s", p)
        return {}
    return normalize_aliases(data)
