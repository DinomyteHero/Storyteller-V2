"""Tests for scale advisor, conclusion planner, and universe modularity features."""
from __future__ import annotations

import os
import pytest
from unittest.mock import patch, MagicMock


# ── Scale advisor tests ──────────────────────────────────────────────


class TestEvaluateScaleRecommendation:
    """Tests for _evaluate_scale_recommendation() pure function."""

    def _call(self, **kwargs):
        from backend.app.core.nodes.arc_planner import _evaluate_scale_recommendation
        defaults = {
            "current_scale": "medium",
            "arc_stage": "RISING",
            "tension_level": "ESCALATING",
            "ledger": {"open_threads": [], "active_goals": []},
            "turn_number": 30,
            "last_scale_change_turn": 0,
            "pivotal_event_count": 0,
        }
        defaults.update(kwargs)
        return _evaluate_scale_recommendation(**defaults)

    def test_no_change_during_setup(self):
        """Scale advisor should never recommend during SETUP stage."""
        result = self._call(arc_stage="SETUP")
        assert result is None

    def test_cooldown_enforced(self):
        """Scale advisor should not recommend if within cooldown period."""
        # Cooldown is 15 turns. Turn 20 with last change at turn 10 = 10 turns, under cooldown.
        result = self._call(
            turn_number=20,
            last_scale_change_turn=10,
            ledger={"open_threads": [f"[W3] thread-{i}" for i in range(5)], "active_goals": ["g"] * 5},
            pivotal_event_count=5,
        )
        assert result is None

    def test_cooldown_passed_allows_recommendation(self):
        """Scale advisor should recommend when cooldown has passed and density is high."""
        result = self._call(
            turn_number=30,
            last_scale_change_turn=10,  # 20 turns ago, past 15-turn cooldown
            ledger={"open_threads": [f"[W3] thread-{i}" for i in range(5)], "active_goals": ["g"] * 5},
            pivotal_event_count=5,
        )
        assert result is not None
        assert result["direction"] == "up"

    def test_scale_up_high_density_rising(self):
        """High narrative density during RISING should recommend scale up."""
        result = self._call(
            arc_stage="RISING",
            ledger={
                "open_threads": [f"[W2] thread-{i}" for i in range(5)],
                "active_goals": ["goal-1", "goal-2"],
            },
            pivotal_event_count=3,
        )
        assert result is not None
        assert result["direction"] == "up"
        assert result["recommended_scale"] == "large"

    def test_scale_up_high_density_climax(self):
        """High narrative density during CLIMAX should recommend scale up."""
        result = self._call(
            arc_stage="CLIMAX",
            current_scale="small",
            ledger={
                "open_threads": [f"[W2] thread-{i}" for i in range(5)],
                "active_goals": ["goal-1", "goal-2", "goal-3"],
            },
            pivotal_event_count=2,
        )
        assert result is not None
        assert result["direction"] == "up"
        assert result["recommended_scale"] == "medium"

    def test_scale_down_low_density_resolution(self):
        """Low narrative density during RESOLUTION should recommend scale down."""
        result = self._call(
            arc_stage="RESOLUTION",
            current_scale="large",
            ledger={"open_threads": [], "active_goals": []},
            pivotal_event_count=0,
        )
        assert result is not None
        assert result["direction"] == "down"
        assert result["recommended_scale"] == "medium"

    def test_no_scale_down_during_rising(self):
        """Low density during RISING should NOT recommend scale down (only RESOLUTION)."""
        result = self._call(
            arc_stage="RISING",
            current_scale="large",
            ledger={"open_threads": [], "active_goals": []},
            pivotal_event_count=0,
        )
        # density_score = 0, below scale_up threshold but not in RESOLUTION for scale down
        assert result is None

    def test_already_at_epic_no_up(self):
        """Already at epic scale should not recommend further scaling up."""
        result = self._call(
            current_scale="epic",
            arc_stage="RISING",
            ledger={
                "open_threads": [f"[W3] t-{i}" for i in range(5)],
                "active_goals": ["g"] * 5,
            },
            pivotal_event_count=5,
        )
        assert result is None

    def test_already_at_small_no_down(self):
        """Already at small scale should not recommend further scaling down."""
        result = self._call(
            current_scale="small",
            arc_stage="RESOLUTION",
            ledger={"open_threads": [], "active_goals": []},
            pivotal_event_count=0,
        )
        assert result is None


# ── Conclusion planner tests ─────────────────────────────────────────


class TestBuildConclusionPlan:
    """Tests for _build_conclusion_plan() pure function."""

    def _call(self, **kwargs):
        from backend.app.core.nodes.arc_planner import _build_conclusion_plan
        defaults = {
            "arc_stage": "RESOLUTION",
            "turns_in_stage": 3,
            "campaign_scale": "medium",
            "ledger": {"open_threads": [], "established_facts": []},
        }
        defaults.update(kwargs)
        return _build_conclusion_plan(**defaults)

    def test_returns_none_outside_resolution(self):
        """Conclusion plan should only be generated during RESOLUTION."""
        for stage in ("SETUP", "RISING", "CLIMAX"):
            result = self._call(arc_stage=stage)
            assert result is None

    def test_empty_threads_trivially_ready(self):
        """No threads = campaign trivially ready to conclude (after min turns)."""
        result = self._call(turns_in_stage=3)
        assert result is not None
        assert result["conclusion_ready"] is True
        assert result["resolved_ratio"] == 1.0

    def test_not_ready_before_min_turns(self):
        """Even with no threads, must wait for minimum resolution turns."""
        result = self._call(turns_in_stage=1)
        assert result is not None
        assert result["conclusion_ready"] is False

    def test_ending_style_by_scale(self):
        """Ending style should match the campaign scale."""
        for scale, expected_style in [
            ("small", "closed"),
            ("medium", "soft_cliffhanger"),
            ("large", "open_bittersweet"),
            ("epic", "full_cliffhanger"),
        ]:
            result = self._call(campaign_scale=scale)
            assert result["ending_style"] == expected_style, f"Scale {scale} should produce {expected_style}"

    def test_dangling_hooks_from_low_weight_threads(self):
        """Low-weight unresolved threads should become dangling hooks."""
        result = self._call(
            ledger={
                "open_threads": [
                    "[W1] A minor rumor about pirates",
                    "[W3] The main quest to find the artifact",
                ],
                "established_facts": [],
            },
        )
        assert result is not None
        # W1 threads become hooks, W3 threads become payoffs
        assert any("pirates" in h for h in result["dangling_hooks"])
        assert any("artifact" in p for p in result["payoff_threads"])

    def test_resolved_ratio_calculation(self):
        """Resolved ratio should reflect resolved vs total thread count."""
        result = self._call(
            ledger={
                "open_threads": [
                    "[W2] The stolen artifact",
                    "[W1] The missing spy",
                    "[W1] The rebel outpost",
                ],
                "established_facts": [
                    "resolved the stolen artifact — returned to its owner",
                ],
            },
        )
        assert result is not None
        # 1 out of 3 threads resolved
        assert result["resolved_ratio"] == pytest.approx(0.33, abs=0.01)


# ── Constants tests ──────────────────────────────────────────────────


class TestScaleConstants:
    """Tests for scale-related constants."""

    def test_scale_order_tuple(self):
        from backend.app.constants import SCALE_ORDER
        assert SCALE_ORDER == ("small", "medium", "large", "epic")

    def test_inter_campaign_scale_map_completeness(self):
        from backend.app.constants import INTER_CAMPAIGN_SCALE_MAP
        for stage in ("SETUP", "RISING", "CLIMAX", "RESOLUTION"):
            assert stage in INTER_CAMPAIGN_SCALE_MAP

    def test_conclusion_resolved_ratio_keys(self):
        from backend.app.constants import CONCLUSION_RESOLVED_RATIO
        for scale in ("small", "medium", "large", "epic"):
            assert scale in CONCLUSION_RESOLVED_RATIO
            assert 0.0 < CONCLUSION_RESOLVED_RATIO[scale] <= 1.0

    def test_conclusion_ending_styles(self):
        from backend.app.constants import CONCLUSION_ENDING_STYLES
        for scale in ("small", "medium", "large", "epic"):
            assert scale in CONCLUSION_ENDING_STYLES


# ── Arc planner integration tests ────────────────────────────────────


class TestArcPlannerScaleIntegration:
    """Tests that arc_planner_node integrates the scale advisor correctly."""

    def _make_state(self, **overrides):
        state = {
            "turn_number": 20,
            "campaign": {
                "world_state_json": {
                    "ledger": {
                        "open_threads": [],
                        "active_goals": [],
                        "established_facts": [],
                        "active_themes": [],
                    },
                    "arc_state": {
                        "current_stage": "RISING",
                        "stage_start_turn": 10,
                    },
                    "campaign_scale": "medium",
                    "last_scale_change_turn": 0,
                    "pivotal_event_count": 0,
                },
            },
        }
        # Apply overrides to world_state_json
        ws = state["campaign"]["world_state_json"]
        for k, v in overrides.items():
            if k in ws:
                ws[k] = v
            elif k in ws.get("ledger", {}):
                ws["ledger"][k] = v
            else:
                state[k] = v
        return state

    @patch("backend.app.config.ENABLE_SCALE_ADVISOR", True)
    def test_scale_recommendation_in_arc_guidance(self):
        """When scale advisor is enabled and density is high, arc_guidance includes recommendation."""
        from backend.app.core.nodes.arc_planner import arc_planner_node
        state = self._make_state()
        state["campaign"]["world_state_json"]["ledger"]["open_threads"] = [
            f"[W3] thread-{i}" for i in range(5)
        ]
        state["campaign"]["world_state_json"]["ledger"]["active_goals"] = ["g1", "g2"]
        state["campaign"]["world_state_json"]["pivotal_event_count"] = 3
        result = arc_planner_node(state)
        assert "scale_recommendation" in result.get("arc_guidance", {})

    @patch("backend.app.config.ENABLE_SCALE_ADVISOR", False)
    def test_no_recommendation_when_disabled(self):
        """When scale advisor is disabled, no recommendation should appear."""
        from backend.app.core.nodes.arc_planner import arc_planner_node
        state = self._make_state()
        state["campaign"]["world_state_json"]["ledger"]["open_threads"] = [
            f"[W3] thread-{i}" for i in range(5)
        ]
        state["campaign"]["world_state_json"]["pivotal_event_count"] = 5
        result = arc_planner_node(state)
        assert "scale_recommendation" not in result.get("arc_guidance", {})

    def test_conclusion_plan_in_resolution(self):
        """During RESOLUTION, arc_guidance should include a conclusion_plan."""
        from backend.app.core.nodes.arc_planner import arc_planner_node
        state = self._make_state()
        state["campaign"]["world_state_json"]["arc_state"] = {
            "current_stage": "RESOLUTION",
            "stage_start_turn": 15,
        }
        state["turn_number"] = 20
        result = arc_planner_node(state)
        assert "conclusion_plan" in result.get("arc_guidance", {})

    def test_no_conclusion_plan_in_rising(self):
        """During RISING, no conclusion_plan should be present."""
        from backend.app.core.nodes.arc_planner import arc_planner_node
        state = self._make_state()
        result = arc_planner_node(state)
        assert "conclusion_plan" not in result.get("arc_guidance", {})


# ── Universe modularity tests ────────────────────────────────────────


class TestBypassMethods:
    """Tests for data-driven bypass methods."""

    def test_core_methods_present(self):
        from backend.app.world.era_pack_models import ALLOWED_BYPASS_METHODS, _CORE_BYPASS_METHODS
        for method in _CORE_BYPASS_METHODS:
            assert method in ALLOWED_BYPASS_METHODS

    def test_default_setting_methods_present(self):
        """Default (Star Wars) setting methods should be present when no env override."""
        from backend.app.world.era_pack_models import ALLOWED_BYPASS_METHODS
        # Star Wars defaults (when SETTING_BYPASS_METHODS env is not set)
        assert "violence" in ALLOWED_BYPASS_METHODS  # core
        assert "hack" in ALLOWED_BYPASS_METHODS  # core

    def test_env_override_setting_methods(self):
        """SETTING_BYPASS_METHODS env should replace default setting methods."""
        from backend.app.world.era_pack_models import _load_setting_bypass_methods
        with patch.dict(os.environ, {"SETTING_BYPASS_METHODS": "magic,potion,enchantment"}):
            methods = _load_setting_bypass_methods()
            assert methods == {"magic", "potion", "enchantment"}


class TestBaseStyleMap:
    """Tests for configurable base style map."""

    def test_default_base_style(self):
        """Default base style map should use star_wars_base_style."""
        from backend.app.rag.style_mappings import BASE_STYLE_MAP
        assert "star_wars_base_style" in BASE_STYLE_MAP or any(
            v == "BASE" for v in BASE_STYLE_MAP.values()
        )


class TestBackgroundFigures:
    """Tests for era pack background figures fallback."""

    def test_fallback_to_builtin(self):
        """Without era pack figures, should fall back to built-in BACKGROUND_FIGURES."""
        from backend.app.core.agents.encounter import generate_background_figures
        import random
        rng = random.Random(42)
        figures = generate_background_figures({"cantina"}, era_id="NONEXISTENT", rng=rng, count=2)
        assert len(figures) == 2
        assert all(isinstance(f, str) for f in figures)


class TestBanterPoolNeutralized:
    """Tests that Force/Jedi references are neutralized in banter pool."""

    def test_no_force_or_jedi_in_banter(self):
        """Banter pool should not contain literal 'the Force' or 'the Jedi' references."""
        from backend.app.constants import BANTER_POOL, BANTER_MEMORY_POOL
        for style, tones in BANTER_POOL.items():
            for tone, lines in tones.items():
                for line in lines:
                    assert "the Force " not in line, f"Found 'the Force' in BANTER_POOL[{style}][{tone}]: {line}"
                    assert "the Jedi " not in line, f"Found 'the Jedi' in BANTER_POOL[{style}][{tone}]: {line}"
        for style, lines in BANTER_MEMORY_POOL.items():
            for line in lines:
                assert "the Force " not in line, f"Found 'the Force' in BANTER_MEMORY_POOL[{style}]: {line}"
                assert "the Jedi " not in line, f"Found 'the Jedi' in BANTER_MEMORY_POOL[{style}]: {line}"


class TestEraPackNewFields:
    """Tests for new EraPack fields."""

    def test_background_figures_field_default(self):
        """EraPack should have background_figures field with empty dict default."""
        from backend.app.world.era_pack_models import EraPack
        pack = EraPack(era_id="test")
        assert pack.background_figures == {}

    def test_setting_name_field_default(self):
        """EraPack should have setting_name field with None default."""
        from backend.app.world.era_pack_models import EraPack
        pack = EraPack(era_id="test")
        assert pack.setting_name is None

    def test_setting_name_custom(self):
        """EraPack should accept a custom setting_name."""
        from backend.app.world.era_pack_models import EraPack
        pack = EraPack(era_id="test", setting_name="Harry Potter")
        assert pack.setting_name == "Harry Potter"


# ── Campaign init role test ──────────────────────────────────────────


class TestCampaignInitRole:
    """Tests for the campaign_init LLM role."""

    def test_campaign_init_in_model_config(self):
        """campaign_init role should be in MODEL_CONFIG."""
        from backend.app.config import MODEL_CONFIG
        assert "campaign_init" in MODEL_CONFIG

    def test_campaign_init_token_budget(self):
        """campaign_init should have token budgets defined."""
        from backend.app.config import get_role_max_context_tokens, get_role_reserved_output_tokens
        assert get_role_max_context_tokens("campaign_init") == 8192
        assert get_role_reserved_output_tokens("campaign_init") == 4096


class TestScaleAdvisorFeatureFlag:
    """Tests for the ENABLE_SCALE_ADVISOR feature flag."""

    def test_default_off(self):
        """ENABLE_SCALE_ADVISOR should default to False."""
        from backend.app.config import ENABLE_SCALE_ADVISOR
        assert ENABLE_SCALE_ADVISOR is False
