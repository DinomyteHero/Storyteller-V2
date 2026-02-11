"""Tests for bracket-tagged suggestion intents flowing into mechanic resolution."""

from backend.app.core.agents.mechanic import _classify_action, _extract_choice_tags, resolve
from backend.app.models.state import CharacterSheet, GameState


def _base_state(user_input: str) -> GameState:
    return GameState(
        campaign_id="c1",
        player_id="p1",
        user_input=user_input,
        intent="ACTION",
        player=CharacterSheet(character_id="p1", name="PC", stats={"Charisma": 8, "Combat": 6}),
        campaign={"world_state_json": {"arc_state": {"current_stage": "SETUP"}}},
        current_location="cantina",
        present_npcs=[{"id": "npc1", "name": "Broker", "relationship_score": 0}],
        debug_seed=7,
    )


def test_extract_choice_tags_strips_prefix_tokens():
    tags, cleaned = _extract_choice_tags("[PERSUADE] [PARAGON] Let's do this peacefully")
    assert tags == ["PERSUADE", "PARAGON"]
    assert cleaned == "Let's do this peacefully"


def test_classify_action_prefers_choice_tag_over_keyword_heuristics():
    # Contains attack-y wording, but tag should force PERSUADE.
    action = _classify_action("[PERSUADE] I draw my blaster and threaten him", "ACTION")
    assert action == "PERSUADE"


def test_paragon_tag_applies_alignment_bias_and_tone():
    result = resolve(_base_state("[PARAGON] [PERSUADE] We can solve this without violence"))
    assert result.tone_tag == "PARAGON"
    assert (result.alignment_delta or {}).get("paragon_renegade", 0) >= 2
    assert any("Choice path tags" in fact for fact in (result.narrative_facts or []))


def test_renegade_tag_applies_alignment_bias_and_attack_override():
    result = resolve(_base_state("[RENEGADE] [COMBAT] Talk is over."))
    assert result.action_type == "ATTACK"
    assert result.tone_tag == "RENEGADE"
    assert (result.alignment_delta or {}).get("paragon_renegade", 0) <= -2
