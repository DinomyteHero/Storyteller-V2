"""Tests for V8.0 Gate 3: Player Agency improvements.

Tests cover:
- Structured intent passthrough (router trusts frontend metadata)
- Consequence surfacing (wave/tsunami in narrator prompt) [already tested in Gate 2]
- Companion loyalty stakes wiring
- Choice prompt consistency fix ("exactly 4" → "3-6")
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


# ---------------------------------------------------------------------------
# 3.1: Structured Intent Passthrough
# ---------------------------------------------------------------------------


class TestStructuredIntentPassthrough:
    """Router trusts structured_intent and skips LLM classification."""

    def test_structured_talk_skips_llm(self):
        """TALK action_type with SAFE risk → TALK intent, no LLM call."""
        from backend.app.core.router import route

        result = route(
            "I ask about the rumors",
            structured_intent={"action_type": "TALK", "risk_level": "SAFE", "meaning_tag": "seek_history"},
        )
        assert result.route == "TALK"
        assert result.action_class == "DIALOGUE_ONLY"
        assert result.confidence == 1.0
        assert "structured" in result.rationale_short

    def test_structured_do_goes_to_mechanic(self):
        """DO action_type → always goes to MECHANIC regardless of risk."""
        from backend.app.core.router import route

        result = route(
            "I pick the lock",
            structured_intent={"action_type": "DO", "risk_level": "RISKY"},
        )
        assert result.route == "MECHANIC"
        assert result.requires_resolution is True

    def test_structured_investigate_goes_to_mechanic(self):
        """INVESTIGATE → MECHANIC (physical action)."""
        from backend.app.core.router import route

        result = route(
            "I search the room carefully",
            structured_intent={"action_type": "INVESTIGATE"},
        )
        assert result.route == "MECHANIC"
        assert result.action_class == "PHYSICAL_ACTION"

    def test_structured_risky_talk_goes_to_mechanic(self):
        """TALK with RISKY risk → MECHANIC (needs resolution)."""
        from backend.app.core.router import route

        result = route(
            "I try to convince the guard",
            structured_intent={"action_type": "TALK", "risk_level": "RISKY"},
        )
        assert result.route == "MECHANIC"
        assert result.requires_resolution is True

    def test_free_text_still_uses_classification(self):
        """Without structured_intent, router uses heuristic/LLM classification."""
        from backend.app.core.router import route

        # This should go through the heuristic path (no structured_intent)
        result = route("I stab the guard")
        assert result.route == "MECHANIC"
        assert "guardrail" in result.rationale_short or "heuristic" in result.rationale_short or "LLM" in result.rationale_short


# ---------------------------------------------------------------------------
# 3.1b: Router Node Integration
# ---------------------------------------------------------------------------


class TestRouterNodeIntegration:
    """Router node correctly maps structured_intent to pipeline intent."""

    def test_router_node_talk_intent(self):
        from backend.app.core.nodes.router import router_node

        state = {
            "user_input": "Tell me about the base",
            "structured_intent": {"action_type": "TALK", "risk_level": "SAFE"},
        }
        result = router_node(state)
        assert result["intent"] == "TALK"

    def test_router_node_action_intent(self):
        from backend.app.core.nodes.router import router_node

        state = {
            "user_input": "I draw my blaster",
            "structured_intent": {"action_type": "DO", "risk_level": "RISKY"},
        }
        result = router_node(state)
        assert result["intent"] == "ACTION"

    def test_router_node_meaning_tag_mechanic(self):
        """Meaning tags like make_demand force mechanic even for TALK."""
        from backend.app.core.nodes.router import router_node

        state = {
            "user_input": "Give me the credits or else",
            "structured_intent": {
                "action_type": "TALK",
                "risk_level": "SAFE",
                "meaning_tag": "make_demand",
            },
        }
        result = router_node(state)
        assert result["intent"] == "ACTION"


# ---------------------------------------------------------------------------
# 3.3: Companion Loyalty Stakes Wiring
# ---------------------------------------------------------------------------


class TestCompanionLoyaltyStakes:
    """Companion loyalty crisis wired into ChoiceCrafter and Narrator."""

    def test_choice_crafter_companion_hint_includes_crisis(self):
        """When companion_threatens_leave is set, companion_hint includes LOYALTY CRISIS."""
        from backend.app.core.nodes.choice_crafter_node import _build_companion_hint
        from backend.app.models.state import GameState

        gs = GameState(
            campaign_id="test",
            player_id="p1",
            campaign={
                "party": ["kira"],
                "world_state_json": {"party_state": {"companion_states": {}}},
            },
        )
        state = {"companion_threatens_leave": ["Kira"]}
        hint = _build_companion_hint(gs, state=state)
        assert "LOYALTY CRISIS" in hint
        assert "Kira" in hint

    def test_no_crisis_without_flag(self):
        """Without companion_threatens_leave, no LOYALTY CRISIS in hint."""
        from backend.app.core.nodes.choice_crafter_node import _build_companion_hint
        from backend.app.models.state import GameState

        gs = GameState(
            campaign_id="test",
            player_id="p1",
            campaign={"party": [], "world_state_json": {}},
        )
        hint = _build_companion_hint(gs, state={})
        assert "LOYALTY CRISIS" not in hint


# ---------------------------------------------------------------------------
# 3.4: Choice Prompt Consistency Fix
# ---------------------------------------------------------------------------


class TestChoicePromptConsistency:
    """Verify stale "exactly 4" text has been updated to "3-6"."""

    def test_choice_crafter_agent_says_3_6(self):
        """ChoiceCrafterAgent source should say 3-6, not exactly 4."""
        import backend.app.core.agents.choice_crafter_agent as cca

        source = open(cca.__file__).read()
        assert "3-6" in source
        assert "exactly 4" not in source

    def test_suggestion_refiner_correction_says_3_6(self):
        """SuggestionRefiner correction prompt should say 3-6, not exactly 4."""
        import importlib
        from backend.app.core.nodes import suggestion_refiner

        importlib.reload(suggestion_refiner)
        source = open(suggestion_refiner.__file__).read()
        assert "exactly 4" not in source
        assert "3-6 objects" in source

    def test_choice_crafter_node_docstring(self):
        """ChoiceCrafterNode module docstring should say 3-6."""
        from backend.app.core.nodes import choice_crafter_node

        assert "3-6" in choice_crafter_node.__doc__
        assert "generate 4" not in choice_crafter_node.__doc__


# ---------------------------------------------------------------------------
# 3.1c: Structured intent saves LLM call (latency optimization)
# ---------------------------------------------------------------------------


class TestStructuredIntentPerformance:
    """Structured intent should avoid LLM classification entirely."""

    def test_structured_intent_confidence_1(self):
        """Structured intent always returns confidence 1.0 (no LLM uncertainty)."""
        from backend.app.core.router import route

        for action_type in ["TALK", "DO", "INVESTIGATE", "TRAVEL", "USE_ABILITY"]:
            result = route(
                "test input",
                structured_intent={"action_type": action_type, "risk_level": "SAFE"},
            )
            assert result.confidence == 1.0, f"Failed for action_type={action_type}"
