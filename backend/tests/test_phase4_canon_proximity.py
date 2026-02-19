from __future__ import annotations

from backend.app.core.nodes.encounter import apply_canon_proximity_rules
from backend.app.world.era_pack_models import CanonCharacterRule, NpcVoice


def _state(mode: str, beat: str = "", user_input: str = "") -> dict:
    return {
        "campaign": {
            "world_state_json": {
                "campaign_mode": mode,
                "current_beat": beat,
            }
        },
        "user_input": user_input,
    }


def _extended_rule(name: str = "Luke Skywalker", **overrides) -> CanonCharacterRule:
    """Build an extended canon character rule with full voice/personality data."""
    defaults = dict(
        name=name,
        proximity="extended",
        locations=["loc-rebel-base", "loc-training-ground"],
        exclusion_events=["Battle of Yavin trench run"],
        role="Jedi-in-training, Alliance pilot",
        archetype="Reluctant hero",
        voice_tags=["earnest", "hopeful", "determined"],
        traits=["brave", "idealistic", "loyal"],
        motivation="Become a Jedi; fight for the Rebellion",
        faction_id="alliance",
        knowledge_boundary="0-4 ABY (Rebellion era)",
        knowledge_exclusions=["Does NOT know Vader is his father"],
        scene_hooks=["Training", "Tactical briefings"],
        off_limits=["Cannot be killed", "Cannot turn to the dark side"],
        character_voice_id="luke-skywalker",
        voice=NpcVoice(
            belief="There is good in everyone.",
            wound="Orphaned on a moisture farm.",
            rhetorical_style="Earnest and direct.",
            tell="Gazes at the horizon.",
            taboo="Refuses to accept anyone is beyond redemption.",
        ),
    )
    defaults.update(overrides)
    return CanonCharacterRule(**defaults)


def test_canon_proximity_noop_in_sandbox() -> None:
    present, bg, warnings = apply_canon_proximity_rules(
        state=_state("sandbox"),
        effective_loc="loc-cantina",
        present_npcs=[{"id": "npc-1", "name": "Luke Skywalker"}],
        background_figures=[],
        canon_rules=[
            CanonCharacterRule(
                name="Luke Skywalker",
                proximity="cameo",
                locations=["loc-cantina"],
                exclusion_events=[],
            )
        ],
    )
    assert len(present) == 1
    assert not bg
    assert not warnings


def test_canon_proximity_cameo_removes_interaction_adds_background_figure() -> None:
    present, bg, warnings = apply_canon_proximity_rules(
        state=_state("historical"),
        effective_loc="loc-cantina",
        present_npcs=[{"id": "npc-luke", "name": "Luke Skywalker"}],
        background_figures=[],
        canon_rules=[
            CanonCharacterRule(
                name="Luke Skywalker",
                proximity="cameo",
                locations=["loc-cantina"],
                exclusion_events=[],
            )
        ],
    )
    assert not any(n.get("name") == "Luke Skywalker" for n in present)
    assert any("Luke Skywalker" in line for line in bg)
    assert not warnings


def test_canon_proximity_interaction_adds_protected_npc() -> None:
    present, bg, warnings = apply_canon_proximity_rules(
        state=_state("historical"),
        effective_loc="loc-rebel-base",
        present_npcs=[],
        background_figures=[],
        canon_rules=[
            CanonCharacterRule(
                name="Princess Leia",
                proximity="interaction",
                locations=["loc-rebel-base"],
                exclusion_events=[],
            )
        ],
    )
    assert any(n.get("name") == "Princess Leia" for n in present)
    leia = next(n for n in present if n.get("name") == "Princess Leia")
    assert leia.get("canon_protected") is True
    assert leia.get("canon_proximity") == "interaction"
    assert any("cannot be altered" in w for w in warnings)
    assert not bg


def test_canon_proximity_exclusion_warns_and_redirects_flavor() -> None:
    present, bg, warnings = apply_canon_proximity_rules(
        state=_state("historical", beat="Battle of Yavin trench run"),
        effective_loc="loc-rebel-base",
        present_npcs=[{"id": "npc-luke", "name": "Luke Skywalker"}],
        background_figures=[],
        canon_rules=[
            CanonCharacterRule(
                name="Luke Skywalker",
                proximity="exclusion",
                locations=["loc-rebel-base"],
                exclusion_events=["Battle of Yavin trench run"],
            )
        ],
    )
    assert not any(n.get("name") == "Luke Skywalker" for n in present)
    assert any("redirected away" in w for w in warnings)
    assert any("pull you away" in line for line in bg)


# ---------------------------------------------------------------------------
# Extended proximity tests
# ---------------------------------------------------------------------------


def test_canon_proximity_extended_adds_full_npc() -> None:
    """Extended proximity adds a fully enriched NPC to present_npcs."""
    rule = _extended_rule()
    present, bg, warnings = apply_canon_proximity_rules(
        state=_state("historical"),
        effective_loc="loc-rebel-base",
        present_npcs=[],
        background_figures=[],
        canon_rules=[rule],
    )
    assert len(present) == 1
    luke = present[0]
    assert luke["name"] == "Luke Skywalker"
    assert luke["canon_protected"] is True
    assert luke["canon_proximity"] == "extended"
    assert luke["role"] == "Jedi-in-training, Alliance pilot"
    assert luke["archetype"] == "Reluctant hero"
    assert luke["voice_tags"] == ["earnest", "hopeful", "determined"]
    assert luke["traits"] == ["brave", "idealistic", "loyal"]
    assert luke["motivation"] == "Become a Jedi; fight for the Rebellion"
    assert any("CANON EXTENDED" in w for w in warnings)
    assert not bg


def test_canon_proximity_extended_includes_knowledge_boundary() -> None:
    """Extended NPC dict carries knowledge_boundary, knowledge_exclusions, and off_limits."""
    rule = _extended_rule()
    present, _, _ = apply_canon_proximity_rules(
        state=_state("historical"),
        effective_loc="loc-rebel-base",
        present_npcs=[],
        background_figures=[],
        canon_rules=[rule],
    )
    luke = present[0]
    assert luke.get("knowledge_boundary") == "0-4 ABY (Rebellion era)"
    assert "Does NOT know Vader is his father" in luke.get("knowledge_exclusions", [])
    assert "Cannot be killed" in luke.get("off_limits", [])
    assert "Training" in luke.get("scene_hooks", [])
    assert luke.get("character_voice_id") == "luke-skywalker"


def test_canon_proximity_extended_includes_voice_profile() -> None:
    """Extended NPC dict carries the NpcVoice data as a dict."""
    rule = _extended_rule()
    present, _, _ = apply_canon_proximity_rules(
        state=_state("historical"),
        effective_loc="loc-rebel-base",
        present_npcs=[],
        background_figures=[],
        canon_rules=[rule],
    )
    luke = present[0]
    voice = luke.get("voice")
    assert isinstance(voice, dict)
    assert voice["belief"] == "There is good in everyone."
    assert voice["wound"] == "Orphaned on a moisture farm."
    assert "Earnest" in voice["rhetorical_style"]


def test_canon_proximity_extended_enriches_existing_npc() -> None:
    """If the NPC already exists in present_npcs, extended enriches it in-place."""
    existing = {"id": "npc-luke", "name": "Luke Skywalker", "role": "pilot"}
    rule = _extended_rule()
    present, _, _ = apply_canon_proximity_rules(
        state=_state("historical"),
        effective_loc="loc-rebel-base",
        present_npcs=[existing],
        background_figures=[],
        canon_rules=[rule],
    )
    assert len(present) == 1
    luke = present[0]
    assert luke["id"] == "npc-luke"  # original ID preserved
    assert luke["canon_proximity"] == "extended"
    assert luke["voice_tags"] == ["earnest", "hopeful", "determined"]
    assert isinstance(luke.get("voice"), dict)


def test_canon_proximity_extended_noop_in_sandbox() -> None:
    """Extended proximity is bypassed entirely in sandbox mode."""
    rule = _extended_rule()
    existing = {"id": "npc-luke", "name": "Luke Skywalker", "role": "pilot"}
    present, bg, warnings = apply_canon_proximity_rules(
        state=_state("sandbox"),
        effective_loc="loc-rebel-base",
        present_npcs=[existing],
        background_figures=[],
        canon_rules=[rule],
    )
    assert len(present) == 1
    assert present[0].get("canon_proximity") is None
    assert not warnings
    assert not bg


def test_canon_proximity_extended_respects_exclusion_events() -> None:
    """Exclusion events take priority over extended — character is removed."""
    rule = _extended_rule()
    present, bg, warnings = apply_canon_proximity_rules(
        state=_state("historical", beat="Battle of Yavin trench run"),
        effective_loc="loc-rebel-base",
        present_npcs=[{"id": "npc-luke", "name": "Luke Skywalker"}],
        background_figures=[],
        canon_rules=[rule],
    )
    assert not any(n.get("name") == "Luke Skywalker" for n in present)
    assert any("redirected away" in w for w in warnings)
    assert any("pull you away" in line for line in bg)


def test_canon_proximity_extended_location_gating() -> None:
    """Extended character only appears if player is at one of their locations."""
    rule = _extended_rule(locations=["loc-training-ground"])
    present, _, warnings = apply_canon_proximity_rules(
        state=_state("historical"),
        effective_loc="loc-cantina",  # NOT in rule locations
        present_npcs=[],
        background_figures=[],
        canon_rules=[rule],
    )
    assert not present
    assert not warnings
