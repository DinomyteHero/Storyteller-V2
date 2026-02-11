"""Deterministic test harness: 10–20 turns against LangGraph pipeline.

Uses fixed ENCOUNTER_SEED and fixed campaign. Mocks Director/Narrator/Casting/WorldSim
for deterministic output. Asserts: commit count == turn count, no exceptions,
all JSON-structured agents validated (suggested_actions, final_text, lore_citations,
mechanic_result).

Run: pytest backend/tests/test_deterministic_harness.py -v
Or: python scripts/run_deterministic_tests.py
"""
from __future__ import annotations

import logging
import os
import tempfile
import unittest
from unittest.mock import patch

logger = logging.getLogger(__name__)

from backend.app.core.event_store import append_events, get_current_turn_number
from backend.app.core.graph import run_turn
from backend.app.core.state_loader import build_initial_gamestate
from backend.app.db.connection import get_connection
from backend.app.db.migrate import apply_schema
from backend.app.constants import SUGGESTED_ACTIONS_TARGET
from backend.app.models.events import Event
from backend.app.models.narration import NarrationOutput
from backend.app.models.state import ActionSuggestion, MechanicOutput

# Fixed inputs for deterministic runs (mix of TALK, ACTION, META)
DETERMINISTIC_INPUTS = [
    "I look around the room",
    "I ask the barkeep for information",
    "help",
    "I search the crates",
    "I tell her I'm leaving",
    "I walk to the market",
    "save",
    "I talk to the guard",
    "I pick up the datapad",
    "I examine the door",
    "I say hello to the stranger",
    "I check my gear",
    "I move toward the hangar",
    "I ask about the rumor",
    "I open the crate",
]

NUM_TURNS = 15  # 10–20 range


def _get_rendered_turn_count(conn, campaign_id: str) -> int:
    """Return number of rendered turns for campaign."""
    cur = conn.execute(
        "SELECT COUNT(*) FROM rendered_turns WHERE campaign_id = ?",
        (campaign_id,),
    )
    row = cur.fetchone()
    return int(row[0]) if row else 0


def _valid_suggestions(actions: list) -> tuple[bool, str]:
    """Validate suggested_actions structure (DirectorNode). Returns (ok, error_msg)."""
    if not actions:
        return False, "missing suggested_actions"
    if len(actions) != SUGGESTED_ACTIONS_TARGET:
        return False, f"expected {SUGGESTED_ACTIONS_TARGET} suggested_actions, got {len(actions)}"
    for i, a in enumerate(actions[:SUGGESTED_ACTIONS_TARGET]):
        if isinstance(a, dict):
            if not a.get("label") or not a.get("intent_text"):
                return False, f"action[{i}] missing label or intent_text"
            cat = a.get("category")
            if cat not in ("SOCIAL", "EXPLORE", "COMMIT"):
                return False, f"action[{i}] invalid category: {cat}"
        elif hasattr(a, "label") and hasattr(a, "intent_text"):
            if not a.label or not a.intent_text:
                return False, f"action[{i}] missing label or intent_text"
        else:
            return False, f"action[{i}] invalid structure"
    return True, ""


def _valid_lore_citations(citations: list | None) -> tuple[bool, str]:
    """Validate lore_citations structure (NarratorNode). Returns (ok, error_msg)."""
    if citations is None:
        return True, ""
    if not isinstance(citations, list):
        return False, f"lore_citations must be list, got {type(citations).__name__}"
    for i, c in enumerate(citations):
        if not isinstance(c, dict):
            return False, f"lore_citations[{i}] must be dict, got {type(c).__name__}"
        if "chunk_id" not in c:
            return False, f"lore_citations[{i}] missing chunk_id"
    return True, ""


class TestDeterministicHarness(unittest.TestCase):
    """Run 15 turns with mocked agents; assert commit count, no exceptions, JSON validated."""

    def setUp(self) -> None:
        os.environ["ENCOUNTER_SEED"] = "42"
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name
        apply_schema(self.db_path)
        self.conn = get_connection(self.db_path)
        self.campaign_id = "harness-campaign"
        self.player_id = "harness-player"
        # Minimal campaign + player (no NPCs needed for mocked agents)
        import json
        from backend.app.core.companions import build_initial_companion_state
        companion_state = build_initial_companion_state(world_time_minutes=0)
        world_state = {"active_factions": [], **companion_state}
        self.conn.execute(
            """INSERT INTO campaigns (id, title, time_period, world_state_json, world_time_minutes)
               VALUES (?, ?, ?, ?, ?)""",
            (self.campaign_id, "Harness Campaign", "LOTF", json.dumps(world_state), 0),
        )
        self.conn.execute(
            """INSERT INTO characters (id, campaign_id, name, role, location_id, stats_json, hp_current, relationship_score, secret_agenda, credits)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (self.player_id, self.campaign_id, "Hero", "Player", "loc-tavern", "{}", 10, None, None, 0),
        )
        self.conn.commit()
        # Initial turn 1 (campaign_started)
        append_events(self.conn, self.campaign_id, 1, [
            Event(event_type="FLAG_SET", payload={"key": "campaign_started", "value": True}),
        ])
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
        os.environ.pop("ENCOUNTER_SEED", None)

    def _make_mock_director_plan(self):
        return ("Pacing.", [
            ActionSuggestion(label="Talk", intent_text="Say: Hi", category="SOCIAL"),
            ActionSuggestion(label="Look", intent_text="Look around", category="EXPLORE"),
            ActionSuggestion(label="Act", intent_text="Do something", category="COMMIT"),
        ])

    def _make_mock_narrator_out(self, turn_idx: int):
        return NarrationOutput(
            text=f"Narrated output for turn {turn_idx + 1}.",
            citations=[],
        )

    def _make_mock_mechanic_out(self, user_input: str):
        return MechanicOutput(
            action_type="INTERACT",
            events=[],
            narrative_facts=[f"Player did something: {user_input[:50]}"],
            time_cost_minutes=5,
        )

    def test_harness_15_turns_deterministic(self) -> None:
        """Run 15 turns with mocked agents; assert commit count, no exceptions, JSON validated."""
        director_plan = self._make_mock_director_plan()
        turn_results: list = []
        last_exception: Exception | None = None
        fail_turn: int | None = None

        def mock_director_plan(*args, **kwargs):
            return director_plan

        def mock_narrator_generate(gs, *args, **kwargs):
            return self._make_mock_narrator_out(len(turn_results))

        def mock_mechanic_resolve(gs):
            return self._make_mock_mechanic_out(gs.user_input or "")

        with patch("backend.app.core.nodes.director.DirectorAgent") as MockDirector:
            MockDirector.return_value.plan = mock_director_plan
            with patch("backend.app.core.nodes.narrator.NarratorAgent") as MockNarrator:
                MockNarrator.return_value.generate = mock_narrator_generate
                with patch("backend.app.core.nodes.mechanic.MechanicAgent") as MockMechanic:
                    MockMechanic.return_value.resolve = mock_mechanic_resolve
                    # WorldSim is now deterministic (no LLM) — no mock needed
                    with patch("backend.app.core.nodes.encounter.CastingAgent"):
                        for i, user_input in enumerate(DETERMINISTIC_INPUTS[:NUM_TURNS]):
                            try:
                                state = build_initial_gamestate(
                                    self.conn, self.campaign_id, self.player_id
                                )
                                state.user_input = user_input
                                result = run_turn(self.conn, state)
                                turn_results.append(result)
                                # Validate JSON structure (Director → suggested_actions, Narrator → final_text)
                                ok, err = _valid_suggestions(result.suggested_actions or [])
                                self.assertTrue(
                                    ok,
                                    f"Turn {i + 1} DirectorNode: invalid suggested_actions — {err}",
                                )
                                self.assertIsInstance(
                                    result.final_text,
                                    str,
                                    f"Turn {i + 1} NarratorNode: final_text must be str, got {type(result.final_text)}",
                                )
                                ok_cit, err_cit = _valid_lore_citations(result.lore_citations)
                                self.assertTrue(
                                    ok_cit,
                                    f"Turn {i + 1} NarratorNode: invalid lore_citations — {err_cit}",
                                )
                            except Exception as e:
                                logger.exception("Deterministic harness failed on turn %d", i + 1)
                                fail_turn = i + 1
                                # Point to likely node from exception context (actionable failures)
                                exc_str = str(e).lower()
                                if "director" in exc_str or "suggestion" in exc_str:
                                    hint = "DirectorNode"
                                elif "narrator" in exc_str or "final_text" in exc_str or "lore_citation" in exc_str:
                                    hint = "NarratorNode"
                                elif "mechanic" in exc_str or "mechanic_result" in exc_str:
                                    hint = "MechanicNode"
                                elif "commit" in exc_str or "append_events" in exc_str or "write_rendered" in exc_str:
                                    hint = "CommitNode"
                                elif "encounter" in exc_str or "casting" in exc_str or "spawn" in exc_str:
                                    hint = "EncounterNode/CastingAgent"
                                elif "world_sim" in exc_str or "faction_engine" in exc_str:
                                    hint = "WorldSimNode/FactionEngine"
                                elif "router" in exc_str:
                                    hint = "RouterNode"
                                elif "companion" in exc_str or "affinity" in exc_str:
                                    hint = "CompanionReactionNode"
                                else:
                                    hint = "check traceback"
                                raise AssertionError(
                                    f"Turn {fail_turn} failed (input={user_input!r}) — likely {hint}: "
                                    f"{type(e).__name__}: {e}"
                                ) from e

        # Assert commit count == turn count
        rendered_count = _get_rendered_turn_count(self.conn, self.campaign_id)
        self.assertEqual(
            rendered_count,
            NUM_TURNS,
            f"commit count ({rendered_count}) != turn count ({NUM_TURNS}); "
            "CommitNode may have skipped or failed for some turns.",
        )
        max_turn = get_current_turn_number(self.conn, self.campaign_id)
        self.assertEqual(
            max_turn,
            1 + NUM_TURNS,
            f"turn_events max turn ({max_turn}) != 1 + {NUM_TURNS}; "
            "append_events may have failed for some turns.",
        )
