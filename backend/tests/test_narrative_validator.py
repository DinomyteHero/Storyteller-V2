"""Tests for the narrative validator node: mechanic consistency + constraint contradiction checks."""
import sys
from pathlib import Path

import pytest

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

pytestmark = [pytest.mark.release_gate, pytest.mark.narrative]

from backend.app.core.nodes.narrative_validator import (  # noqa: E402
    narrative_validator_node,
    _check_mechanic_consistency,
)


class TestMechanicConsistency:
    def test_success_language_on_failure_warns(self):
        corrected, warnings, repairs = _check_mechanic_consistency(
            "You succeeded in breaking the lock.", {"success": False}
        )
        assert len(warnings) == 1
        assert "mechanic contradiction" in warnings[0].lower() or "repaired" in warnings[0].lower()
        assert len(repairs) >= 1
        assert "succeeded" not in corrected.lower() or "struggled" in corrected.lower()

    def test_manages_to_on_failure_warns(self):
        corrected, warnings, repairs = _check_mechanic_consistency(
            "You managed to slip past the guard.", {"success": False}
        )
        assert len(warnings) == 1
        assert len(repairs) >= 1

    def test_failure_language_on_success_warns(self):
        corrected, warnings, repairs = _check_mechanic_consistency(
            "You fumbled the attempt.", {"success": True}
        )
        assert len(warnings) == 1
        assert "mechanic contradiction" in warnings[0].lower() or "repaired" in warnings[0].lower()
        assert len(repairs) >= 1

    def test_miss_on_success_warns(self):
        corrected, warnings, repairs = _check_mechanic_consistency(
            "Your shot missed the target.", {"success": True}
        )
        assert len(warnings) == 1
        assert len(repairs) >= 1

    def test_no_warning_when_success_matches(self):
        corrected, warnings, repairs = _check_mechanic_consistency(
            "You succeeded brilliantly.", {"success": True}
        )
        assert len(warnings) == 0
        assert len(repairs) == 0

    def test_no_warning_when_failure_matches(self):
        corrected, warnings, repairs = _check_mechanic_consistency(
            "You failed to pick the lock.", {"success": False}
        )
        assert len(warnings) == 0
        assert len(repairs) == 0

    def test_no_warning_without_success_field(self):
        corrected, warnings, repairs = _check_mechanic_consistency(
            "Something happened.", {"action_type": "TALK"}
        )
        assert len(warnings) == 0

    def test_no_warning_on_empty_text(self):
        corrected, warnings, repairs = _check_mechanic_consistency("", {"success": False})
        assert len(warnings) == 0

    def test_no_warning_on_none_mechanic(self):
        corrected, warnings, repairs = _check_mechanic_consistency("You succeeded.", None)
        assert len(warnings) == 0

class TestNarrativeValidatorNode:
    def test_node_returns_validation_notes(self):
        state = {
            "final_text": "You succeeded in the attack.",
            "mechanic_result": {"success": False},
            "campaign": {},
            "warnings": [],
        }
        result = narrative_validator_node(state)
        assert "validation_notes" in result
        assert len(result["validation_notes"]) >= 1

    def test_node_preserves_state(self):
        state = {
            "final_text": "Nothing special.",
            "mechanic_result": {},
            "campaign": {},
            "warnings": [],
            "some_key": "preserved",
        }
        result = narrative_validator_node(state)
        assert result["some_key"] == "preserved"

    def test_node_appends_warnings(self):
        state = {
            "final_text": "You accomplished the task.",
            "mechanic_result": {"success": False},
            "campaign": {},
            "warnings": ["Existing warning"],
        }
        result = narrative_validator_node(state)
        assert "Existing warning" in result["warnings"]
        assert len(result["warnings"]) >= 2

    def test_node_no_warnings_on_clean_text(self):
        state = {
            "final_text": "The world is quiet.",
            "mechanic_result": {"success": True},
            "campaign": {},
            "warnings": [],
        }
        result = narrative_validator_node(state)
        assert len(result["validation_notes"]) == 0

    def test_node_with_constraint_check_is_noop(self):
        """V3.0: Constraint checker is disabled, so no warnings expected."""
        state = {
            "final_text": "The bridge is not destroyed.",
            "mechanic_result": {},
            "campaign": {
                "world_state_json": {
                    "ledger": {
                        "constraints": ["The bridge is destroyed"],
                    }
                }
            },
            "warnings": [],
        }
        result = narrative_validator_node(state)
        assert len(result["validation_notes"]) == 0
