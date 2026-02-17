"""Tests for V2.20 era-pack companion support, PartyState, affordances, and banter guard."""
from __future__ import annotations

import pytest

from backend.app.world.era_pack_models import (
    EraCompanion,
    EraCompanionBanter,
    EraCompanionInfluence,
    EraCompanionRecruitment,
    EraCompanionVoice,
    EraPack,
)
from backend.app.content.repository import CONTENT_REPOSITORY
from backend.app.core.party_state import (
    PartyState,
    add_companion_to_party,
    remove_companion_from_party,
    apply_influence_delta,
    load_party_state,
    save_party_state,
    compute_available_affordances,
    compute_influence_from_response,
)
from backend.app.core.banter_manager import _is_safe_for_banter


# ---------------------------------------------------------------------------
# A) Era Pack Schema + Loading
# ---------------------------------------------------------------------------

class TestEraCompanionSchema:
    """EraCompanion Pydantic model validates correctly."""

    def test_minimal_companion(self):
        comp = EraCompanion(id="comp-test", name="Test")
        assert comp.id == "comp-test"
        assert comp.species == "Human"
        assert comp.role_in_party == "companion"
        assert comp.enables_affordances == []
        assert comp.blocks_affordances == []

    def test_full_companion(self):
        comp = EraCompanion(
            id="comp-kessa",
            name="Kessa Vane",
            species="Zabrak",
            gender="female",
            archetype="Alliance scout",
            faction_id="fac-rebel-alliance",
            role_in_party="specialist",
            voice_tags=["determined", "analytical"],
            motivation="Map safe routes.",
            speech_quirk="Lists options under breath.",
            voice=EraCompanionVoice(
                belief="Every route saved is a hundred lives.",
                wound="Lost her scouting cell.",
                taboo="Never fly blind.",
                rhetorical_style="analytical",
                tell="Traces star charts on surfaces.",
            ),
            traits={"idealist_pragmatic": 40, "merciful_ruthless": -20},
            default_affinity=5,
            recruitment=EraCompanionRecruitment(
                unlock_conditions="Assist with supply run.",
                first_meeting_location="loc-safe_house",
            ),
            tags=["scout", "navigator"],
            enables_affordances=["astrogation", "sensor_sweep"],
            influence=EraCompanionInfluence(
                starts_at=5,
                triggers=[{"intent": "threaten", "delta": -3}],
            ),
            banter=EraCompanionBanter(style="warm", triggers=["hyperspace"]),
        )
        assert comp.enables_affordances == ["astrogation", "sensor_sweep"]
        assert comp.influence.starts_at == 5
        assert comp.banter.style == "warm"

    def test_companion_in_era_pack(self):
        """EraCompanion can be embedded in EraPack.companions."""
        pack = EraPack(
            era_id="TEST",
            companions=[
                EraCompanion(id="comp-1", name="Alpha"),
                EraCompanion(id="comp-2", name="Beta"),
            ],
        )
        assert len(pack.companions) == 2
        assert pack.companion_by_id("comp-1") is not None
        assert pack.companion_by_id("comp-1").name == "Alpha"
        assert pack.companion_by_id("comp-missing") is None


class TestEraPackCompanionLoading:
    """Rebellion era pack loads companions.yaml correctly."""

    def setup_method(self):
        CONTENT_REPOSITORY.clear_cache()

    def test_rebellion_pack_has_companions(self):
        pack = CONTENT_REPOSITORY.get_pack("REBELLION")
        assert len(pack.companions) >= 1
        kessa = pack.companion_by_id("comp-reb-kessa")
        assert kessa is not None
        assert kessa.name == "Kessa Vane"
        assert kessa.species == "Zabrak"
        assert "astrogation" in kessa.enables_affordances

    def test_companion_reference_validation(self):
        """Companion with invalid faction_id should fail validation in strict mode."""
        import shared.config as _cfg
        _orig = _cfg.ERA_PACK_LENIENT_VALIDATION
        _cfg.ERA_PACK_LENIENT_VALIDATION = False
        try:
            with pytest.raises(ValueError, match="faction"):
                EraPack(
                    era_id="TEST",
                    factions=[],
                    companions=[
                        EraCompanion(id="comp-bad", name="Bad", faction_id="fac-nonexistent"),
                    ],
                )
        finally:
            _cfg.ERA_PACK_LENIENT_VALIDATION = _orig


# ---------------------------------------------------------------------------
# B) PartyState + CompanionRuntimeState
# ---------------------------------------------------------------------------

class TestPartyState:
    """PartyState CRUD and persistence."""

    def test_add_remove_companion(self):
        ps = PartyState()
        assert add_companion_to_party(ps, "comp-1", initial_influence=10, traits={"a": 5})
        assert ps.has_companion("comp-1")
        assert ps.companion_states["comp-1"].influence == 10
        # Adding again returns False
        assert not add_companion_to_party(ps, "comp-1")
        # Remove
        assert remove_companion_from_party(ps, "comp-1")
        assert not ps.has_companion("comp-1")
        assert not remove_companion_from_party(ps, "comp-1")

    def test_influence_delta(self):
        ps = PartyState()
        add_companion_to_party(ps, "comp-1", initial_influence=50)
        new_val = apply_influence_delta(ps, "comp-1", 10, "paragon choice")
        assert new_val == 60
        # Clamp at 100
        apply_influence_delta(ps, "comp-1", 200, "huge bonus")
        assert ps.companion_states["comp-1"].influence == 100
        # Clamp at -100
        apply_influence_delta(ps, "comp-1", -300, "big penalty")
        assert ps.companion_states["comp-1"].influence == -100
        # Nonexistent companion
        assert apply_influence_delta(ps, "comp-missing", 5) == 0

    def test_influence_axes(self):
        ps = PartyState()
        add_companion_to_party(ps, "comp-1")
        apply_influence_delta(ps, "comp-1", 5, "test", trust_delta=10, respect_delta=-5, fear_delta=3)
        cs = ps.companion_states["comp-1"]
        assert cs.trust == 10
        assert cs.respect == -5
        assert cs.fear == 3

    def test_significant_moments_recorded(self):
        ps = PartyState()
        add_companion_to_party(ps, "comp-1")
        apply_influence_delta(ps, "comp-1", 3, "helped them escape")
        assert len(ps.companion_states["comp-1"].memories) == 1
        # Small deltas don't record
        apply_influence_delta(ps, "comp-1", 1, "minor")
        assert len(ps.companion_states["comp-1"].memories) == 1

    def test_load_save_roundtrip(self):
        ps = PartyState()
        add_companion_to_party(ps, "comp-1", initial_influence=25, traits={"a": 10})
        ws: dict = {}
        save_party_state(ws, ps)
        # Legacy fields written
        assert ws["party"] == ["comp-1"]
        assert ws["party_affinity"]["comp-1"] == 25
        # Reload
        ps2 = load_party_state(ws)
        assert ps2.active_companions == ["comp-1"]
        assert ps2.companion_states["comp-1"].influence == 25

    def test_backward_compat_migration(self):
        """Legacy world_state without party_state field migrates correctly."""
        ws = {
            "party": ["comp-a", "comp-b"],
            "party_affinity": {"comp-a": 30, "comp-b": -10},
            "party_traits": {"comp-a": {"idealist_pragmatic": 50}},
            "loyalty_progress": {"comp-a": 40},
        }
        ps = load_party_state(ws)
        assert ps.active_companions == ["comp-a", "comp-b"]
        assert ps.companion_states["comp-a"].influence == 30
        assert ps.companion_states["comp-a"].traits == {"idealist_pragmatic": 50}
        assert ps.companion_states["comp-a"].loyalty_progress == 40


# ---------------------------------------------------------------------------
# C) Companion Affordances
# ---------------------------------------------------------------------------

class TestCompanionAffordances:
    """Affordance merging from location + companions."""

    def test_enables_adds_affordances(self):
        ps = PartyState()
        add_companion_to_party(ps, "comp-1")
        # Simulate companion with enables_affordances
        ps.companion_states["comp-1"].companion_id = "comp-1"
        # Direct test of compute_available_affordances
        result = compute_available_affordances(["medbay", "arms_dealer"], ps)
        # Should include location services (companion_affordances returns empty for unknown comp)
        assert "medbay" in result
        assert "arms_dealer" in result

    def test_empty_party_returns_location_only(self):
        ps = PartyState()
        result = compute_available_affordances(["medbay"], ps)
        assert result == ["medbay"]


# ---------------------------------------------------------------------------
# D) Banter Safety Guard
# ---------------------------------------------------------------------------

class TestBanterSafetyGuard:
    """Banter only triggers during safe scenes."""

    def test_travel_quiet_is_safe(self):
        frame = {"allowed_scene_type": "travel", "pressure": {"alert": "Quiet", "heat": "Low"}}
        assert _is_safe_for_banter(frame, {}) is True

    def test_exploration_quiet_is_safe(self):
        frame = {"allowed_scene_type": "exploration", "pressure": {"alert": "Quiet", "heat": "Low"}}
        assert _is_safe_for_banter(frame, {}) is True

    def test_combat_is_never_safe(self):
        frame = {"allowed_scene_type": "combat", "pressure": {"alert": "Quiet", "heat": "Low"}}
        assert _is_safe_for_banter(frame, {}) is False

    def test_stealth_is_never_safe(self):
        frame = {"allowed_scene_type": "stealth", "pressure": {"alert": "Quiet", "heat": "Low"}}
        assert _is_safe_for_banter(frame, {}) is False

    def test_watchful_alert_blocks_banter(self):
        frame = {"allowed_scene_type": "travel", "pressure": {"alert": "Watchful", "heat": "Low"}}
        assert _is_safe_for_banter(frame, {}) is False

    def test_lockdown_blocks_banter(self):
        frame = {"allowed_scene_type": "dialogue", "pressure": {"alert": "Lockdown", "heat": "Low"}}
        assert _is_safe_for_banter(frame, {}) is False

    def test_wanted_heat_blocks_banter(self):
        frame = {"allowed_scene_type": "travel", "pressure": {"alert": "Quiet", "heat": "Wanted"}}
        assert _is_safe_for_banter(frame, {}) is False

    def test_dialogue_quiet_low_is_safe(self):
        frame = {"allowed_scene_type": "dialogue", "pressure": {"alert": "Quiet", "heat": "Low"}}
        assert _is_safe_for_banter(frame, {}) is True

    def test_dialogue_noticed_heat_blocks(self):
        frame = {"allowed_scene_type": "dialogue", "pressure": {"alert": "Quiet", "heat": "Noticed"}}
        assert _is_safe_for_banter(frame, {}) is False

    def test_no_scene_frame_blocks(self):
        assert _is_safe_for_banter(None, {}) is False


# ---------------------------------------------------------------------------
# E) Influence from Response
# ---------------------------------------------------------------------------

class TestInfluenceFromResponse:
    """compute_influence_from_response uses trait-based and trigger-based deltas."""

    def test_trait_based_influence(self):
        ps = PartyState()
        add_companion_to_party(
            ps, "comp-1", initial_influence=0,
            traits={"idealist_pragmatic": 80, "merciful_ruthless": -60},
        )
        # PARAGON tone should produce positive delta for idealist+merciful companion
        results = compute_influence_from_response(ps, "talk", "", "PARAGON")
        assert "comp-1" in results
        delta, reason = results["comp-1"]
        assert delta > 0

    def test_no_delta_for_neutral(self):
        ps = PartyState()
        add_companion_to_party(ps, "comp-1", traits={"idealist_pragmatic": 0, "merciful_ruthless": 0})
        results = compute_influence_from_response(ps, "talk", "", "NEUTRAL")
        # Should be empty (no reaction to neutral from balanced traits)
        assert "comp-1" not in results

    def test_empty_party_returns_empty(self):
        ps = PartyState()
        results = compute_influence_from_response(ps, "talk", "", "PARAGON")
        assert results == {}
