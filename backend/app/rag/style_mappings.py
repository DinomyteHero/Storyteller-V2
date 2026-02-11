"""Static mappings from style source_title to era/genre/archetype classification."""
from __future__ import annotations

# Map source_title (filename stem) -> "BASE" (always-on Star Wars style)
BASE_STYLE_MAP: dict[str, str] = {
    "star_wars_base_style": "BASE",
}

# Map source_title (filename stem) -> canonical era ID
ERA_STYLE_MAP: dict[str, str] = {
    "rebellion_style": "REBELLION",
    "legacy_style": "LEGACY",
    "new_republic_style": "NEW_REPUBLIC",
    "new_jedi_order_style": "NEW_JEDI_ORDER",
}

# Map source_title (filename stem) -> genre slug
GENRE_STYLE_MAP: dict[str, str] = {
    "noir_detective_style": "noir_detective",
    "cosmic_horror_style": "cosmic_horror",
    "samurai_cinema_style": "samurai_cinema",
    "mythic_quest_style": "mythic_quest",
    "survival_horror_style": "survival_horror",
    "political_thriller_style": "political_thriller",
    "military_tactical_style": "military_tactical",
    "heist_caper_style": "heist_caper",
    "gothic_romance_style": "gothic_romance",
    "espionage_thriller_style": "espionage_thriller",
    "space_western_style": "space_western",
    "court_intrigue_style": "court_intrigue",
    "post_apocalyptic_style": "post_apocalyptic",
    "murder_mystery_style": "murder_mystery",
    "epic_fantasy_quest_style": "epic_fantasy_quest",
}

# Map source_title (filename stem) -> archetype slug (narrative structure)
ARCHETYPE_STYLE_MAP: dict[str, str] = {
    "hero_journey_style": "heros_journey",
}

# --- Reverse lookups ---

# Base source titles (always-on)
BASE_SOURCE_TITLES: list[str] = list(BASE_STYLE_MAP.keys())

# Reverse lookup: era ID -> list of source_titles
_ERA_TO_SOURCES: dict[str, list[str]] = {}
for _src, _era in ERA_STYLE_MAP.items():
    _ERA_TO_SOURCES.setdefault(_era, []).append(_src)

# Reverse lookup: genre slug -> source_title
_GENRE_TO_SOURCE: dict[str, str] = {v: k for k, v in GENRE_STYLE_MAP.items()}

# Reverse lookup: archetype slug -> source_title
_ARCHETYPE_TO_SOURCE: dict[str, str] = {v: k for k, v in ARCHETYPE_STYLE_MAP.items()}


def era_source_titles(era_id: str) -> list[str]:
    """Return source_title values for a given era ID (e.g., REBELLION -> ['rebellion_style'])."""
    return _ERA_TO_SOURCES.get(era_id, [])


def genre_source_title(genre_slug: str) -> str | None:
    """Return source_title for a genre slug (e.g., 'noir_detective' -> 'noir_detective_style')."""
    return _GENRE_TO_SOURCE.get(genre_slug)


def archetype_source_title(archetype_slug: str) -> str | None:
    """Return source_title for an archetype slug (e.g., 'heros_journey' -> 'hero_journey_style')."""
    return _ARCHETYPE_TO_SOURCE.get(archetype_slug)
