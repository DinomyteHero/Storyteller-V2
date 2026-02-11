"""Deterministic genre auto-assignment based on background, location tags, and arc context.

Genre is a narrative flavoring overlay on top of the Star Wars base layer.
No LLM calls — pure Python mappings.

Usage:
    assign_initial_genre(background_id, location_tags) -> genre slug or None
    detect_genre_shift(current_genre, location_tags, arc_stage, turns_since_last_shift) -> genre slug or None
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Minimum turns between genre shifts to prevent jarring whiplash
GENRE_SHIFT_COOLDOWN = 5

# ---------------------------------------------------------------------------
# Background ID → default genre slug
# ---------------------------------------------------------------------------
BACKGROUND_GENRE_MAP: dict[str, str] = {
    # Rebellion era backgrounds
    "imperial_officer": "military_tactical",
    "rebel_operative": "espionage_thriller",
    "smuggler": "space_western",
    "bounty_hunter": "noir_detective",
    "force_sensitive": "mythic_quest",
    "imperial_defector": "espionage_thriller",
    "scoundrel": "space_western",

    # New Republic era backgrounds
    "new_republic_pilot": "military_tactical",
    "jedi_initiate": "mythic_quest",
    "intelligence_agent": "espionage_thriller",
    "senator": "political_thriller",
    "warlord_hunter": "military_tactical",

    # New Jedi Order era backgrounds
    "jedi_knight": "mythic_quest",
    "vong_survivor": "survival_horror",
    "resistance_fighter": "military_tactical",

    # Legacy era backgrounds
    "sith_apprentice": "dark_fantasy",
    "imperial_knight": "military_tactical",
    "legacy_jedi": "mythic_quest",
    "galactic_alliance_agent": "espionage_thriller",
    "bounty_hunter_legacy": "noir_detective",
    "fel_loyalist": "political_thriller",
    "pirate_captain": "heist_caper",

    # Generic/cross-era backgrounds
    "merchant_trader": "heist_caper",
    "explorer": "space_western",
    "diplomat": "political_thriller",
    "mechanic": "space_western",
    "medic": "survival_horror",
}

# ---------------------------------------------------------------------------
# Location tag → genre affinity (ordered by priority)
# ---------------------------------------------------------------------------
LOCATION_TAG_GENRE_MAP: dict[str, str] = {
    # Underworld / crime
    "underworld": "noir_detective",
    "cantina": "space_western",
    "smuggler": "heist_caper",
    "black_market": "noir_detective",

    # Military
    "military": "military_tactical",
    "imperial_garrison": "military_tactical",
    "base": "military_tactical",
    "hangar": "military_tactical",
    "command_center": "military_tactical",
    "star_destroyer": "military_tactical",

    # Political
    "senate": "political_thriller",
    "court": "court_intrigue",
    "palace": "court_intrigue",
    "diplomatic": "political_thriller",

    # Danger / survival
    "prison": "survival_horror",
    "wilderness": "survival_horror",
    "hostile": "survival_horror",
    "ruins": "survival_horror",

    # Force / mystical
    "temple": "mythic_quest",
    "jedi": "mythic_quest",
    "sith": "dark_fantasy",
    "force": "mythic_quest",
    "ancient": "mythic_quest",

    # Frontier / exploration
    "frontier": "space_western",
    "outpost": "space_western",
    "spaceport": "space_western",
    "docking_bay": "space_western",
    "marketplace": "space_western",

    # Intelligence
    "intelligence": "espionage_thriller",
    "surveillance": "espionage_thriller",
    "covert": "espionage_thriller",
}

# Priority order for location tag matching (first match wins)
_TAG_PRIORITY = [
    # Highest priority: distinctive environments
    "sith", "temple", "jedi", "force", "ancient",
    "prison", "intelligence", "covert", "surveillance",
    "senate", "court", "palace", "diplomatic",
    "underworld", "black_market",
    # Medium priority
    "imperial_garrison", "star_destroyer", "command_center",
    "military", "base", "hangar",
    "smuggler", "cantina",
    # Lower priority: common tags
    "wilderness", "hostile", "ruins",
    "frontier", "outpost", "spaceport", "docking_bay", "marketplace",
]


def assign_initial_genre(
    background_id: str | None,
    location_tags: list[str] | None = None,
) -> str | None:
    """Deterministic initial genre from background + location.

    Background takes priority over location tags.
    Returns genre slug (e.g. 'space_western') or None if no match.
    """
    # Background takes priority
    if background_id:
        bg_lower = background_id.lower().strip()
        genre = BACKGROUND_GENRE_MAP.get(bg_lower)
        if genre:
            logger.debug("Genre assigned from background '%s': %s", background_id, genre)
            return genre

    # Fall back to location tags
    if location_tags:
        tags_lower = {t.lower().strip().replace("-", "_") for t in location_tags if t}
        for tag in _TAG_PRIORITY:
            if tag in tags_lower:
                genre = LOCATION_TAG_GENRE_MAP[tag]
                logger.debug("Genre assigned from location tag '%s': %s", tag, genre)
                return genre

    return None


def detect_genre_shift(
    current_genre: str | None,
    location_tags: list[str] | None,
    arc_stage: str | None = None,
    turns_since_last_shift: int = 0,
) -> str | None:
    """Per-turn genre detection. Returns new genre slug if shift warranted, else None.

    Enforces cooldown to prevent jarring shifts. Only shifts when the
    location context strongly suggests a different genre.

    Args:
        current_genre: Current active genre slug (or None)
        location_tags: Tags for the player's current location
        arc_stage: Current arc stage (SETUP, RISING, CLIMAX, RESOLUTION)
        turns_since_last_shift: Number of turns since last genre change

    Returns:
        New genre slug if a shift is warranted, None otherwise.
    """
    # Don't shift if cooldown hasn't elapsed
    if turns_since_last_shift < GENRE_SHIFT_COOLDOWN:
        return None

    # Don't shift during CLIMAX or RESOLUTION — keep narrative tension stable
    if arc_stage and arc_stage.upper() in ("CLIMAX", "RESOLUTION"):
        return None

    if not location_tags:
        return None

    tags_lower = {t.lower().strip().replace("-", "_") for t in location_tags if t}
    candidate = None
    for tag in _TAG_PRIORITY:
        if tag in tags_lower:
            candidate = LOCATION_TAG_GENRE_MAP[tag]
            break

    if candidate and candidate != current_genre:
        logger.info(
            "Genre shift detected: %s -> %s (location tags: %s, arc: %s)",
            current_genre, candidate, sorted(tags_lower), arc_stage,
        )
        return candidate

    return None
