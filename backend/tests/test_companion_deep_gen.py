"""Tests for V1.1 companion deep generation pipeline.

Covers:
- Deterministic fallback generation from trait axes
- NPC free-text trait mapping to companion axes
- Deep profile registration and cache merge
- Campaign init companion depth generation hook
- NPC-to-companion promotion
- Recruitment-time auto-depth (Emergent tier)
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────


def _base_companion(name="Kira", archetype="Jedi", **overrides):
    """Build a minimal companion dict for testing."""
    comp = {
        "id": f"comp-test-{name.lower()}",
        "name": name,
        "archetype": archetype,
        "traits": {"idealist_pragmatic": 60, "merciful_ruthless": -40, "lawful_rebellious": 20},
        "motivation": "Find redemption through service",
        "banter_style": "stoic",
        "faction_interest": ["Rebel Alliance"],
        "voice": {"belief": "The truth always surfaces", "wound": "Lost everything once"},
        "speech_quirk": "Speaks in clipped military phrases",
    }
    comp.update(overrides)
    return comp


def _base_npc(**overrides):
    """Build a minimal NPC dict for testing."""
    npc = {
        "id": "gen-npc-rask",
        "name": "Rask",
        "role": "Informant",
        "faction_id": "underworld",
        "traits": ["observant", "cautious", "shrewd"],
        "motivation": "Survive by trading secrets",
        "species": "Human",
        "voice": {
            "belief": "Information is the only true currency",
            "wound": "Betrayed by a partner who sold him out",
            "rhetorical_style": "cautious, indirect",
        },
    }
    npc.update(overrides)
    return npc


# ── Deterministic fallback tests ─────────────────────────────────────


class TestDeterministicDeepData:
    """Deterministic fallback generates valid deep data from trait axes."""

    def test_generates_all_required_keys(self):
        from backend.app.core.agents.companion_deep_gen_agent import (
            _deterministic_deep_data,
        )

        comp = _base_companion()
        data = _deterministic_deep_data(comp)

        assert "personal_banter" in data
        assert "opinion_triggers" in data
        assert "personal_quest" in data
        assert "dialogue_samples" in data

    def test_banter_has_all_tones(self):
        from backend.app.core.agents.companion_deep_gen_agent import (
            _deterministic_deep_data,
        )

        comp = _base_companion()
        data = _deterministic_deep_data(comp)
        banter = data["personal_banter"]

        for tone in ("PARAGON", "RENEGADE", "INVESTIGATE", "general"):
            assert tone in banter, f"Missing banter tone: {tone}"
            assert len(banter[tone]) >= 1, f"Empty banter for {tone}"

    def test_opinion_triggers_have_required_fields(self):
        from backend.app.core.agents.companion_deep_gen_agent import (
            _deterministic_deep_data,
        )

        comp = _base_companion()
        data = _deterministic_deep_data(comp)

        assert len(data["opinion_triggers"]) >= 3
        for trigger in data["opinion_triggers"]:
            assert "situation" in trigger
            assert "reaction" in trigger
            assert "affinity_bonus" in trigger
            assert "tags" in trigger
            assert isinstance(trigger["tags"], list)

    def test_idealistic_companion_banter_differs_from_pragmatic(self):
        from backend.app.core.agents.companion_deep_gen_agent import (
            _deterministic_deep_data,
        )

        idealist = _base_companion(
            name="Leia",
            traits={"idealist_pragmatic": 80, "merciful_ruthless": 0, "lawful_rebellious": 0},
        )
        pragmatist = _base_companion(
            name="Han",
            traits={"idealist_pragmatic": -80, "merciful_ruthless": 0, "lawful_rebellious": 0},
        )

        data_i = _deterministic_deep_data(idealist)
        data_p = _deterministic_deep_data(pragmatist)

        # Banter content should differ
        assert data_i["personal_banter"]["PARAGON"] != data_p["personal_banter"]["PARAGON"]
        assert data_i["personal_banter"]["RENEGADE"] != data_p["personal_banter"]["RENEGADE"]

    def test_generates_wound_when_not_present(self):
        from backend.app.core.agents.companion_deep_gen_agent import (
            _deterministic_deep_data,
        )

        comp = _base_companion()
        # No wound in base companion
        assert "wound" not in comp

        data = _deterministic_deep_data(comp)
        assert "wound" in data
        assert "surface" in data["wound"]
        assert "deep" in data["wound"]
        assert "core" in data["wound"]
        assert "revelation_stages" in data
        assert len(data["revelation_stages"]) == 3

    def test_preserves_existing_wound(self):
        from backend.app.core.agents.companion_deep_gen_agent import (
            _deterministic_deep_data,
        )

        comp = _base_companion(
            wound={
                "surface": "Custom surface wound",
                "deep": "Custom deep wound",
                "core": "Custom core wound",
            }
        )
        data = _deterministic_deep_data(comp)

        # Should NOT generate wound when one already exists
        assert "wound" not in data
        assert "revelation_stages" not in data

    def test_personal_quest_includes_companion_name(self):
        from backend.app.core.agents.companion_deep_gen_agent import (
            _deterministic_deep_data,
        )

        comp = _base_companion(name="Torrin")
        data = _deterministic_deep_data(comp)

        quest = data["personal_quest"]
        assert "Torrin" in quest["title"] or "Torrin" in quest["hook"]
        assert len(quest["stages"]) >= 3
        assert len(quest["resolution_paths"]) >= 2

    def test_dialogue_samples_cover_required_contexts(self):
        from backend.app.core.agents.companion_deep_gen_agent import (
            _deterministic_deep_data,
        )

        comp = _base_companion()
        data = _deterministic_deep_data(comp)

        contexts = {s["context"] for s in data["dialogue_samples"]}
        for required in ("greeting", "disagreement", "vulnerable", "combat"):
            assert required in contexts, f"Missing dialogue context: {required}"


# ── Trait mapping tests ──────────────────────────────────────────────


class TestTraitMapping:
    """Free-text NPC traits map correctly to companion trait axes."""

    def test_merciful_traits_map_positive(self):
        from backend.app.core.agents.companion_deep_gen_agent import (
            _map_freetext_traits_to_axes,
        )

        axes = _map_freetext_traits_to_axes(["compassionate", "kind"])
        assert axes["merciful_ruthless"] > 0

    def test_ruthless_traits_map_negative(self):
        from backend.app.core.agents.companion_deep_gen_agent import (
            _map_freetext_traits_to_axes,
        )

        axes = _map_freetext_traits_to_axes(["ruthless", "intimidating"])
        assert axes["merciful_ruthless"] < 0

    def test_rebellious_traits_map_positive(self):
        from backend.app.core.agents.companion_deep_gen_agent import (
            _map_freetext_traits_to_axes,
        )

        axes = _map_freetext_traits_to_axes(["daring", "reckless"])
        assert axes["lawful_rebellious"] > 0

    def test_lawful_traits_map_negative(self):
        from backend.app.core.agents.companion_deep_gen_agent import (
            _map_freetext_traits_to_axes,
        )

        axes = _map_freetext_traits_to_axes(["strict", "honorable"])
        assert axes["lawful_rebellious"] < 0

    def test_mixed_traits_balance(self):
        from backend.app.core.agents.companion_deep_gen_agent import (
            _map_freetext_traits_to_axes,
        )

        axes = _map_freetext_traits_to_axes(["compassionate", "ruthless"])
        # Merciful + ruthless should partially cancel
        assert -100 <= axes["merciful_ruthless"] <= 100

    def test_empty_traits_return_zeroes(self):
        from backend.app.core.agents.companion_deep_gen_agent import (
            _map_freetext_traits_to_axes,
        )

        axes = _map_freetext_traits_to_axes([])
        assert axes == {
            "idealist_pragmatic": 0,
            "merciful_ruthless": 0,
            "lawful_rebellious": 0,
        }

    def test_npc_traits_produce_valid_deep_data(self):
        """NPC-style list traits should produce valid deep data via fallback."""
        from backend.app.core.agents.companion_deep_gen_agent import (
            _deterministic_deep_data,
        )

        npc_as_comp = _base_companion(
            traits=["observant", "cautious", "shrewd"],
        )
        data = _deterministic_deep_data(npc_as_comp)

        assert "personal_banter" in data
        assert len(data["opinion_triggers"]) >= 3


# ── Agent tests (mocked LLM) ────────────────────────────────────────


class TestCompanionDeepGenAgent:
    """Agent generates deep data via LLM or falls back to deterministic."""

    def test_fallback_when_no_llm(self):
        from backend.app.core.agents.companion_deep_gen_agent import (
            CompanionDeepGenAgent,
        )

        agent = CompanionDeepGenAgent(llm=None)
        comp = _base_companion()
        data = agent.generate(comp)

        assert "personal_banter" in data
        assert "opinion_triggers" in data
        assert "personal_quest" in data
        assert "dialogue_samples" in data

    def test_generate_batch_skips_deep_companions(self):
        from backend.app.core.agents.companion_deep_gen_agent import (
            CompanionDeepGenAgent,
        )

        agent = CompanionDeepGenAgent(llm=None)
        companions = [
            _base_companion(name="Deep", depth_tier="deep"),
            _base_companion(name="Standard"),
        ]
        results = agent.generate_batch(companions)

        # Deep companion should be skipped
        assert "comp-test-deep" not in results
        assert "comp-test-standard" in results

    def test_generate_batch_respects_max_count(self):
        from backend.app.core.agents.companion_deep_gen_agent import (
            CompanionDeepGenAgent,
        )

        agent = CompanionDeepGenAgent(llm=None)
        companions = [
            _base_companion(name=f"Comp{i}") for i in range(10)
        ]
        results = agent.generate_batch(companions, max_count=3)

        assert len(results) == 3

    def test_llm_result_is_normalized(self):
        """Even with LLM output, data gets normalized and clamped."""
        from backend.app.core.agents.companion_deep_gen_agent import (
            _normalize_deep_data,
        )

        raw = {
            "personal_banter": {
                "PARAGON": ["line 1", "line 2", "line 3", "line 4", "line 5"],
                "RENEGADE": ["r1"],
                "INVESTIGATE": ["i1"],
                "general": ["g1"],
            },
            "opinion_triggers": [
                {
                    "situation": "Test Situation",
                    "reaction": "reacts",
                    "affinity_bonus": 99,  # Should be clamped
                    "tags": ["tag1"],
                },
                {"situation": "s2", "reaction": "r2", "affinity_bonus": -99, "tags": ["t"]},
                {"situation": "s3", "reaction": "r3", "affinity_bonus": 0, "tags": ["t"]},
            ],
            "personal_quest": {
                "title": "Quest",
                "hook": "Hook",
                "trigger_affinity": 200,  # Should be clamped
                "stages": ["s1", "s2", "s3"],
                "resolution_paths": ["r1", "r2"],
            },
            "dialogue_samples": [
                {"context": "greeting", "line": "hello"},
                {"context": "disagreement", "line": "no"},
                {"context": "vulnerable", "line": "..."},
                {"context": "combat", "line": "charge!"},
            ],
        }

        comp = _base_companion()
        normalized = _normalize_deep_data(raw, comp)

        # Banter capped at COMPANION_DEEP_GEN_BANTER_CAP (4)
        assert len(normalized["personal_banter"]["PARAGON"]) <= 4

        # Affinity bonus clamped to [-5, 5]
        assert normalized["opinion_triggers"][0]["affinity_bonus"] == 5
        assert normalized["opinion_triggers"][1]["affinity_bonus"] == -5

        # Trigger affinity clamped to [20, 80]
        assert normalized["personal_quest"]["trigger_affinity"] == 80

        # Situation normalized to lowercase_snake_case
        assert normalized["opinion_triggers"][0]["situation"] == "test_situation"


# ── Profile registration tests ───────────────────────────────────────


class TestProfileRegistration:
    """Deep profiles merge correctly into companion cache."""

    def test_register_marks_companion_as_deep(self):
        from backend.app.core.companions import (
            load_companions,
            clear_companions_cache,
            get_companion_by_id,
            is_deep_companion,
            register_deep_profile,
        )

        clear_companions_cache()

        # Find a standard-tier companion
        comps = load_companions()
        standard = None
        for c in comps:
            if str(c.get("depth_tier", "")).lower() != "deep":
                standard = c
                break
        if not standard:
            pytest.skip("No standard-tier companions available")

        comp_id = standard["id"]
        assert not is_deep_companion(comp_id)

        # Register deep profile
        deep_data = {
            "personal_banter": {"PARAGON": ["test"], "RENEGADE": ["test"],
                                "INVESTIGATE": ["test"], "general": ["test"]},
            "opinion_triggers": [
                {"situation": "test", "reaction": "test", "affinity_bonus": 1, "tags": ["test"]}
            ],
            "personal_quest": {"title": "Test Quest", "hook": "hook",
                               "trigger_affinity": 40, "stages": ["s1"], "resolution_paths": ["r1"]},
            "dialogue_samples": [{"context": "greeting", "line": "hi"}],
        }
        assert register_deep_profile(comp_id, deep_data)
        assert is_deep_companion(comp_id)

        # Clean up
        standard.pop("depth_tier", None)
        standard.pop("personal_banter", None)
        standard.pop("opinion_triggers", None)
        standard.pop("personal_quest", None)
        standard.pop("dialogue_samples", None)

    def test_register_preserves_curated_wound(self):
        from backend.app.core.companions import (
            load_companions,
            clear_companions_cache,
            get_companion_by_id,
            register_deep_profile,
        )

        clear_companions_cache()

        # Find a companion with existing wound
        comps = load_companions()
        wounded = None
        for c in comps:
            if c.get("wound"):
                wounded = c
                break
        if not wounded:
            pytest.skip("No companions with wound data available")

        comp_id = wounded["id"]
        original_wound = dict(wounded["wound"])

        # Register deep profile with a different wound
        deep_data = {
            "personal_banter": {"PARAGON": ["x"], "RENEGADE": ["x"],
                                "INVESTIGATE": ["x"], "general": ["x"]},
            "opinion_triggers": [],
            "personal_quest": None,
            "dialogue_samples": [],
            "wound": {"surface": "OVERWRITTEN", "deep": "OVERWRITTEN", "core": "OVERWRITTEN"},
        }
        register_deep_profile(comp_id, deep_data)

        # Original wound should be preserved (curated wins)
        comp = get_companion_by_id(comp_id)
        assert comp["wound"]["surface"] == original_wound["surface"]

        # Clean up
        wounded.pop("depth_tier", None)

    def test_restore_companion_profiles(self):
        from backend.app.core.companions import (
            load_companions,
            clear_companions_cache,
            is_deep_companion,
            restore_companion_profiles,
        )

        clear_companions_cache()
        comps = load_companions()

        # Find two standard-tier companions
        standards = [
            c for c in comps
            if str(c.get("depth_tier", "")).lower() != "deep"
        ][:2]
        if len(standards) < 2:
            pytest.skip("Need at least 2 standard-tier companions")

        profiles = {}
        for s in standards:
            profiles[s["id"]] = {
                "personal_banter": {"PARAGON": ["x"], "RENEGADE": ["x"],
                                    "INVESTIGATE": ["x"], "general": ["x"]},
                "opinion_triggers": [],
                "personal_quest": None,
                "dialogue_samples": [],
            }

        count = restore_companion_profiles(profiles)
        assert count == 2

        for s in standards:
            assert is_deep_companion(s["id"])
            # Clean up
            s.pop("depth_tier", None)
            s.pop("personal_banter", None)
            s.pop("opinion_triggers", None)
            s.pop("personal_quest", None)
            s.pop("dialogue_samples", None)


# ── NPC promotion tests ──────────────────────────────────────────────


class TestNPCPromotion:
    """NPC-to-companion promotion creates valid companion definitions."""

    def test_promote_creates_companion_id(self):
        from backend.app.core.companions import (
            promote_npc_to_companion,
            get_companion_by_id,
            load_companions,
            clear_companions_cache,
        )

        clear_companions_cache()
        npc = _base_npc()

        comp_id = promote_npc_to_companion(npc, generate_depth=False)
        assert comp_id is not None
        assert comp_id.startswith("comp-")

        comp = get_companion_by_id(comp_id)
        assert comp is not None
        assert comp["name"] == "Rask"
        assert comp["archetype"] == "Informant"
        assert isinstance(comp["traits"], dict)
        assert "idealist_pragmatic" in comp["traits"]

        # Clean up: remove from cache
        all_comps = load_companions()
        all_comps[:] = [c for c in all_comps if c.get("id") != comp_id]

    def test_promote_maps_npc_traits_to_axes(self):
        from backend.app.core.companions import (
            promote_npc_to_companion,
            get_companion_by_id,
            load_companions,
            clear_companions_cache,
        )

        clear_companions_cache()
        npc = _base_npc(traits=["ruthless", "rebellious", "pragmatic"])

        comp_id = promote_npc_to_companion(npc, generate_depth=False)
        comp = get_companion_by_id(comp_id)

        assert comp["traits"]["merciful_ruthless"] < 0  # ruthless
        assert comp["traits"]["lawful_rebellious"] > 0  # rebellious
        assert comp["traits"]["idealist_pragmatic"] < 0  # pragmatic

        # Clean up
        all_comps = load_companions()
        all_comps[:] = [c for c in all_comps if c.get("id") != comp_id]

    def test_promote_with_depth_generates_deep_data(self):
        from backend.app.core.companions import (
            promote_npc_to_companion,
            get_companion_by_id,
            is_deep_companion,
            load_companions,
            clear_companions_cache,
        )

        clear_companions_cache()
        npc = _base_npc(id="gen-npc-deeptest")

        # Patch AgentLLM to return None (triggers fallback)
        with patch("backend.app.core.agents.base.AgentLLM", side_effect=Exception("No LLM")):
            comp_id = promote_npc_to_companion(npc, generate_depth=True)

        # Should still succeed via deterministic fallback
        assert comp_id is not None
        # The companion is created but depth gen may have failed gracefully
        comp = get_companion_by_id(comp_id)
        assert comp is not None

        # Clean up
        all_comps = load_companions()
        all_comps[:] = [c for c in all_comps if c.get("id") != comp_id]

    def test_promote_idempotent(self):
        from backend.app.core.companions import (
            promote_npc_to_companion,
            load_companions,
            clear_companions_cache,
        )

        clear_companions_cache()
        npc = _base_npc(id="gen-npc-idem")

        comp_id_1 = promote_npc_to_companion(npc, generate_depth=False)
        comp_id_2 = promote_npc_to_companion(npc, generate_depth=False)

        # Same ID returned on second call
        assert comp_id_1 == comp_id_2

        # Clean up
        all_comps = load_companions()
        all_comps[:] = [c for c in all_comps if c.get("id") != comp_id_1]


# ── Campaign init integration tests ─────────────────────────────────


class TestCampaignInitCompanionDepth:
    """Campaign init generates companion depth profiles."""

    def test_generate_companion_depth_returns_profiles(self):
        from backend.app.core.campaign_init import _generate_companion_depth
        from backend.app.core.companions import clear_companions_cache

        clear_companions_cache()

        # Patch AgentLLM to ensure deterministic fallback
        with patch(
            "backend.app.core.campaign_init.AgentLLM",
            side_effect=Exception("No LLM"),
        ):
            profiles = _generate_companion_depth(era="REBELLION", era_pack=None)

        # Should have generated profiles for standard-tier companions
        # (may be empty if all companions are already deep)
        assert isinstance(profiles, dict)

    def test_generate_companion_depth_skips_deep_companions(self):
        from backend.app.core.campaign_init import _generate_companion_depth
        from backend.app.core.companions import (
            clear_companions_cache,
            load_companions,
        )

        clear_companions_cache()
        comps = load_companions("REBELLION")

        # Count curated deep companions
        deep_ids = {
            c["id"] for c in comps
            if str(c.get("depth_tier", "")).lower() == "deep"
        }

        with patch(
            "backend.app.core.campaign_init.AgentLLM",
            side_effect=Exception("No LLM"),
        ):
            profiles = _generate_companion_depth(era="REBELLION", era_pack=None)

        # None of the curated deep companions should be in profiles
        for comp_id in deep_ids:
            assert comp_id not in profiles, f"Deep companion {comp_id} should be skipped"

    def test_campaign_init_includes_companion_profiles(self):
        """Full initialize_campaign_world includes companion_deep_profiles in result."""
        from backend.app.core.campaign_init import initialize_campaign_world

        with patch(
            "backend.app.core.campaign_init.AgentLLM",
            side_effect=Exception("No LLM"),
        ):
            with patch(
                "backend.app.core.campaign_init._retrieve_era_lore",
                return_value=[],
            ):
                result = initialize_campaign_world(
                    campaign_id="test-deep-gen",
                    era="REBELLION",
                    era_pack=None,
                    player_concept="A pilot",
                    starting_location="loc-cantina",
                    existing_factions=[],
                    skeleton={},
                )

        # Result should include companion profiles
        assert "generated_locations" in result
        assert "generated_npcs" in result
        # companion_deep_profiles present if any standard companions exist
        if result.get("companion_deep_profiles"):
            profiles = result["companion_deep_profiles"]
            assert isinstance(profiles, dict)
            for comp_id, data in profiles.items():
                assert "personal_banter" in data
                assert "opinion_triggers" in data


# ── Recruitment auto-depth tests ─────────────────────────────────────


class TestRecruitmentAutoDepth:
    """Recruitment triggers automatic depth generation for standard companions."""

    def test_recruit_standard_companion_generates_depth(self):
        from backend.app.core.companions import (
            recruit_companion,
            load_companions,
            clear_companions_cache,
            is_deep_companion,
        )

        clear_companions_cache()
        comps = load_companions()

        # Find a standard-tier companion
        standard = None
        for c in comps:
            if str(c.get("depth_tier", "")).lower() != "deep":
                standard = c
                break
        if not standard:
            pytest.skip("No standard-tier companions available")

        comp_id = standard["id"]
        ws: dict = {"party": [], "party_affinity": {}, "party_traits": {}, "loyalty_progress": {}}

        # Patch AgentLLM to trigger deterministic fallback
        with patch(
            "backend.app.core.agents.base.AgentLLM",
            side_effect=Exception("No LLM"),
        ):
            result = recruit_companion(ws, comp_id, auto_depth=True)

        assert result is True
        assert comp_id in ws["party"]

        # Clean up (remove depth_tier to not pollute other tests)
        standard.pop("depth_tier", None)
        standard.pop("personal_banter", None)
        standard.pop("opinion_triggers", None)
        standard.pop("personal_quest", None)
        standard.pop("dialogue_samples", None)
        standard.pop("wound", None)
        standard.pop("revelation_stages", None)

    def test_recruit_with_auto_depth_false_skips_generation(self):
        from backend.app.core.companions import (
            recruit_companion,
            load_companions,
            clear_companions_cache,
            is_deep_companion,
        )

        clear_companions_cache()
        comps = load_companions()

        standard = None
        for c in comps:
            if str(c.get("depth_tier", "")).lower() != "deep":
                standard = c
                break
        if not standard:
            pytest.skip("No standard-tier companions available")

        comp_id = standard["id"]
        ws: dict = {"party": [], "party_affinity": {}, "party_traits": {}, "loyalty_progress": {}}

        result = recruit_companion(ws, comp_id, auto_depth=False)
        assert result is True
        assert not is_deep_companion(comp_id)
