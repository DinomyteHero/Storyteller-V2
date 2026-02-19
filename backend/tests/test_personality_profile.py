"""Tests for the NPC personality profile builder."""
from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from backend.app.core.personality_profile import (  # noqa: E402
    build_personality_block,
    build_scene_personality_context,
)


def test_han_solo_personality():
    """Han Solo's personality block should include his voice tags and traits."""
    han = {
        "name": "Han Solo",
        "archetype": "Reluctant hero",
        "traits": ["cocky", "charming", "cynical"],
        "voice_tags": ["wry", "fast", "sarcastic"],
        "motivation": "Get paid, stay free, and avoid Jabba's bounty hunters",
    }
    block = build_personality_block(han)
    assert "HAN SOLO" in block
    assert "Reluctant hero" in block
    assert "wry, fast, sarcastic" in block
    assert "cocky, charming, cynical" in block
    # Speech pattern should be derived from voice_tags
    assert "Speech pattern:" in block
    assert "deflecting humor" in block.lower() or "sarcastic" in block.lower()
    # Archetype interaction
    assert "Comes through in the clutch" in block
    # Motivation
    assert "Jabba" in block


def test_luke_skywalker_personality():
    """Luke's personality block should include earnest/hopeful voice."""
    luke = {
        "name": "Luke Skywalker",
        "archetype": "Idealistic hero",
        "traits": ["idealistic", "brave", "impulsive"],
        "voice_tags": ["earnest", "young", "hopeful"],
        "motivation": "Prove himself and fight for something greater than himself",
    }
    block = build_personality_block(luke)
    assert "LUKE SKYWALKER" in block
    assert "Idealistic hero" in block
    assert "earnest" in block.lower()
    # Behavioral note from traits
    assert "Behavior:" in block
    assert "greater good" in block.lower() or "idealistic" in block.lower()


def test_darth_vader_personality():
    """Vader's personality should convey menace and cold authority."""
    vader = {
        "name": "Darth Vader",
        "archetype": "Relentless hunter",
        "traits": ["ruthless", "powerful", "implacable"],
        "voice_tags": ["menacing", "mechanical", "cold"],
        "motivation": "Hunt down the last Jedi and crush the Rebellion",
    }
    block = build_personality_block(vader)
    assert "DARTH VADER" in block
    assert "menacing" in block.lower()
    assert "Relentless hunter" in block
    # Interaction style
    assert "persistence" in block.lower() or "Single-minded" in block


def test_empty_npc_returns_empty():
    """An NPC with no personality data should return empty string."""
    npc = {"name": "Random Guard", "role": "Guard"}
    block = build_personality_block(npc)
    assert block == ""


def test_partial_data():
    """An NPC with only traits (no voice_tags) should still produce a block."""
    npc = {
        "name": "Informant",
        "traits": ["cunning", "secretive"],
        "motivation": "Sell information to the highest bidder",
    }
    block = build_personality_block(npc)
    assert "INFORMANT" in block
    assert "cunning, secretive" in block
    assert "Drives:" in block


def test_unknown_tags_graceful():
    """Unknown voice_tags and traits should not cause errors."""
    npc = {
        "name": "Alien",
        "traits": ["unknown_trait_xyz"],
        "voice_tags": ["alien_garble"],
        "archetype": "Unknown archetype abc",
    }
    block = build_personality_block(npc)
    assert "ALIEN" in block
    # Should still include the raw tags even if no mapping exists
    assert "alien_garble" in block
    assert "unknown_trait_xyz" in block


def test_scene_context_multiple_npcs():
    """Scene context should build blocks for multiple NPCs."""
    npcs = [
        {"name": "Luke Skywalker", "id": "luke_skywalker"},
        {"name": "Han Solo", "id": "han_solo"},
        {"name": "Guard", "id": "guard_001"},
    ]
    era_lookup = {
        "luke_skywalker": {
            "name": "Luke Skywalker",
            "traits": ["idealistic"],
            "voice_tags": ["earnest"],
            "archetype": "Idealistic hero",
            "motivation": "Fight for the greater good",
        },
        "han_solo": {
            "name": "Han Solo",
            "traits": ["cocky"],
            "voice_tags": ["sarcastic"],
            "archetype": "Reluctant hero",
            "motivation": "Get paid",
        },
    }
    ctx = build_scene_personality_context(npcs, era_npc_lookup=era_lookup)
    assert "LUKE SKYWALKER" in ctx
    assert "HAN SOLO" in ctx
    # Guard has no era data — should not produce a block (no traits/voice)
    assert "GUARD" not in ctx


def test_scene_context_max_npcs():
    """Scene context should respect max_npcs limit."""
    npcs = [{"name": f"NPC{i}", "traits": ["brave"], "voice_tags": ["calm"], "motivation": "test"} for i in range(10)]
    ctx = build_scene_personality_context(npcs, max_npcs=2)
    # Only first 2 NPCs should have blocks
    assert "NPC0" in ctx
    assert "NPC1" in ctx
    assert "NPC2" not in ctx


def test_companion_speech_quirk():
    """Companions with speech_quirk should have it in the block."""
    companion = {
        "name": "Shade Vos",
        "archetype": "Underworld fixer",
        "traits": ["cunning"],
        "voice_tags": ["smooth"],
        "banter_style": "snarky",
        "speech_quirk": "Calls everyone 'friend' in a way that means 'mark'",
        "motivation": "Survive and profit",
    }
    block = build_personality_block(companion)
    assert "Quirk:" in block
    assert "friend" in block


def test_scene_context_reflects_companion_influence_state():
    """Companion influence state should modulate personality stance guidance."""
    npcs = [{"name": "Nyra", "id": "comp_nyra"}]
    companion_lookup = {
        "comp_nyra": {
            "name": "Nyra",
            "traits": ["loyal"],
            "voice_tags": ["warm"],
            "motivation": "Protect the crew",
        }
    }
    companion_state_lookup = {
        "comp_nyra": {"influence": 75, "trust": 80, "fear": 5}
    }
    ctx = build_scene_personality_context(
        npcs,
        companion_lookup=companion_lookup,
        companion_state_lookup=companion_state_lookup,
    )
    assert "Current stance: Warm and trusting" in ctx


# ---------------------------------------------------------------------------
# Voice profile (NpcVoice) tests
# ---------------------------------------------------------------------------


def test_personality_block_with_voice_profile():
    """build_personality_block should render NpcVoice fields when present."""
    npc = {
        "name": "Luke Skywalker",
        "archetype": "Reluctant hero",
        "voice_tags": ["earnest", "hopeful"],
        "traits": ["brave", "idealistic"],
        "motivation": "Become a Jedi",
        "voice": {
            "belief": "There is good in everyone.",
            "wound": "Orphaned on a moisture farm.",
            "rhetorical_style": "Earnest and direct.",
            "tell": "Gazes at the horizon.",
            "taboo": "Refuses to accept anyone is beyond redemption.",
        },
    }
    block = build_personality_block(npc)
    assert "Core belief: There is good in everyone." in block
    assert "Formative wound: Orphaned on a moisture farm." in block
    assert "Rhetorical style: Earnest and direct." in block
    assert "Tell/mannerism: Gazes at the horizon." in block
    assert "Taboo (never discusses): Refuses to accept anyone is beyond redemption." in block


def test_personality_block_voice_profile_partial():
    """Voice profile with only some fields should render those present."""
    npc = {
        "name": "Mysterious Stranger",
        "traits": ["cunning"],
        "motivation": "Unknown",
        "voice": {
            "belief": "Trust no one.",
            "wound": None,
            "rhetorical_style": "",
            "tell": "Taps fingers on the table.",
            "taboo": None,
        },
    }
    block = build_personality_block(npc)
    assert "Core belief: Trust no one." in block
    assert "Tell/mannerism: Taps fingers" in block
    # None and empty-string fields should NOT appear
    assert "Formative wound" not in block
    assert "Rhetorical style" not in block
    assert "Taboo" not in block


def test_personality_block_voice_profile_ignored_when_not_dict():
    """Non-dict voice value should be ignored without error."""
    npc = {
        "name": "Droid",
        "traits": ["loyal"],
        "motivation": "Serve",
        "voice": "beep boop",  # invalid — should be ignored
    }
    block = build_personality_block(npc)
    assert "DROID" in block
    assert "Core belief" not in block


# ---------------------------------------------------------------------------
# Canon extended context tests
# ---------------------------------------------------------------------------


def test_scene_context_canon_extended_knowledge_boundary():
    """Canon extended NPC should get knowledge boundary and off-limits in scene context."""
    npcs = [
        {
            "name": "Luke Skywalker",
            "archetype": "Reluctant hero",
            "voice_tags": ["earnest"],
            "traits": ["brave"],
            "motivation": "Become a Jedi",
            "canon_proximity": "extended",
            "knowledge_boundary": "0-4 ABY (Rebellion era)",
            "knowledge_exclusions": [
                "Does NOT know Vader is his father",
                "Does NOT know Leia is his sister",
            ],
            "scene_hooks": ["Training", "Tactical briefings"],
            "off_limits": ["Cannot be killed", "Cannot turn to the dark side"],
        }
    ]
    ctx = build_scene_personality_context(npcs)
    assert "KNOWLEDGE BOUNDARY" in ctx
    assert "0-4 ABY" in ctx
    assert "Do NOT reference events" in ctx
    assert "Does NOT know Vader is his father" in ctx
    assert "Does NOT know Leia is his sister" in ctx
    assert "Scene hooks" in ctx
    assert "Training" in ctx
    assert "OFF-LIMITS" in ctx
    assert "Cannot be killed" in ctx
    assert "Cannot turn to the dark side" in ctx


def test_scene_context_non_extended_canon_skips_knowledge_boundary():
    """Non-extended canon NPCs should NOT get knowledge boundary injection."""
    npcs = [
        {
            "name": "Princess Leia",
            "voice_tags": ["commanding"],
            "traits": ["strategic"],
            "motivation": "Restore the Republic",
            "canon_protected": True,
            "canon_proximity": "interaction",
            "knowledge_boundary": "0-4 ABY",
            "off_limits": ["Cannot be killed"],
        }
    ]
    ctx = build_scene_personality_context(npcs)
    assert "PRINCESS LEIA" in ctx
    # Knowledge boundary and off-limits should NOT appear for non-extended
    assert "KNOWLEDGE BOUNDARY" not in ctx
    assert "OFF-LIMITS" not in ctx


def test_scene_context_canon_extended_without_optional_fields():
    """Extended NPC with no knowledge_exclusions or off_limits should still work."""
    npcs = [
        {
            "name": "Han Solo",
            "voice_tags": ["wry"],
            "traits": ["cocky"],
            "motivation": "Get paid",
            "canon_proximity": "extended",
            "knowledge_boundary": "0-4 ABY",
        }
    ]
    ctx = build_scene_personality_context(npcs)
    assert "KNOWLEDGE BOUNDARY" in ctx
    assert "0-4 ABY" in ctx
    # These should not appear since they weren't provided
    assert "THIS CHARACTER DOES NOT KNOW" not in ctx
    assert "OFF-LIMITS" not in ctx
