"""Tests for stress delta computation in the mechanic agent."""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from backend.app.core.agents.mechanic import (
    _compute_stress_delta,
    _compute_critical_outcome,
    _compute_world_reaction_needed,
)
from backend.app.models.events import Event


class TestComputeStressDelta:
    def test_critical_failure_roll_1(self):
        delta = _compute_stress_delta("ATTACK", False, 1, [])
        # roll==1: +2, but also normal failure: however roll==1 takes the elif branch
        # Actually: roll==1 -> +2 (first branch), success is False but elif won't trigger
        # risky success check: success is False so no -1
        assert delta == 2

    def test_normal_failure(self):
        delta = _compute_stress_delta("ATTACK", False, 5, [])
        # normal failure: +1
        assert delta == 1

    def test_success_on_risky_action(self):
        delta = _compute_stress_delta("ATTACK", True, 15, [])
        # risky success: -1
        assert delta == -1

    def test_success_on_safe_action(self):
        delta = _compute_stress_delta("INVESTIGATE", True, 15, [])
        # not a risky action (ATTACK/SNEAK/PERSUADE), no stress change
        assert delta == 0

    def test_talk_social_relief(self):
        delta = _compute_stress_delta("TALK", None, None, [])
        # TALK: -1
        assert delta == -1

    def test_high_damage_event(self):
        events = [Event(event_type="DAMAGE", payload={"amount": 5})]
        delta = _compute_stress_delta("ATTACK", True, 15, events)
        # damage > 3: +1, risky success: -1 => net 0
        assert delta == 0

    def test_low_damage_no_stress(self):
        events = [Event(event_type="DAMAGE", payload={"amount": 2})]
        delta = _compute_stress_delta("ATTACK", True, 15, events)
        # damage <= 3: no stress from damage, risky success: -1
        assert delta == -1

    def test_dict_events_supported(self):
        events = [{"event_type": "DAMAGE", "payload": {"amount": 5}}]
        delta = _compute_stress_delta("ATTACK", True, 15, events)
        # damage > 3: +1, risky success: -1 => net 0
        assert delta == 0

    def test_persuade_is_risky(self):
        delta = _compute_stress_delta("PERSUADE", True, 10, [])
        assert delta == -1

    def test_sneak_is_risky(self):
        delta = _compute_stress_delta("SNEAK", True, 10, [])
        assert delta == -1

    def test_critical_failure_with_damage(self):
        events = [Event(event_type="DAMAGE", payload={"amount": 5})]
        delta = _compute_stress_delta("ATTACK", False, 1, events)
        # roll==1: +2, damage>3: +1 => total +3
        assert delta == 3


class TestComputeCriticalOutcome:
    def test_roll_1_is_critical_failure(self):
        assert _compute_critical_outcome(1) == "CRITICAL_FAILURE"

    def test_roll_20_is_critical_success(self):
        assert _compute_critical_outcome(20) == "CRITICAL_SUCCESS"

    def test_normal_roll_returns_none(self):
        assert _compute_critical_outcome(10) is None

    def test_none_roll_returns_none(self):
        assert _compute_critical_outcome(None) is None


class TestComputeWorldReactionNeeded:
    def test_high_damage_triggers(self):
        events = [Event(event_type="DAMAGE", payload={"amount": 10})]
        assert _compute_world_reaction_needed(events) is True

    def test_low_damage_no_trigger(self):
        events = [Event(event_type="DAMAGE", payload={"amount": 5})]
        assert _compute_world_reaction_needed(events) is False

    def test_large_relationship_drop_triggers(self):
        events = [Event(event_type="RELATIONSHIP", payload={"delta": -4})]
        assert _compute_world_reaction_needed(events) is True

    def test_small_relationship_drop_no_trigger(self):
        events = [Event(event_type="RELATIONSHIP", payload={"delta": -2})]
        assert _compute_world_reaction_needed(events) is False

    def test_faction_flag_triggers(self):
        events = [Event(event_type="FLAG_SET", payload={"key": "faction_betrayal", "value": True})]
        assert _compute_world_reaction_needed(events) is True

    def test_non_faction_flag_no_trigger(self):
        events = [Event(event_type="FLAG_SET", payload={"key": "quest_started", "value": True})]
        assert _compute_world_reaction_needed(events) is False

    def test_empty_events_no_trigger(self):
        assert _compute_world_reaction_needed([]) is False

    def test_dict_events_supported(self):
        events = [{"event_type": "DAMAGE", "payload": {"amount": 12}}]
        assert _compute_world_reaction_needed(events) is True
