"""Tests for Phase 7 narrator feedback loop: _check_mechanic_consistency from narrative_validator."""
from __future__ import annotations

import pytest

from backend.app.core.nodes.narrative_validator import _check_mechanic_consistency


# ---------------------------------------------------------------------------
# _check_mechanic_consistency
# ---------------------------------------------------------------------------


def test_check_mechanic_consistency_success_language_on_failure():
    """Narrator uses success language ('succeeded brilliantly') but mechanic says success=False."""
    final_text = "The player succeeded brilliantly, unlocking the door with ease."
    mechanic_result = {"success": False}
    warnings = _check_mechanic_consistency(final_text, mechanic_result)
    assert len(warnings) > 0
    assert any("success" in w.lower() for w in warnings)


def test_check_mechanic_consistency_clean():
    """Narrator text matches mechanic outcome (failure language for failure). No warnings."""
    final_text = "The player tried but the door held firm."
    mechanic_result = {"success": False}
    warnings = _check_mechanic_consistency(final_text, mechanic_result)
    assert len(warnings) == 0


def test_check_mechanic_consistency_failure_language_on_success():
    """Narrator uses failure language ('fumbled') but mechanic says success=True."""
    final_text = "You fumbled the lock, and sparks flew as the mechanism jammed."
    mechanic_result = {"success": True}
    warnings = _check_mechanic_consistency(final_text, mechanic_result)
    assert len(warnings) > 0
    assert any("failure" in w.lower() or "fumble" in w.lower() for w in warnings)


def test_check_mechanic_consistency_no_success_field():
    """mechanic_result without a 'success' field should produce no warnings (no check/roll)."""
    mechanic_result = {"action_type": "TALK"}
    warnings = _check_mechanic_consistency("The conversation continued smoothly.", mechanic_result)
    assert len(warnings) == 0
