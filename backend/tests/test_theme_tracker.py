"""Tests for thematic resonance: _themes_from_text(), format_ledger_for_prompt(), update_ledger()."""
from __future__ import annotations


from backend.app.core.ledger import (
    _themes_from_text,
    format_ledger_for_prompt,
    update_ledger,
)
from backend.app.constants import LEDGER_MAX_THEMES


# ---------------------------------------------------------------------------
# _themes_from_text
# ---------------------------------------------------------------------------


def test_themes_from_text_activates_on_two_hits():
    """Text with 'trust' and 'loyal' (2 hits for cost_of_loyalty) should activate that theme."""
    text = "The soldier placed his trust in the captain's loyal heart."
    result = _themes_from_text(text, [])
    assert "cost_of_loyalty" in result


def test_themes_from_text_no_activation_on_single_hit():
    """Text with only 'trust' (1 hit for cost_of_loyalty) should not activate the theme."""
    text = "She extended her trust cautiously."
    result = _themes_from_text(text, [])
    assert "cost_of_loyalty" not in result


def test_themes_from_text_caps_at_max():
    """Text triggering many themes should be capped at LEDGER_MAX_THEMES."""
    # Build text with 2+ keywords from every theme in the map
    text = (
        "betray trust loyal sacrifice "      # cost_of_loyalty (4 hits)
        "power corrupt control dominate "     # power_corrupts (4 hits)
        "forgive atone redeem regret "        # redemption (4 hits)
        "survive moral choice compromise "    # survival_vs_morality (4 hits)
        "belong identity home outsider "      # identity_and_belonging (4 hits)
        "hope dark light resist endure "      # hope_against_darkness (5 hits)
        "duty desire want obligation "        # duty_vs_desire (4 hits)
    )
    result = _themes_from_text(text, [])
    assert len(result) <= LEDGER_MAX_THEMES


def test_themes_stability():
    """Existing themes stay when new text has no theme keywords."""
    existing = ["redemption"]
    text = "The sun rose over the quiet meadow."
    result = _themes_from_text(text, existing)
    assert "redemption" in result


# ---------------------------------------------------------------------------
# format_ledger_for_prompt (theme integration)
# ---------------------------------------------------------------------------


def test_format_ledger_includes_themes():
    """A ledger with active_themes should have 'Active themes:' and the theme name in output."""
    ledger = {
        "established_facts": ["Location: Cantina"],
        "open_threads": [],
        "active_goals": [],
        "constraints": [],
        "tone_tags": ["tense"],
        "active_themes": ["redemption"],
    }
    output = format_ledger_for_prompt(ledger)
    assert "Active themes:" in output
    assert "redemption" in output


# ---------------------------------------------------------------------------
# update_ledger (theme integration)
# ---------------------------------------------------------------------------


def test_update_ledger_includes_themes():
    """Narrated text with theme keywords should populate active_themes in the returned ledger."""
    narrated_text = "He chose to betray his trust and remain loyal to his oath, a true sacrifice."
    result = update_ledger(previous=None, new_events=[], narrated_text=narrated_text)
    assert "active_themes" in result
    assert "cost_of_loyalty" in result["active_themes"]
