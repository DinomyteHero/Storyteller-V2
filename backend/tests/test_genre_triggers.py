"""Tests for the deterministic genre auto-assignment system."""
from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from backend.app.core.genre_triggers import (
    assign_initial_genre,
    detect_genre_shift,
    GENRE_SHIFT_COOLDOWN,
)


# --- assign_initial_genre ---

def test_smuggler_gets_space_western():
    assert assign_initial_genre("smuggler") == "space_western"


def test_bounty_hunter_gets_noir():
    assert assign_initial_genre("bounty_hunter") == "noir_detective"


def test_imperial_officer_gets_military():
    assert assign_initial_genre("imperial_officer") == "military_tactical"


def test_force_sensitive_gets_mythic():
    assert assign_initial_genre("force_sensitive") == "mythic_quest"


def test_sith_apprentice_gets_dark_fantasy():
    assert assign_initial_genre("sith_apprentice") == "dark_fantasy"


def test_rebel_operative_gets_espionage():
    assert assign_initial_genre("rebel_operative") == "espionage_thriller"


def test_background_takes_priority_over_location():
    """Background genre should win over location tags."""
    genre = assign_initial_genre("smuggler", ["temple", "jedi"])
    assert genre == "space_western"  # background wins, not mythic_quest


def test_location_fallback_when_no_background():
    """When no background match, location tags should determine genre."""
    genre = assign_initial_genre(None, ["underworld", "cantina"])
    assert genre == "noir_detective"  # underworld has higher priority


def test_location_tag_priority():
    """Temple/jedi should win over cantina in tag priority."""
    genre = assign_initial_genre(None, ["cantina", "temple"])
    assert genre == "mythic_quest"  # temple has higher priority


def test_no_match_returns_none():
    assert assign_initial_genre(None, None) is None
    assert assign_initial_genre(None, []) is None
    assert assign_initial_genre("unknown_background") is None


def test_case_insensitive_background():
    """Background IDs should be case-insensitive."""
    assert assign_initial_genre("SMUGGLER") == "space_western"
    assert assign_initial_genre("Bounty_Hunter") == "noir_detective"


def test_location_tags_normalized():
    """Location tags with dashes should be normalized to underscores."""
    genre = assign_initial_genre(None, ["imperial-garrison"])
    assert genre == "military_tactical"


# --- detect_genre_shift ---

def test_shift_after_cooldown():
    """Genre should shift when cooldown has elapsed and location differs."""
    new = detect_genre_shift("space_western", ["temple", "jedi"], "RISING", GENRE_SHIFT_COOLDOWN + 1)
    assert new == "mythic_quest"


def test_no_shift_during_cooldown():
    """Genre should NOT shift during cooldown period."""
    new = detect_genre_shift("space_western", ["temple", "jedi"], "RISING", GENRE_SHIFT_COOLDOWN - 1)
    assert new is None


def test_no_shift_during_climax():
    """Genre should NOT shift during CLIMAX arc stage."""
    new = detect_genre_shift("space_western", ["temple"], "CLIMAX", GENRE_SHIFT_COOLDOWN + 10)
    assert new is None


def test_no_shift_during_resolution():
    """Genre should NOT shift during RESOLUTION arc stage."""
    new = detect_genre_shift("space_western", ["temple"], "RESOLUTION", GENRE_SHIFT_COOLDOWN + 10)
    assert new is None


def test_no_shift_when_same_genre():
    """No shift should occur if location maps to the same genre."""
    new = detect_genre_shift("space_western", ["cantina", "frontier"], "SETUP", GENRE_SHIFT_COOLDOWN + 10)
    assert new is None  # cantina maps to space_western, same as current


def test_no_shift_without_location_tags():
    """No shift without location context."""
    new = detect_genre_shift("space_western", None, "RISING", GENRE_SHIFT_COOLDOWN + 10)
    assert new is None
    new = detect_genre_shift("space_western", [], "RISING", GENRE_SHIFT_COOLDOWN + 10)
    assert new is None


def test_shift_to_survival_from_prison():
    """Moving to a prison location should trigger survival_horror."""
    new = detect_genre_shift("space_western", ["prison"], "RISING", GENRE_SHIFT_COOLDOWN + 1)
    assert new == "survival_horror"
