"""Tests for companion banter prose weaving."""

from backend.app.core.nodes.narrator import _inject_companion_interjection


def test_inject_companion_interjection_mid_scene():
    prose = "The alley is quiet, lit only by neon.\n\nA patrol passes at the far end."
    out = _inject_companion_interjection(prose, "Kira", "This place smells like a trap")
    assert "Kira cut in" in out
    assert "---" not in out
    assert "A patrol passes" in out


def test_inject_companion_interjection_handles_empty_prose():
    out = _inject_companion_interjection("", "Kira", "Eyes up")
    assert out == 'Kira cut in, "Eyes up"'
