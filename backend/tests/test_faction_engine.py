"""Tests for the deterministic faction simulation engine."""
from __future__ import annotations

import pytest

from backend.app.world.faction_engine import simulate_faction_tick, _primary_tag


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REBELLION_FACTIONS = [
    {"name": "Alliance to Restore the Republic", "location": "loc-yavin_base", "current_goal": "Restore the Galactic Republic", "resources": 5, "is_hostile": False},
    {"name": "Galactic Empire", "location": "loc-star_destroyer", "current_goal": "Enforce order through fear", "resources": 7, "is_hostile": True},
    {"name": "Criminal Syndicates", "location": "loc-cantina", "current_goal": "Profit from wartime shortages", "resources": 4, "is_hostile": False},
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSimulateFactionTick:
    """Tests for simulate_faction_tick."""

    def test_produces_rumors(self):
        """Verify at least 1 rumor is generated on every tick."""
        out = simulate_faction_tick(
            active_factions=REBELLION_FACTIONS,
            turn_number=1,
            player_location="loc-cantina",
        )
        assert len(out.new_rumors) >= 1
        for rumor in out.new_rumors:
            assert isinstance(rumor, str)
            assert len(rumor) > 10

    def test_produces_faction_moves(self):
        """Verify faction moves are generated."""
        out = simulate_faction_tick(
            active_factions=REBELLION_FACTIONS,
            turn_number=1,
            player_location="loc-cantina",
        )
        assert len(out.faction_moves) >= 1
        for move in out.faction_moves:
            assert isinstance(move, str)
            assert len(move) > 10

    def test_produces_updated_factions(self):
        """Verify updated_factions has the same count as input."""
        out = simulate_faction_tick(
            active_factions=REBELLION_FACTIONS,
            turn_number=5,
            player_location="loc-cantina",
        )
        assert out.updated_factions is not None
        assert len(out.updated_factions) == len(REBELLION_FACTIONS)

    def test_deterministic_same_inputs(self):
        """Same inputs must produce the same outputs (seeded RNG)."""
        out1 = simulate_faction_tick(
            active_factions=REBELLION_FACTIONS,
            turn_number=42,
            player_location="loc-cantina",
            arc_stage="RISING",
        )
        out2 = simulate_faction_tick(
            active_factions=REBELLION_FACTIONS,
            turn_number=42,
            player_location="loc-cantina",
            arc_stage="RISING",
        )
        assert out1.new_rumors == out2.new_rumors
        assert out1.faction_moves == out2.faction_moves
        assert out1.hidden_events == out2.hidden_events
        assert out1.updated_factions == out2.updated_factions

    def test_different_turn_numbers_differ(self):
        """Different turn numbers should produce different outputs."""
        out1 = simulate_faction_tick(
            active_factions=REBELLION_FACTIONS,
            turn_number=1,
            player_location="loc-cantina",
        )
        out2 = simulate_faction_tick(
            active_factions=REBELLION_FACTIONS,
            turn_number=2,
            player_location="loc-cantina",
        )
        # They could theoretically be the same, but with 3 factions
        # and 15+ templates each, it's astronomically unlikely
        assert out1.new_rumors != out2.new_rumors or out1.faction_moves != out2.faction_moves

    def test_arc_climax_escalates(self):
        """CLIMAX arc_stage should produce more rumors and at least 1 hidden event."""
        out = simulate_faction_tick(
            active_factions=REBELLION_FACTIONS,
            turn_number=10,
            player_location="loc-cantina",
            arc_stage="CLIMAX",
        )
        assert len(out.new_rumors) >= 2
        assert len(out.hidden_events) >= 1

    def test_arc_resolution_produces_events(self):
        """RESOLUTION arc_stage should produce hidden events."""
        out = simulate_faction_tick(
            active_factions=REBELLION_FACTIONS,
            turn_number=20,
            player_location="loc-cantina",
            arc_stage="RESOLUTION",
        )
        assert len(out.hidden_events) >= 1

    def test_travel_generates_more_rumors(self):
        """travel_occurred should produce at least 2 rumors."""
        out = simulate_faction_tick(
            active_factions=REBELLION_FACTIONS,
            turn_number=3,
            player_location="loc-docking-bay",
            travel_occurred=True,
        )
        assert len(out.new_rumors) >= 2

    def test_world_reaction_generates_events(self):
        """world_reaction_needed should produce at least 2 rumors and hidden events."""
        out = simulate_faction_tick(
            active_factions=REBELLION_FACTIONS,
            turn_number=7,
            player_location="loc-cantina",
            world_reaction_needed=True,
        )
        assert len(out.new_rumors) >= 2
        assert len(out.hidden_events) >= 1

    def test_resources_stay_in_bounds(self):
        """Resources should always be between 1 and 10."""
        # Run many ticks to stress-test bounds
        factions = [
            {"name": "Low Resources", "location": "loc-cantina", "current_goal": "survive", "resources": 1, "is_hostile": False},
            {"name": "High Resources", "location": "loc-cantina", "current_goal": "dominate", "resources": 10, "is_hostile": True},
        ]
        for turn in range(1, 50):
            out = simulate_faction_tick(
                active_factions=factions,
                turn_number=turn,
                player_location="loc-cantina",
            )
            for f in out.updated_factions:
                assert 1 <= f["resources"] <= 10, f"Resources out of bounds at turn {turn}: {f}"
            # Use updated factions for next iteration
            factions = out.updated_factions

    def test_no_factions_noop(self):
        """Empty factions list should return empty WorldSimOutput."""
        out = simulate_faction_tick(
            active_factions=[],
            turn_number=1,
            player_location="loc-cantina",
        )
        assert out.new_rumors == []
        assert out.faction_moves == []
        assert out.hidden_events == []
        assert out.updated_factions is None

    def test_elapsed_time_summary(self):
        """Should always have an elapsed_time_summary."""
        out = simulate_faction_tick(
            active_factions=REBELLION_FACTIONS,
            turn_number=1,
            player_location="loc-cantina",
        )
        assert isinstance(out.elapsed_time_summary, str)
        assert len(out.elapsed_time_summary) > 5

    def test_single_faction(self):
        """Should work with a single faction."""
        out = simulate_faction_tick(
            active_factions=[REBELLION_FACTIONS[0]],
            turn_number=1,
            player_location="loc-cantina",
        )
        assert len(out.new_rumors) >= 1
        assert out.updated_factions is not None
        assert len(out.updated_factions) == 1

    def test_rumor_text_contains_faction_or_location(self):
        """Rumors should reference a faction name or location."""
        out = simulate_faction_tick(
            active_factions=REBELLION_FACTIONS,
            turn_number=1,
            player_location="loc-cantina",
        )
        for rumor in out.new_rumors:
            # Rumor should contain at least one of: faction name, location, or generic reference
            has_reference = any(
                f.get("name", "").lower() in rumor.lower()
                for f in REBELLION_FACTIONS
            ) or "loc-" in rumor.lower() or any(
                word in rumor.lower()
                for word in ["spacers", "sector", "whispers", "travelers", "rumor"]
            )
            assert has_reference, f"Rumor has no faction/location reference: {rumor}"


class TestPrimaryTag:
    """Tests for _primary_tag helper."""

    def test_rebel_detection(self):
        assert _primary_tag({"name": "Rebel Alliance"}) == "rebel"

    def test_imperial_detection(self):
        assert _primary_tag({"name": "Galactic Empire"}) == "imperial"

    def test_criminal_detection(self):
        assert _primary_tag({"name": "Hutt Cartel"}) == "criminal"

    def test_hostile_default(self):
        """Hostile faction with no matching tags defaults to imperial."""
        assert _primary_tag({"name": "Unknown Force", "is_hostile": True}) == "imperial"

    def test_unknown_default(self):
        assert _primary_tag({"name": "Some Group"}) == "default"
