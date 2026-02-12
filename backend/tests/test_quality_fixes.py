"""Tests for V2.9+ quality fixes: state_loader field extraction, projections null guard, companion node resilience."""
import json
import sqlite3
import sys
import unittest
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from backend.app.core.state_loader import load_campaign, _default_companion_state
from backend.app.core.projections import apply_projection


def _create_in_memory_db() -> sqlite3.Connection:
    """Create a minimal in-memory SQLite DB with the campaigns table."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE campaigns (
            id TEXT PRIMARY KEY,
            title TEXT,
            time_period TEXT,
            world_state_json TEXT,
            world_time_minutes INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE characters (
            id TEXT PRIMARY KEY,
            campaign_id TEXT,
            name TEXT,
            role TEXT,
            location_id TEXT,
            stats_json TEXT,
            hp_current INTEGER DEFAULT 10,
            relationship_score INTEGER DEFAULT 0,
            credits INTEGER DEFAULT 0,
            planet_id TEXT,
            background TEXT,
            psych_profile TEXT,
            cyoa_answers_json TEXT,
            gender TEXT,
            secret_agenda TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE inventory (
            id TEXT PRIMARY KEY,
            owner_id TEXT,
            item_name TEXT,
            quantity INTEGER DEFAULT 1,
            attributes_json TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE turn_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id TEXT,
            turn_number INTEGER,
            event_type TEXT,
            payload TEXT,
            is_hidden INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    return conn


class TestStateLoaderV29Fields(unittest.TestCase):
    """Test that load_campaign extracts V2.9 fields from world_state_json."""

    def test_defaults_include_v29_fields(self):
        """_default_companion_state includes faction_memory, npc_states, companion_triggers_fired."""
        defaults = _default_companion_state()
        self.assertIn("faction_memory", defaults)
        self.assertIn("npc_states", defaults)
        self.assertIn("companion_triggers_fired", defaults)
        self.assertEqual(defaults["faction_memory"], {})
        self.assertEqual(defaults["npc_states"], {})
        self.assertEqual(defaults["companion_triggers_fired"], [])

    def test_load_campaign_extracts_faction_memory(self):
        """faction_memory is extracted from world_state_json to top-level campaign key."""
        conn = _create_in_memory_db()
        ws = {"faction_memory": {"rebel_alliance": {"stance": "hostile", "plan": "ambush convoy"}}}
        conn.execute(
            "INSERT INTO campaigns (id, title, time_period, world_state_json) VALUES (?, ?, ?, ?)",
            ("c1", "Test", "REBELLION", json.dumps(ws)),
        )
        campaign = load_campaign(conn, "c1")
        self.assertIsNotNone(campaign)
        self.assertEqual(campaign["faction_memory"], ws["faction_memory"])

    def test_load_campaign_extracts_npc_states(self):
        """npc_states is extracted from world_state_json to top-level campaign key."""
        conn = _create_in_memory_db()
        ws = {"npc_states": {"npc-001": {"location": "cantina", "goal": "recruit"}}}
        conn.execute(
            "INSERT INTO campaigns (id, title, time_period, world_state_json) VALUES (?, ?, ?, ?)",
            ("c1", "Test", "REBELLION", json.dumps(ws)),
        )
        campaign = load_campaign(conn, "c1")
        self.assertIsNotNone(campaign)
        self.assertEqual(campaign["npc_states"], ws["npc_states"])

    def test_load_campaign_extracts_companion_triggers_fired(self):
        """companion_triggers_fired is extracted from world_state_json."""
        conn = _create_in_memory_db()
        ws = {"companion_triggers_fired": ["comp-reb-kira:COMPANION_REQUEST"]}
        conn.execute(
            "INSERT INTO campaigns (id, title, time_period, world_state_json) VALUES (?, ?, ?, ?)",
            ("c1", "Test", "REBELLION", json.dumps(ws)),
        )
        campaign = load_campaign(conn, "c1")
        self.assertIsNotNone(campaign)
        self.assertEqual(campaign["companion_triggers_fired"], ["comp-reb-kira:COMPANION_REQUEST"])

    def test_load_campaign_defaults_when_v29_fields_missing(self):
        """When V2.9 fields are absent from world_state_json, defaults are used."""
        conn = _create_in_memory_db()
        ws = {"party": ["comp-reb-kira"]}  # No faction_memory, npc_states, or companion_triggers_fired
        conn.execute(
            "INSERT INTO campaigns (id, title, time_period, world_state_json) VALUES (?, ?, ?, ?)",
            ("c1", "Test", "REBELLION", json.dumps(ws)),
        )
        campaign = load_campaign(conn, "c1")
        self.assertIsNotNone(campaign)
        self.assertEqual(campaign["faction_memory"], {})
        self.assertEqual(campaign["npc_states"], {})
        self.assertEqual(campaign["companion_triggers_fired"], [])


class TestProjectionNullGuard(unittest.TestCase):
    """Test that apply_projection handles None event_type gracefully."""

    def test_none_event_type_does_not_crash(self):
        """An event-like object with event_type=None should be skipped without crashing."""
        from types import SimpleNamespace

        conn = _create_in_memory_db()
        conn.execute(
            "INSERT INTO campaigns (id, title, time_period, world_state_json) VALUES (?, ?, ?, ?)",
            ("c1", "Test", "REBELLION", "{}"),
        )
        # Use SimpleNamespace to simulate a malformed event (Pydantic Event won't allow None)
        bad_event = SimpleNamespace(event_type=None, payload={}, is_hidden=False)
        # Should not raise
        apply_projection(conn, "c1", [bad_event], commit=False)

    def test_empty_string_event_type_does_not_crash(self):
        """An event-like object with event_type='' should be skipped without crashing."""
        from types import SimpleNamespace

        conn = _create_in_memory_db()
        conn.execute(
            "INSERT INTO campaigns (id, title, time_period, world_state_json) VALUES (?, ?, ?, ?)",
            ("c1", "Test", "REBELLION", "{}"),
        )
        bad_event = SimpleNamespace(event_type="", payload={}, is_hidden=False)
        apply_projection(conn, "c1", [bad_event], commit=False)


class TestCompanionNodeResilience(unittest.TestCase):
    """Test that companion_reaction_node survives errors gracefully."""

    def test_node_survives_bad_mechanic_result(self):
        """companion_reaction_node should not crash on malformed mechanic_result."""
        from backend.app.core.nodes.companion import companion_reaction_node

        # Simulate a state with a malformed mechanic_result
        state = {
            "campaign_id": "c1",
            "player_id": "p1",
            "turn_number": 1,
            "mechanic_result": "not_a_dict",  # Should be a dict
            "campaign": {
                "party": ["comp-reb-kira"],
                "party_traits": {"comp-reb-kira": {"idealist_pragmatic": 80}},
            },
        }
        # Should not raise — should return state (potentially with warning)
        result = companion_reaction_node(state)
        self.assertIsNotNone(result)

    def test_node_returns_state_on_missing_campaign(self):
        """companion_reaction_node returns state unchanged when campaign is missing."""
        from backend.app.core.nodes.companion import companion_reaction_node

        state = {
            "campaign_id": "c1",
            "player_id": "p1",
            "turn_number": 1,
            "mechanic_result": None,
        }
        result = companion_reaction_node(state)
        self.assertEqual(result, state)


if __name__ == "__main__":
    unittest.main()
