"""Tests for V2.10 starship acquisition: projection event, Director context, Mechanic transport."""
import json
import sqlite3
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from backend.app.core.projections import apply_projection
from backend.app.models.events import Event
from backend.app.models.state import GameState, CharacterSheet


def _create_in_memory_db() -> sqlite3.Connection:
    """Create a minimal in-memory SQLite DB with campaigns + player_starships tables."""
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
        CREATE TABLE player_starships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL,
            ship_type TEXT NOT NULL,
            custom_name TEXT,
            upgrades_json TEXT NOT NULL DEFAULT '{}',
            acquired_at TEXT NOT NULL DEFAULT (datetime('now')),
            acquired_method TEXT NOT NULL,
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
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
    return conn


class TestStarshipAcquiredEvent(unittest.TestCase):
    """Test STARSHIP_ACQUIRED event handler in projections."""

    def test_starship_acquired_creates_db_row(self):
        """STARSHIP_ACQUIRED event should insert a row into player_starships."""
        conn = _create_in_memory_db()
        conn.execute(
            "INSERT INTO campaigns (id, title, time_period, world_state_json) VALUES (?, ?, ?, ?)",
            ("c1", "Test", "REBELLION", "{}"),
        )
        event = Event(
            event_type="STARSHIP_ACQUIRED",
            payload={
                "ship_type": "ship-reb-yt1300",
                "acquired_method": "quest",
                "custom_name": "The Lucky Star",
            },
        )
        apply_projection(conn, "c1", [event], commit=True)
        # Verify row was created
        cur = conn.execute("SELECT * FROM player_starships WHERE campaign_id = 'c1'")
        row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["ship_type"], "ship-reb-yt1300")
        self.assertEqual(row["acquired_method"], "quest")
        self.assertEqual(row["custom_name"], "The Lucky Star")

    def test_starship_acquired_updates_world_state(self):
        """STARSHIP_ACQUIRED should set has_starship and active_starship in world_state_json."""
        conn = _create_in_memory_db()
        conn.execute(
            "INSERT INTO campaigns (id, title, time_period, world_state_json) VALUES (?, ?, ?, ?)",
            ("c1", "Test", "REBELLION", "{}"),
        )
        event = Event(
            event_type="STARSHIP_ACQUIRED",
            payload={"ship_type": "ship-reb-firespray", "acquired_method": "salvage"},
        )
        apply_projection(conn, "c1", [event], commit=True)
        cur = conn.execute("SELECT world_state_json FROM campaigns WHERE id = 'c1'")
        ws = json.loads(cur.fetchone()[0])
        self.assertTrue(ws.get("has_starship"))
        self.assertEqual(ws.get("active_starship"), "ship-reb-firespray")

    def test_starship_acquired_missing_ship_type_is_noop(self):
        """STARSHIP_ACQUIRED with no ship_type should not create a row."""
        conn = _create_in_memory_db()
        conn.execute(
            "INSERT INTO campaigns (id, title, time_period, world_state_json) VALUES (?, ?, ?, ?)",
            ("c1", "Test", "REBELLION", "{}"),
        )
        event = Event(
            event_type="STARSHIP_ACQUIRED",
            payload={"acquired_method": "purchase"},  # no ship_type
        )
        apply_projection(conn, "c1", [event], commit=True)
        cur = conn.execute("SELECT COUNT(*) FROM player_starships WHERE campaign_id = 'c1'")
        self.assertEqual(cur.fetchone()[0], 0)


class TestDirectorStarshipContext(unittest.TestCase):
    """Test Director prompt includes starship awareness."""

    def _make_state(self, has_ship: bool) -> GameState:
        starship = {"ship_type": "ship-reb-yt1300", "has_starship": True} if has_ship else None
        return GameState(
            campaign_id="c1",
            player_id="p1",
            turn_number=3,
            current_location="mos_eisley_cantina",
            player=CharacterSheet(character_id="p1", name="Kael", stats={"Combat": 3}),
            campaign={"time_period": "REBELLION", "world_state_json": {}},
            player_starship=starship,
        )

    def test_no_ship_context_in_state(self):
        """GameState with no starship should have player_starship=None."""
        state = self._make_state(has_ship=False)
        self.assertIsNone(state.player_starship)

    def test_has_ship_context_in_state(self):
        """GameState with starship should have player_starship populated."""
        state = self._make_state(has_ship=True)
        self.assertIsNotNone(state.player_starship)
        self.assertEqual(state.player_starship["ship_type"], "ship-reb-yt1300")
        self.assertTrue(state.player_starship["has_starship"])


class TestBackgroundNoLongerGrantsShip(unittest.TestCase):
    """Verify that era pack backgrounds have null starting_starship."""

    def test_rebellion_backgrounds_no_starting_ship(self):
        """All Rebellion backgrounds should have starting_starship: null."""
        import yaml
        bg_path = _root / "data" / "static" / "era_packs" / "rebellion" / "backgrounds.yaml"
        if not bg_path.exists():
            self.skipTest("Rebellion backgrounds.yaml not found")
        with open(bg_path) as f:
            data = yaml.safe_load(f)
        backgrounds = data.get("backgrounds") or []
        for bg in backgrounds:
            self.assertIsNone(
                bg.get("starting_starship"),
                f"Background '{bg.get('id')}' should not grant a starting starship",
            )

    def test_new_republic_backgrounds_no_starting_ship(self):
        """All New Republic backgrounds should have starting_starship: null."""
        import yaml
        bg_path = _root / "data" / "static" / "era_packs" / "new_republic" / "backgrounds.yaml"
        if not bg_path.exists():
            self.skipTest("New Republic backgrounds.yaml not found")
        with open(bg_path) as f:
            data = yaml.safe_load(f)
        backgrounds = data.get("backgrounds") or []
        for bg in backgrounds:
            self.assertIsNone(
                bg.get("starting_starship"),
                f"Background '{bg.get('id')}' should not grant a starting starship",
            )


if __name__ == "__main__":
    unittest.main()
