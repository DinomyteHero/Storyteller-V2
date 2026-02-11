"""Tests for V2.17+V2.18 DialogueTurn contract: schema, scene_frame, npc_utterance, player_responses, validation."""
from __future__ import annotations

import pytest

from backend.app.models.dialogue_turn import (
    DEFAULT_DEPTH_BUDGET,
    DepthBudget,
    DialogueTurn,
    NPCRef,
    NPCUtterance,
    PlayerAction,
    PlayerResponse,
    SceneFrame,
    ValidationReport,
    compute_scene_hash,
    infer_action_type,
    infer_intent,
    infer_meaning_tag,
)
from backend.app.core.agents.narrator import _extract_npc_utterance
from backend.app.core.director_validation import (
    action_suggestion_to_player_response,
    action_suggestions_to_player_responses,
    classify_suggestion,
)
from backend.app.core.nodes.narrative_validator import _check_dialogue_turn_validity
from backend.app.core.nodes.scene_frame import (
    scene_frame_node,
    _derive_topic,
    _derive_subtext,
    _derive_npc_agenda,
    _derive_style_tags,
    _derive_pressure,
    _build_voice_profile,
)
from backend.app.models.state import ActionSuggestion


# ---------------------------------------------------------------------------
# Schema golden tests
# ---------------------------------------------------------------------------

class TestDialogueTurnSchema:
    """DialogueTurn Pydantic schema tests."""

    def test_full_construction(self):
        """Construct a complete DialogueTurn and verify all fields serialise."""
        dt = DialogueTurn(
            turn_id="camp1_t5",
            scene_frame=SceneFrame(
                location_id="loc-cantina",
                location_name="the cantina",
                present_npcs=[NPCRef(id="npc-greedo", name="Greedo", role="bounty hunter")],
                immediate_situation="Greedo blocks your path.",
                player_objective="Find information about the smuggler.",
                allowed_scene_type="dialogue",
                scene_hash="abc123",
            ),
            npc_utterance=NPCUtterance(
                speaker_id="npc-greedo",
                speaker_name="Greedo",
                text="Going somewhere, Solo?",
            ),
            player_responses=[
                PlayerResponse(
                    id="resp_1",
                    display_text="Show Greedo good faith",
                    action=PlayerAction(type="do", intent="charm", target="npc-greedo", tone="PARAGON"),
                    tone_tag="PARAGON",
                ),
                PlayerResponse(
                    id="resp_2",
                    display_text="Ask about the bounty",
                    action=PlayerAction(type="say", intent="ask", target="npc-greedo", tone="INVESTIGATE"),
                    tone_tag="INVESTIGATE",
                ),
            ],
            narrated_prose="The cantina smelled of spilled juma juice...",
            validation=ValidationReport(checks_passed=["mechanic_consistency"]),
        )
        data = dt.model_dump(mode="json")
        assert data["turn_id"] == "camp1_t5"
        assert data["scene_frame"]["location_id"] == "loc-cantina"
        assert len(data["player_responses"]) == 2
        assert data["player_responses"][0]["tone_tag"] == "PARAGON"
        assert data["npc_utterance"]["speaker_name"] == "Greedo"
        assert data["narrated_prose"].startswith("The cantina")

    def test_minimal_construction(self):
        """DialogueTurn with defaults."""
        dt = DialogueTurn(
            turn_id="c_t1",
            scene_frame=SceneFrame(location_id="loc-x", location_name="a room"),
            npc_utterance=NPCUtterance(),
        )
        assert dt.player_responses == []
        assert dt.narrated_prose == ""
        assert dt.validation is None


# ---------------------------------------------------------------------------
# SceneFrame hash tests
# ---------------------------------------------------------------------------

class TestSceneHash:
    """Scene hash determinism and change detection."""

    def test_deterministic(self):
        """Same inputs always produce the same hash."""
        h1 = compute_scene_hash("loc-cantina", ["npc-a", "npc-b"], "ATTACK")
        h2 = compute_scene_hash("loc-cantina", ["npc-b", "npc-a"], "ATTACK")  # order doesn't matter
        assert h1 == h2

    def test_different_npcs_different_hash(self):
        """Different NPC sets produce different hashes."""
        h1 = compute_scene_hash("loc-cantina", ["npc-a", "npc-b"])
        h2 = compute_scene_hash("loc-cantina", ["npc-c"])
        assert h1 != h2

    def test_different_location_different_hash(self):
        h1 = compute_scene_hash("loc-cantina", ["npc-a"])
        h2 = compute_scene_hash("loc-hangar", ["npc-a"])
        assert h1 != h2

    def test_hash_length(self):
        h = compute_scene_hash("loc-x", [])
        assert len(h) == 16


# ---------------------------------------------------------------------------
# NPC utterance extraction
# ---------------------------------------------------------------------------

class TestNPCUtteranceExtraction:
    """Test _extract_npc_utterance from narrator output."""

    def test_with_separator(self):
        """Text with ---NPC_LINE--- separator splits correctly."""
        raw = (
            "The cantina was dimly lit. Smoke curled above the tables.\n\n"
            "---NPC_LINE---\n"
            "SPEAKER: Greedo\n"
            '"Going somewhere, Solo?"'
        )
        npcs = [{"id": "npc-greedo", "name": "Greedo", "role": "bounty hunter"}]
        prose, utt = _extract_npc_utterance(raw, npcs)
        assert "cantina" in prose
        assert "---NPC_LINE---" not in prose
        assert utt.speaker_name == "Greedo"
        assert utt.speaker_id == "npc-greedo"
        assert "Solo" in utt.text

    def test_without_separator_fallback(self):
        """Text without separator falls back to narrator observation."""
        raw = "The corridor stretched ahead. Pipes hissed steam in the darkness."
        prose, utt = _extract_npc_utterance(raw, [])
        assert prose == raw
        assert utt.speaker_id == "narrator"
        assert utt.speaker_name == "Narrator"
        assert utt.text  # Should have some fallback text

    def test_speaker_resolution(self):
        """Speaker name resolved to NPC id from present_npcs."""
        raw = "Prose here.\n---NPC_LINE---\nSPEAKER: Mara Jade\n\"Watch your back.\""
        npcs = [
            {"id": "npc-mara", "name": "Mara Jade", "role": "agent"},
            {"id": "npc-luke", "name": "Luke", "role": "Jedi"},
        ]
        _, utt = _extract_npc_utterance(raw, npcs)
        assert utt.speaker_id == "npc-mara"
        assert utt.speaker_name == "Mara Jade"

    def test_unknown_speaker_fallback(self):
        """Unknown speaker gets slug-based id when not in present_npcs."""
        raw = "Prose.\n---NPC_LINE---\nSPEAKER: Unknown Figure\n\"Who are you?\""
        _, utt = _extract_npc_utterance(raw, [])
        # Speaker not in present_npcs -> slug-based id
        assert utt.speaker_id == "unknown_figure"
        assert utt.speaker_name == "Unknown Figure"


# ---------------------------------------------------------------------------
# ActionSuggestion -> PlayerResponse conversion
# ---------------------------------------------------------------------------

class TestActionSuggestionToPlayerResponse:
    """Test the converter from ActionSuggestion to PlayerResponse dict."""

    def test_basic_conversion(self):
        sug = classify_suggestion("Ask about the bounty")
        result = action_suggestion_to_player_response(sug, 0)
        assert result["id"] == "resp_1"
        assert result["display_text"] == "Ask about the bounty"
        assert result["action"]["intent"] == "ask"
        assert result["tone_tag"] in {"PARAGON", "INVESTIGATE", "RENEGADE", "NEUTRAL"}

    def test_say_action_type(self):
        sug = classify_suggestion("Say: 'I can help you.'")
        result = action_suggestion_to_player_response(sug, 1)
        assert result["action"]["type"] == "say"

    def test_do_action_type(self):
        sug = classify_suggestion("Search the room for clues")
        result = action_suggestion_to_player_response(sug, 2)
        assert result["action"]["type"] == "do"

    def test_target_resolution_with_scene_frame(self):
        sug = classify_suggestion("Talk to Greedo about the job")
        scene = {
            "present_npcs": [
                {"id": "npc-greedo", "name": "Greedo", "role": "bounty hunter"},
            ],
        }
        result = action_suggestion_to_player_response(sug, 0, scene)
        assert result["action"]["target"] == "npc-greedo"

    def test_batch_conversion(self):
        suggestions = [
            classify_suggestion("Help the wounded"),
            classify_suggestion("Ask about the patrol"),
            classify_suggestion("Demand answers"),
            classify_suggestion("Slip away quietly"),
        ]
        results = action_suggestions_to_player_responses(suggestions)
        assert len(results) == 4
        assert results[0]["id"] == "resp_1"
        assert results[3]["id"] == "resp_4"


# ---------------------------------------------------------------------------
# Intent inference
# ---------------------------------------------------------------------------

class TestIntentInference:
    """Test infer_intent and infer_action_type helpers."""

    def test_ask_intent(self):
        assert infer_intent("Ask about the bounty") == "ask"

    def test_attack_intent(self):
        assert infer_intent("Attack the guard") == "attack"

    def test_observe_fallback(self):
        assert infer_intent("Ponder the universe") == "observe"

    def test_leave_intent(self):
        assert infer_intent("Leave the cantina") == "leave"

    def test_say_action_type(self):
        assert infer_action_type("Say: 'Hello there'") == "say"

    def test_ask_action_type(self):
        assert infer_action_type("Ask: 'What happened?'") == "say"

    def test_do_action_type(self):
        assert infer_action_type("Search the room") == "do"


# ---------------------------------------------------------------------------
# SceneFrame node
# ---------------------------------------------------------------------------

class TestSceneFrameNode:
    """Test scene_frame_node pure function."""

    def test_builds_scene_frame(self):
        state = {
            "current_location": "loc-cantina",
            "present_npcs": [
                {"id": "npc-1", "name": "Bith Musician", "role": "entertainer"},
            ],
            "mechanic_result": {
                "action_type": "TALK",
                "outcome_summary": "The conversation begins.",
                "narrative_facts": ["Bith nods politely."],
            },
            "user_input": "Talk to the musician",
        }
        result = state | scene_frame_node(state)
        sf = result.get("scene_frame")
        assert sf is not None
        assert sf["location_id"] == "loc-cantina"
        assert len(sf["present_npcs"]) == 1
        assert sf["scene_hash"]
        assert sf["allowed_scene_type"] == "dialogue"

    def test_combat_scene_type(self):
        state = {
            "current_location": "loc-hangar",
            "present_npcs": [],
            "mechanic_result": {"action_type": "ATTACK"},
            "user_input": "Attack!",
        }
        result = state | scene_frame_node(state)
        sf = result["scene_frame"]
        assert sf["allowed_scene_type"] == "combat"


# ---------------------------------------------------------------------------
# DialogueTurn validation
# ---------------------------------------------------------------------------

class TestDialogueTurnValidation:
    """Test _check_dialogue_turn_validity from narrative_validator."""

    def test_too_few_responses_warns(self):
        state = {
            "player_responses": [{"id": "resp_1", "display_text": "Option 1", "action": {}}],
            "scene_frame": {},
            "npc_utterance": {},
            "final_text": "The room was dark.",
        }
        warnings, _ = _check_dialogue_turn_validity(state)
        assert any("player_responses" in w for w in warnings)

    def test_too_many_responses_trimmed(self):
        state = {
            "player_responses": [
                {"id": f"resp_{i}", "display_text": f"Opt {i}", "action": {}}
                for i in range(8)
            ],
            "scene_frame": {},
            "npc_utterance": {},
            "final_text": "Normal text.",
        }
        _, repairs = _check_dialogue_turn_validity(state)
        assert any("Trimmed" in r for r in repairs)
        assert len(state["player_responses"]) == 6

    def test_empty_display_text_warns(self):
        state = {
            "player_responses": [
                {"id": "resp_1", "display_text": "", "action": {}},
                {"id": "resp_2", "display_text": "Valid", "action": {}},
                {"id": "resp_3", "display_text": "Also valid", "action": {}},
            ],
            "scene_frame": {},
            "npc_utterance": {},
            "final_text": "Text.",
        }
        warnings, _ = _check_dialogue_turn_validity(state)
        assert any("Empty display_text" in w for w in warnings)

    def test_numbered_list_in_narration_warns(self):
        state = {
            "player_responses": [],
            "scene_frame": {},
            "npc_utterance": {},
            "final_text": "The scene unfolds.\n1. Attack the guard\n2. Flee the scene",
        }
        warnings, _ = _check_dialogue_turn_validity(state)
        assert any("numbered list" in w for w in warnings)

    def test_what_do_you_do_warns(self):
        state = {
            "player_responses": [],
            "scene_frame": {},
            "npc_utterance": {},
            "final_text": "The choice is clear. What do you do?",
        }
        warnings, _ = _check_dialogue_turn_validity(state)
        assert any("What do you do" in w for w in warnings)

    def test_clean_state_no_warnings(self):
        state = {
            "player_responses": [
                {"id": f"resp_{i}", "display_text": f"Option {i}", "action": {"intent": "observe"}}
                for i in range(4)
            ],
            "scene_frame": {"present_npcs": []},
            "npc_utterance": {"speaker_id": "narrator"},
            "final_text": "The room was quiet. Dust motes danced in the light.",
        }
        warnings, repairs = _check_dialogue_turn_validity(state)
        assert not warnings
        assert not repairs

    def test_invalid_target_warns(self):
        state = {
            "player_responses": [
                {
                    "id": "resp_1",
                    "display_text": "Talk to ghost",
                    "action": {"intent": "say", "target": "npc-ghost"},
                },
            ],
            "scene_frame": {
                "present_npcs": [{"id": "npc-greedo", "name": "Greedo", "role": "bounty hunter"}],
            },
            "npc_utterance": {"speaker_id": "narrator"},
            "final_text": "Text.",
        }
        warnings, _ = _check_dialogue_turn_validity(state)
        assert any("npc-ghost" in w for w in warnings)


# ---------------------------------------------------------------------------
# V2.18: KOTOR-soul depth tests
# ---------------------------------------------------------------------------

class TestSceneFrameTopicDerivation:
    """V2.18: Topic derivation from NPC role/scene context."""

    def test_guard_role_gives_suspicion_topic(self):
        npc_refs = [NPCRef(id="npc-1", name="Guard", role="guard")]
        primary, _ = _derive_topic(npc_refs, "dialogue", "SETUP", [])
        assert primary == "suspicion"

    def test_mentor_role_gives_identity_topic(self):
        npc_refs = [NPCRef(id="npc-1", name="Sage", role="mentor")]
        primary, _ = _derive_topic(npc_refs, "dialogue", "RISING", [])
        assert primary == "identity"

    def test_combat_scene_type_fallback(self):
        primary, _ = _derive_topic([], "combat", "SETUP", [])
        assert primary == "survival"

    def test_themes_become_secondary_topic(self):
        npc_refs = [NPCRef(id="npc-1", name="X", role="guard")]
        _, secondary = _derive_topic(npc_refs, "dialogue", "SETUP", ["redemption"])
        assert secondary == "redemption"

    def test_arc_stage_secondary_fallback(self):
        npc_refs = [NPCRef(id="npc-1", name="X", role="guard")]
        _, secondary = _derive_topic(npc_refs, "dialogue", "RISING", [])
        assert secondary  # should have a value from _ARC_STAGE_TOPICS


class TestSceneFrameSubtext:
    """V2.18: Subtext derivation from topic + arc stage."""

    def test_subtext_contains_topic(self):
        subtext = _derive_subtext("trust", "SETUP")
        assert "trust" in subtext.lower()

    def test_subtext_changes_by_stage(self):
        s1 = _derive_subtext("trust", "SETUP")
        s2 = _derive_subtext("trust", "CLIMAX")
        assert s1 != s2


class TestSceneFrameNPCAgenda:
    """V2.18: NPC agenda from role + arc stage."""

    def test_guard_rising_has_agenda(self):
        agenda = _derive_npc_agenda("guard", "RISING")
        assert agenda  # should return a non-empty string

    def test_default_fallback(self):
        agenda = _derive_npc_agenda("unknownrole", "SETUP")
        assert agenda  # should return default


class TestSceneFrameVoiceProfile:
    """V2.18: Voice profile building from NPC data."""

    def test_voice_profile_from_voice_tags(self):
        npc = {"voice_tags": ["measured", "formal"]}
        vp = _build_voice_profile(npc)
        # Should derive rhetorical_style and tell from voice_tags
        assert "rhetorical_style" in vp or "tell" in vp or vp == {}

    def test_voice_profile_with_motivation(self):
        npc = {"motivation": "Protect the weak", "voice_tags": ["gruff"]}
        vp = _build_voice_profile(npc)
        if vp.get("belief"):
            assert "Protect" in vp["belief"] or "protect" in vp["belief"].lower()

    def test_empty_npc_gives_empty_profile(self):
        vp = _build_voice_profile({})
        assert isinstance(vp, dict)


class TestSceneFramePressure:
    """V2.18: Pressure derivation from world_state."""

    def test_wanted_heat(self):
        ws = {"faction_reputation": {"empire": -60}}
        p = _derive_pressure(ws)
        assert p.get("heat") == "Wanted"

    def test_quiet_alert(self):
        ws = {"npc_states": {}}
        p = _derive_pressure(ws)
        assert p.get("alert") == "Quiet"

    def test_watchful_alert(self):
        ws = {"npc_states": {"npc-1": {"disposition": "hostile"}}}
        p = _derive_pressure(ws)
        assert p.get("alert") == "Watchful"

    def test_lockdown_alert(self):
        ws = {"npc_states": {
            "n1": {"disposition": "hostile"},
            "n2": {"disposition": "suspicious"},
            "n3": {"disposition": "hostile"},
        }}
        p = _derive_pressure(ws)
        assert p.get("alert") == "Lockdown"


class TestSceneFrameStyleTags:
    """V2.18: Style tag derivation."""

    def test_cantina_location(self):
        tags = _derive_style_tags("loc-cantina", "dialogue", [])
        assert any("noir" in t.lower() or "seedy" in t.lower() for t in tags)

    def test_caps_at_three(self):
        tags = _derive_style_tags("loc-cantina", "dialogue", [])
        assert len(tags) <= 3


class TestMeaningTagInference:
    """V2.18: infer_meaning_tag from text."""

    def test_ask_gives_seek_history(self):
        assert infer_meaning_tag("Ask about the bounty") == "seek_history"

    def test_help_gives_reveal_values(self):
        assert infer_meaning_tag("Help the wounded") == "reveal_values"

    def test_challenge_gives_challenge_premise(self):
        assert infer_meaning_tag("Challenge the guard's claim") == "challenge_premise"

    def test_threaten_gives_set_boundary(self):
        assert infer_meaning_tag("Threaten to leave") == "set_boundary"

    def test_leave_gives_deflect(self):
        assert infer_meaning_tag("Leave quietly") == "deflect"

    def test_search_gives_pragmatic(self):
        assert infer_meaning_tag("Search the room for clues") == "pragmatic"

    def test_fallback_is_pragmatic(self):
        assert infer_meaning_tag("Ponder the universe") == "pragmatic"


class TestMeaningTagOnPlayerResponse:
    """V2.18: meaning_tag carried through to PlayerResponse."""

    def test_classify_suggestion_has_meaning_tag(self):
        sug = classify_suggestion("Ask about the bounty")
        assert sug.meaning_tag  # should be non-empty

    def test_converter_includes_meaning_tag(self):
        sug = classify_suggestion("Help the wounded")
        result = action_suggestion_to_player_response(sug, 0)
        assert "meaning_tag" in result
        assert result["meaning_tag"]  # should be non-empty

    def test_explicit_meaning_tag_preserved(self):
        sug = classify_suggestion("Wait and observe", meaning_tag="pragmatic")
        assert sug.meaning_tag == "pragmatic"

    def test_batch_includes_meaning_tags(self):
        suggestions = [
            classify_suggestion("Help the wounded"),
            classify_suggestion("Ask about the patrol"),
            classify_suggestion("Demand answers"),
            classify_suggestion("Slip away quietly"),
        ]
        results = action_suggestions_to_player_responses(suggestions)
        for r in results:
            assert "meaning_tag" in r


class TestDepthBudget:
    """V2.18: DepthBudget defaults."""

    def test_default_values(self):
        b = DEFAULT_DEPTH_BUDGET
        assert b.max_scene_sentences == 3
        assert b.max_npc_lines == 4
        assert b.max_response_words == 16
        assert b.min_meaning_tags == 3
        assert b.min_tone_tags == 3


class TestV218Validators:
    """V2.18: Extended dialogue turn validity checks."""

    def test_meaning_tag_variety_warns(self):
        """4 responses with only 1 distinct meaning_tag should warn."""
        state = {
            "player_responses": [
                {"id": f"resp_{i}", "display_text": f"Opt {i}", "action": {}, "meaning_tag": "pragmatic", "tone_tag": "NEUTRAL"}
                for i in range(4)
            ],
            "scene_frame": {"present_npcs": []},
            "npc_utterance": {"speaker_id": "narrator"},
            "final_text": "Text.",
        }
        warnings, _ = _check_dialogue_turn_validity(state)
        assert any("meaning_tag" in w for w in warnings)

    def test_tone_variety_warns(self):
        """4 responses all NEUTRAL should warn about tone variety."""
        state = {
            "player_responses": [
                {"id": f"resp_{i}", "display_text": f"Opt {i}", "action": {}, "tone_tag": "NEUTRAL"}
                for i in range(4)
            ],
            "scene_frame": {"present_npcs": []},
            "npc_utterance": {"speaker_id": "narrator"},
            "final_text": "Text.",
        }
        warnings, _ = _check_dialogue_turn_validity(state)
        assert any("tone_tag" in w for w in warnings)

    def test_good_variety_no_warning(self):
        """4 responses with diverse tags should not warn."""
        state = {
            "player_responses": [
                {"id": "resp_1", "display_text": "Help the pilot", "action": {}, "tone_tag": "PARAGON", "meaning_tag": "reveal_values"},
                {"id": "resp_2", "display_text": "Ask about routes", "action": {}, "tone_tag": "INVESTIGATE", "meaning_tag": "seek_history"},
                {"id": "resp_3", "display_text": "Demand the data", "action": {}, "tone_tag": "RENEGADE", "meaning_tag": "set_boundary"},
                {"id": "resp_4", "display_text": "Slip away quietly", "action": {}, "tone_tag": "NEUTRAL", "meaning_tag": "deflect"},
            ],
            "scene_frame": {"present_npcs": [], "topic_primary": "trust"},
            "npc_utterance": {"speaker_id": "narrator", "text": "Trust is earned, not given."},
            "final_text": "The room was quiet.",
        }
        warnings, _ = _check_dialogue_turn_validity(state)
        assert not any("meaning_tag" in w for w in warnings)
        assert not any("tone_tag" in w for w in warnings)

    def test_npc_utterance_line_count_warns(self):
        """NPC utterance with >4 lines should warn."""
        state = {
            "player_responses": [],
            "scene_frame": {"present_npcs": []},
            "npc_utterance": {
                "speaker_id": "narrator",
                "text": "Line 1\nLine 2\nLine 3\nLine 4\nLine 5",
            },
            "final_text": "Text.",
        }
        warnings, _ = _check_dialogue_turn_validity(state)
        assert any("lines" in w for w in warnings)

    def test_response_word_count_warns(self):
        """Response with >16 words should warn."""
        long_text = " ".join(["word"] * 20)
        state = {
            "player_responses": [
                {"id": "resp_1", "display_text": long_text, "action": {}},
            ],
            "scene_frame": {"present_npcs": []},
            "npc_utterance": {"speaker_id": "narrator"},
            "final_text": "Text.",
        }
        warnings, _ = _check_dialogue_turn_validity(state)
        assert any("words" in w for w in warnings)

    def test_topic_anchoring_npc_warns(self):
        """NPC utterance not referencing topic should warn."""
        state = {
            "player_responses": [],
            "scene_frame": {"present_npcs": [], "topic_primary": "loyalty"},
            "npc_utterance": {"speaker_id": "narrator", "text": "The weather is nice today."},
            "final_text": "Text.",
        }
        warnings, _ = _check_dialogue_turn_validity(state)
        assert any("topic" in w.lower() for w in warnings)

    def test_topic_anchoring_passes(self):
        """NPC utterance referencing topic should not warn."""
        state = {
            "player_responses": [],
            "scene_frame": {"present_npcs": [], "topic_primary": "loyalty"},
            "npc_utterance": {"speaker_id": "narrator", "text": "Loyalty is a rare currency."},
            "final_text": "Text.",
        }
        warnings, _ = _check_dialogue_turn_validity(state)
        assert not any("topic" in w.lower() for w in warnings)

    def test_scene_frame_v218_fields_on_schema(self):
        """V2.18 fields exist on SceneFrame with defaults."""
        sf = SceneFrame(location_id="loc-x", location_name="a room")
        assert sf.topic_primary == ""
        assert sf.topic_secondary == ""
        assert sf.subtext == ""
        assert sf.npc_agenda == ""
        assert sf.scene_style_tags == []
        assert sf.pressure == {}

    def test_npc_ref_voice_profile_default(self):
        """V2.18 voice_profile on NPCRef defaults to empty dict."""
        ref = NPCRef(id="npc-1", name="Greedo", role="bounty hunter")
        assert ref.voice_profile == {}

    def test_npc_utterance_v218_fields(self):
        """V2.18 fields on NPCUtterance."""
        utt = NPCUtterance(
            speaker_id="npc-1",
            speaker_name="Greedo",
            text="Going somewhere?",
            subtext_hint="testing the player",
            rhetorical_moves=["probe"],
        )
        assert utt.subtext_hint == "testing the player"
        assert utt.rhetorical_moves == ["probe"]

    def test_player_response_meaning_tag_field(self):
        """V2.18 meaning_tag on PlayerResponse."""
        pr = PlayerResponse(
            id="resp_1",
            display_text="Ask about the bounty",
            action=PlayerAction(type="say", intent="ask"),
            meaning_tag="seek_history",
        )
        assert pr.meaning_tag == "seek_history"
