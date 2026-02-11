"""Living World (V2.5) tests: world clock advancement and psych_profile storage/retrieval."""
import json
import os
import tempfile
from unittest.mock import patch

import pytest

from backend.app.db.migrate import apply_schema
from backend.app.db.connection import get_connection
from backend.app.core.state_loader import build_initial_gamestate, load_campaign, load_player_by_id
from backend.app.core.event_store import get_events
from backend.app.core.graph import run_turn
from backend.app.models.state import MechanicOutput, ActionSuggestion
from backend.app.models.narration import NarrationOutput


@pytest.fixture
def db_and_campaign():
    """Create a temp DB with schema and a campaign; yield (db_path, conn, campaign_id, player_id)."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name
    apply_schema(db_path)
    conn = get_connection(db_path)
    campaign_id = "test-living-world-campaign"
    player_id = "test-living-world-player"
    conn.execute(
        """INSERT INTO campaigns (id, title, time_period, world_state_json, world_time_minutes)
           VALUES (?, ?, ?, ?, ?)""",
        (campaign_id, "Test Living World", "LOTF", "{}", 0),
    )
    conn.execute(
        """INSERT INTO characters (id, campaign_id, name, role, location_id, stats_json, hp_current, relationship_score, secret_agenda, credits, psych_profile)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (player_id, campaign_id, "Hero", "Player", "loc-tavern", "{}", 10, None, None, 0, "{}"),
    )
    conn.commit()
    yield db_path, conn, campaign_id, player_id
    conn.close()
    if os.path.exists(db_path):
        os.unlink(db_path)


def test_world_clock_advancement(db_and_campaign):
    """Setup: Create a new campaign. Assert world_time_minutes is 0.
    Action: Simulate a turn where the Mechanic returns time_cost=120 (2 hours).
    Assert: campaign.world_time_minutes is now 120."""
    _db_path, conn, campaign_id, player_id = db_and_campaign

    # Setup: assert world_time_minutes is 0
    camp = load_campaign(conn, campaign_id)
    assert camp is not None
    assert int(camp.get("world_time_minutes") or 0) == 0, "New campaign should have world_time_minutes=0"

    # Action: simulate a turn with mechanic returning time_cost_minutes=120
    mechanic_result = MechanicOutput(
        action_type="IDLE",
        time_cost_minutes=120,
        events=[],
        narrative_facts=[],
    )

    def mechanic_resolve(gs):
        return mechanic_result

    director_plan_return = (
        "Keep pacing brisk.",
        [
            ActionSuggestion(label="Talk", intent_text="Say: Hello"),
            ActionSuggestion(label="Act", intent_text="Try something"),
            ActionSuggestion(label="Look", intent_text="Look around"),
        ],
    )
    narrator_output = NarrationOutput(text="Time passes. What do you do next?", citations=[])

    with patch("backend.app.core.nodes.mechanic.MechanicAgent") as MockMechanic:
        MockMechanic.return_value.resolve = mechanic_resolve
        with patch("backend.app.core.nodes.director.DirectorAgent") as MockDirector:
            MockDirector.return_value.plan.return_value = director_plan_return
            with patch("backend.app.core.nodes.narrator.NarratorAgent") as MockNarrator:
                MockNarrator.return_value.generate.return_value = narrator_output
                state = build_initial_gamestate(conn, campaign_id, player_id)
                state.user_input = "Wait for two hours"
                run_turn(conn, state)

    # Assert: campaign.world_time_minutes is now 120
    camp = load_campaign(conn, campaign_id)
    assert camp is not None
    assert int(camp.get("world_time_minutes") or 0) == 120, (
        "campaign.world_time_minutes should be 120 after a turn with time_cost_minutes=120"
    )


def test_psych_profile_update(db_and_campaign):
    """Setup: Create a character with a 'Calm' mood.
    Action: Update the character's psych_profile via direct DB update.
    Assert: Verify the JSON is stored and retrieved correctly."""
    _db_path, conn, campaign_id, player_id = db_and_campaign

    # Setup: set character psych_profile to Calm mood
    psych_calm = json.dumps({"current_mood": "Calm", "stress_level": 0, "active_trauma": None})
    conn.execute(
        "UPDATE characters SET psych_profile = ? WHERE id = ? AND campaign_id = ?",
        (psych_calm, player_id, campaign_id),
    )
    conn.commit()

    # Verify initial store/retrieve
    row = load_player_by_id(conn, campaign_id, player_id)
    assert row is not None
    assert row.get("psych_profile") == {"current_mood": "Calm", "stress_level": 0, "active_trauma": None}

    # Action: update psych_profile (e.g. after an event)
    psych_updated = json.dumps({
        "current_mood": "Anxious",
        "stress_level": 2,
        "active_trauma": "recent_loss",
    })
    conn.execute(
        "UPDATE characters SET psych_profile = ? WHERE id = ? AND campaign_id = ?",
        (psych_updated, player_id, campaign_id),
    )
    conn.commit()

    # Assert: JSON stored and retrieved correctly
    row = load_player_by_id(conn, campaign_id, player_id)
    assert row is not None
    profile = row.get("psych_profile")
    assert isinstance(profile, dict), "psych_profile should be parsed as dict"
    assert profile.get("current_mood") == "Anxious"
    assert profile.get("stress_level") == 2
    assert profile.get("active_trauma") == "recent_loss"


def test_turn_stress_updates_character_psych_authority(db_and_campaign):
    """Mechanic stress_delta must write characters.psych_profile (authoritative) each committed turn."""
    _db_path, conn, campaign_id, player_id = db_and_campaign
    conn.execute(
        "UPDATE characters SET psych_profile = ? WHERE id = ? AND campaign_id = ?",
        (json.dumps({"current_mood": "neutral", "stress_level": 3}), player_id, campaign_id),
    )
    conn.commit()

    mechanic_result = MechanicOutput(
        action_type="SNEAK",
        time_cost_minutes=10,
        events=[],
        narrative_facts=[],
        stress_delta=2,
    )

    def mechanic_resolve(gs):
        return mechanic_result

    director_plan_return = (
        "Keep pacing brisk.",
        [
            ActionSuggestion(label="Talk", intent_text="Say: Hello"),
            ActionSuggestion(label="Act", intent_text="Try something"),
            ActionSuggestion(label="Look", intent_text="Look around"),
        ],
    )
    narrator_output = NarrationOutput(text="You steady your breathing.", citations=[])

    with patch("backend.app.core.nodes.mechanic.MechanicAgent") as MockMechanic:
        MockMechanic.return_value.resolve = mechanic_resolve
        with patch("backend.app.core.nodes.director.DirectorAgent") as MockDirector:
            MockDirector.return_value.plan.return_value = director_plan_return
            with patch("backend.app.core.nodes.narrator.NarratorAgent") as MockNarrator:
                MockNarrator.return_value.generate.return_value = narrator_output
                state = build_initial_gamestate(conn, campaign_id, player_id)
                state.user_input = "Slip through the shadows"
                run_turn(conn, state)

    player_row = load_player_by_id(conn, campaign_id, player_id)
    assert player_row is not None
    psych = player_row.get("psych_profile") or {}
    assert psych.get("stress_level") == 5

    camp = load_campaign(conn, campaign_id)
    mirrored = ((camp or {}).get("world_state_json") or {}).get("psych_profile") or {}
    assert mirrored.get("stress_level") == 5


def test_hostile_npc_departure_persists_across_turns(db_and_campaign):
    """A hostile NPC departure should update the read model and remain absent on the next turn."""
    _db_path, conn, campaign_id, player_id = db_and_campaign
    npc_id = "hostile-npc-1"
    conn.execute(
        """INSERT INTO characters
           (id, campaign_id, name, role, location_id, stats_json, hp_current, relationship_score, secret_agenda, credits, psych_profile)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (npc_id, campaign_id, "Fleeing Hunter", "NPC", "loc-tavern", "{}", 10, -80, None, 0, "{}"),
    )
    conn.commit()

    mechanic_result = MechanicOutput(
        action_type="INTERACT",
        time_cost_minutes=5,
        events=[],
        narrative_facts=[],
    )

    def mechanic_resolve(gs):
        return mechanic_result

    director_plan_return = (
        "Keep pacing brisk.",
        [
            ActionSuggestion(label="Talk", intent_text="Say: Hello"),
            ActionSuggestion(label="Act", intent_text="Try something"),
            ActionSuggestion(label="Look", intent_text="Look around"),
        ],
    )
    narrator_output = NarrationOutput(text="The scene shifts quickly.", citations=[])

    with patch.dict(os.environ, {"ENCOUNTER_SEED": "1"}):
        with patch("backend.app.core.nodes.mechanic.MechanicAgent") as MockMechanic:
            MockMechanic.return_value.resolve = mechanic_resolve
            with patch("backend.app.core.nodes.director.DirectorAgent") as MockDirector:
                MockDirector.return_value.plan.return_value = director_plan_return
                with patch("backend.app.core.nodes.narrator.NarratorAgent") as MockNarrator:
                    MockNarrator.return_value.generate.return_value = narrator_output

                    first = build_initial_gamestate(conn, campaign_id, player_id)
                    first.user_input = "Survey the room"
                    run_turn(conn, first)

                    second = build_initial_gamestate(conn, campaign_id, player_id)
                    second.user_input = "Keep moving"
                    run_turn(conn, second)

    row = conn.execute(
        "SELECT location_id FROM characters WHERE id = ? AND campaign_id = ?",
        (npc_id, campaign_id),
    ).fetchone()
    assert row is not None
    assert row[0] is None

    events = get_events(conn, campaign_id, since_turn=0, include_hidden=True)
    dep_events = [
        e for e in events
        if e.get("event_type") == "NPC_DEPART" and (e.get("payload") or {}).get("character_id") == npc_id
    ]
    assert dep_events, "Expected at least one NPC_DEPART event for hostile NPC"
