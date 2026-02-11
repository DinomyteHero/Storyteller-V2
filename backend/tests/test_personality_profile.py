"""Tests for the NPC personality profile builder."""
from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from backend.app.core.personality_profile import (
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
