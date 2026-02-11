"""Tests for the narrative validator node: mechanic consistency + constraint contradiction checks."""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from backend.app.core.nodes.narrative_validator import (
    narrative_validator_node,
    _check_mechanic_consistency,
    _check_constraint_contradictions,
)


class TestMechanicConsistency:
    def test_success_language_on_failure_warns(self):
        warnings = _check_mechanic_consistency(
            "You succeeded in breaking the lock.", {"success": False}
        )
        assert len(warnings) == 1
        assert "success language" in warnings[0]

    def test_manages_to_on_failure_warns(self):
        warnings = _check_mechanic_consistency(
            "You managed to slip past the guard.", {"success": False}
        )
        assert len(warnings) == 1

    def test_failure_language_on_success_warns(self):
        warnings = _check_mechanic_consistency(
            "You fumbled the attempt.", {"success": True}
        )
        assert len(warnings) == 1
        assert "failure language" in warnings[0]

    def test_miss_on_success_warns(self):
        warnings = _check_mechanic_consistency(
            "Your shot missed the target.", {"success": True}
        )
        assert len(warnings) == 1

    def test_no_warning_when_success_matches(self):
        warnings = _check_mechanic_consistency(
            "You succeeded brilliantly.", {"success": True}
        )
        assert len(warnings) == 0

    def test_no_warning_when_failure_matches(self):
        warnings = _check_mechanic_consistency(
            "You failed to pick the lock.", {"success": False}
        )
        assert len(warnings) == 0

    def test_no_warning_without_success_field(self):
        warnings = _check_mechanic_consistency(
            "Something happened.", {"action_type": "TALK"}
        )
        assert len(warnings) == 0

    def test_no_warning_on_empty_text(self):
        warnings = _check_mechanic_consistency("", {"success": False})
        assert len(warnings) == 0

    def test_no_warning_on_none_mechanic(self):
        warnings = _check_mechanic_consistency("You succeeded.", None)
        assert len(warnings) == 0


class TestConstraintContradictions:
    """V3.0: _check_constraint_contradictions is now a no-op (too many false positives)."""

    def test_always_returns_empty(self):
        """Disabled guard always returns empty list."""
        constraints = ["The door is sealed"]
        text = "The door is not sealed anymore."
        warnings = _check_constraint_contradictions(text, constraints)
        assert len(warnings) == 0

    def test_empty_constraints_returns_empty(self):
        warnings = _check_constraint_contradictions("Some text.", [])
        assert len(warnings) == 0

    def test_empty_text_returns_empty(self):
        warnings = _check_constraint_contradictions("", ["Something"])
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
