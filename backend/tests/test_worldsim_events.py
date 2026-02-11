"""Tests for WorldSim event conversion and projections."""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from backend.app.core.nodes.world_sim import make_world_sim_node
from backend.app.core.projections import apply_projection
from backend.app.db.migrate import apply_schema
from backend.app.models.events import Event
from shared.schemas import WorldSimOutput


class TestWorldSimEvents(unittest.TestCase):
    def test_worldsim_outputs_to_events(self) -> None:
        output = WorldSimOutput(
            elapsed_time_summary="tick",
            faction_moves=["Faction A moved to Core"],
            new_rumors=["A rumor spreads"],
            hidden_events=["NPC agent sabotaged a relay"],
            updated_factions=[{"name": "Faction A", "location": "Core", "current_goal": "Expand", "resources": 5, "is_hostile": False}],
        )
        node = make_world_sim_node()
        state = {
            "campaign": {"world_time_minutes": 0},
            "mechanic_result": {"time_cost_minutes": 240},
            "turn_number": 1,
            "current_location": "loc-tavern",
            "campaign_id": "c1",
            "__runtime_conn": None,
        }
        # WorldSim is now deterministic — mock faction engine for controlled output
        with patch("backend.app.core.nodes.world_sim.simulate_faction_tick", return_value=output):
            out = node(state)
        events = out.get("world_sim_events") or []
        event_types = {e.get("event_type") for e in events if isinstance(e, dict)}
        self.assertIn("FACTION_MOVE", event_types)
        self.assertIn("RUMOR_SPREAD", event_types)
        self.assertTrue({"NPC_ACTION", "PLOT_TICK"} & event_types)

    def test_projection_appends_world_sim_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            apply_schema(str(db_path))
            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute(
                    "INSERT INTO campaigns (id, title, time_period, world_state_json) VALUES (?, ?, ?, ?)",
                    ("c1", "Test", "LOTF", "{}"),
                )
                evs = [
                    Event(event_type="FACTION_MOVE", payload={"text": "Faction moved"}, is_hidden=True),
                    Event(event_type="RUMOR_SPREAD", payload={"text": "Rumor"}, is_public_rumor=True),
                ]
                apply_projection(conn, "c1", evs, commit=True)
                row = conn.execute("SELECT world_state_json FROM campaigns WHERE id = ?", ("c1",)).fetchone()
                self.assertIsNotNone(row)
                self.assertIn("world_sim_events", row[0])
            finally:
                conn.close()
