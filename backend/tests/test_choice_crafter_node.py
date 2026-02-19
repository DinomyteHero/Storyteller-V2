from __future__ import annotations

from unittest.mock import patch

from backend.app.core.nodes.choice_crafter_node import _make_fallback_choices, make_choice_crafter_node


def test_make_fallback_choices_returns_four_tones() -> None:
    items = _make_fallback_choices(
        final_text="The corridor hums with unstable power.",
        loc="loc-command-center",
        immediate_situation="an unstable generator is about to overload",
    )
    assert len(items) == 4
    tones = {item.get("tone") for item in items}
    assert tones == {"PARAGON", "INVESTIGATE", "RENEGADE", "NEUTRAL"}
    tiers = [item.get("impact_tier") for item in items]
    assert tiers.count("wave") == 1
    assert tiers.count("ripple") == 3


@patch("backend.app.core.nodes.choice_crafter_node.generate_choices", side_effect=RuntimeError("llm down"))
def test_choice_crafter_node_llm_failure_uses_four_choice_fallback(_mock_generate) -> None:
    node = make_choice_crafter_node()
    state = {
        "campaign_id": "camp-test",
        "player_id": "player-test",
        "turn_number": 3,
        "current_location": "loc-marketplace",
        "final_text": "The market goes quiet as everyone looks toward the gates.",
        "scene_frame": {
            "immediate_situation": "guards are closing in from both sides",
            "topic_primary": "Escalation",
            "subtext": "You have one move",
            "npc_agenda": "Contain the disturbance",
        },
    }

    result = node(state)

    actions = result.get("suggested_actions") or []
    assert len(actions) == 4
    tone_tags = {a.get("tone_tag") for a in actions}
    assert tone_tags == {"PARAGON", "INVESTIGATE", "RENEGADE", "NEUTRAL"}
    impact_tiers = {a.get("impact_tier") for a in actions}
    assert impact_tiers == {"ripple", "wave"}

    warnings = result.get("warnings") or []
    assert any("ChoiceCrafter: LLM failed; showing degraded options." in w for w in warnings)


@patch("backend.app.core.nodes.choice_crafter_node.generate_choices")
def test_choice_crafter_uses_precomputed_context(mock_generate_choices) -> None:
    mock_generate_choices.return_value = [
        {"text": "Stand firm and take control.", "tone": "PARAGON", "meaning": "pragmatic", "risk": "RISKY", "impact_tier": "ripple", "consequence_hint": "You seize momentum."},
        {"text": "Ask what happened at this checkpoint.", "tone": "INVESTIGATE", "meaning": "seek_history", "risk": "SAFE", "impact_tier": "ripple", "consequence_hint": "You learn details."},
        {"text": "Threaten the guard captain into compliance.", "tone": "RENEGADE", "meaning": "make_demand", "risk": "DANGEROUS", "impact_tier": "wave", "consequence_hint": "The room turns hostile."},
        {"text": "Step back and watch for a new angle.", "tone": "NEUTRAL", "meaning": "deflect", "risk": "SAFE", "impact_tier": "ripple", "consequence_hint": "You avoid immediate escalation."},
    ]
    node = make_choice_crafter_node()
    state = {
        "campaign_id": "camp-test",
        "player_id": "player-test",
        "turn_number": 4,
        "current_location": "loc-marketplace",
        "final_text": "Crowds part around the checkpoint while guards close ranks.",
        "scene_frame": {"immediate_situation": "checkpoint standoff"},
        "choice_crafter_pre_context": {
            "location": "loc-checkpoint",
            "npc_descriptions": ["Captain Varo (officer)"],
            "topic_primary": "authority",
            "subtext": "control is slipping",
            "npc_agenda": "force compliance",
            "arc_stage": "RISING",
            "tension_level": "HIGH",
            "director_intent": "Escalate pressure and force a decision.",
            "gm_context": "== GM CONTEXT (this turn) ==\nSituation: tense checkpoint standoff",
        },
    }

    node(state)

    assert mock_generate_choices.called
    kwargs = mock_generate_choices.call_args.kwargs
    assert kwargs["location"] == "loc-checkpoint"
    assert kwargs["npc_descriptions"] == ["Captain Varo (officer)"]
    assert kwargs["topic_primary"] == "authority"
    assert kwargs["subtext"] == "control is slipping"
    assert kwargs["npc_agenda"] == "force compliance"
    assert kwargs["arc_stage"] == "RISING"


@patch("backend.app.core.nodes.choice_crafter_node.generate_choices")
def test_choice_crafter_preserves_impact_tier_on_actions(mock_generate_choices) -> None:
    mock_generate_choices.return_value = [
        {"text": "Rally allies and lock down the district.", "tone": "PARAGON", "meaning": "offer_alliance", "risk": "RISKY", "impact_tier": "wave", "consequence_hint": "Factions react quickly."},
        {"text": "Survey records before making a move.", "tone": "INVESTIGATE", "meaning": "seek_history", "risk": "SAFE", "impact_tier": "ripple", "consequence_hint": "You uncover context."},
        {"text": "Trigger a sabotage chain across all depots.", "tone": "RENEGADE", "meaning": "make_demand", "risk": "DANGEROUS", "impact_tier": "tsunami", "consequence_hint": "Power structures shift."},
        {"text": "Hold position and collect reactions.", "tone": "NEUTRAL", "meaning": "deflect", "risk": "SAFE", "impact_tier": "ripple", "consequence_hint": "You retain flexibility."},
    ]
    node = make_choice_crafter_node()
    state = {
        "campaign_id": "camp-test",
        "player_id": "player-test",
        "turn_number": 7,
        "current_location": "loc-district",
        "final_text": "The district is unstable and several factions wait for your signal.",
    }
    result = node(state)
    actions = result.get("suggested_actions") or []
    assert len(actions) == 4
    assert [a.get("impact_tier") for a in actions] == ["wave", "ripple", "tsunami", "ripple"]
