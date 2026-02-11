"""Tests for companion metadata completeness and validity (Phase 3D).

Ensures every companion in data/companions.yaml has the required enrichment
fields (species, voice_tags, motivation, speech_quirk) and that all values
reference valid constants (voice tags, banter styles).
"""
from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from backend.app.core.companions import load_companions
from backend.app.core.personality_profile import VOICE_TAG_SPEECH_PATTERNS
from backend.app.constants import BANTER_POOL


def _all_companions() -> list[dict]:
    """Load all companions (no era filter)."""
    return load_companions(era=None)


# ── Field presence tests ──────────────────────────────────────────────


def test_all_companions_have_species():
    """Every companion must have a non-empty 'species' field."""
    missing = []
    for c in _all_companions():
        if not c.get("species"):
            missing.append(c.get("id", "???"))
    assert not missing, f"Companions missing 'species': {missing}"


def test_all_companions_have_voice_tags():
    """Every companion must have 2-3 voice_tags."""
    bad = []
    for c in _all_companions():
        tags = c.get("voice_tags") or []
        if not isinstance(tags, list) or len(tags) < 2 or len(tags) > 3:
            bad.append((c.get("id", "???"), len(tags) if isinstance(tags, list) else 0))
    assert not bad, f"Companions with wrong voice_tags count (need 2-3): {bad}"


def test_all_companions_have_motivation():
    """Every companion must have a non-empty 'motivation' string."""
    missing = []
    for c in _all_companions():
        mot = c.get("motivation") or ""
        if not isinstance(mot, str) or len(mot.strip()) < 10:
            missing.append(c.get("id", "???"))
    assert not missing, f"Companions missing 'motivation' (or too short): {missing}"


def test_all_companions_have_speech_quirk():
    """Every companion must have a non-empty 'speech_quirk' string."""
    missing = []
    for c in _all_companions():
        quirk = c.get("speech_quirk") or ""
        if not isinstance(quirk, str) or len(quirk.strip()) < 10:
            missing.append(c.get("id", "???"))
    assert not missing, f"Companions missing 'speech_quirk' (or too short): {missing}"


# ── Validity tests ────────────────────────────────────────────────────


def test_voice_tags_are_valid():
    """All voice_tags must exist in VOICE_TAG_SPEECH_PATTERNS."""
    valid_tags = set(VOICE_TAG_SPEECH_PATTERNS.keys())
    bad = []
    for c in _all_companions():
        for tag in (c.get("voice_tags") or []):
            if tag.lower().strip() not in valid_tags:
                bad.append((c.get("id", "???"), tag))
    assert not bad, f"Companions with invalid voice_tags: {bad}"


def test_all_banter_styles_in_pool():
    """Every banter_style used in companions.yaml must have entries in BANTER_POOL."""
    pool_styles = set(BANTER_POOL.keys())
    bad = []
    for c in _all_companions():
        style = c.get("banter_style", "")
        if style and style not in pool_styles:
            bad.append((c.get("id", "???"), style))
    assert not bad, f"Companions with banter_style not in BANTER_POOL: {bad}"


def test_banter_pool_has_all_tones():
    """Every style in BANTER_POOL must have all 4 tone variants."""
    required_tones = {"PARAGON", "RENEGADE", "INVESTIGATE", "NEUTRAL"}
    bad = []
    for style, tones in BANTER_POOL.items():
        missing = required_tones - set(tones.keys())
        if missing:
            bad.append((style, missing))
    assert not bad, f"BANTER_POOL styles missing tones: {bad}"
