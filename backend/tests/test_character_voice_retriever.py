"""Tests for character voice retriever: fallback logic, missing table."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import lancedb
import pyarrow as pa
from unittest.mock import patch

from backend.app.rag.character_voice_retriever import (
    get_voice_snippets,
    VoiceSnippet,
)

TABLE_NAME = "character_voice_chunks"
VECTOR_DIM = 384  # LanceDB often expects vector for search; we use filter-only


def _make_voice_table(tmp_path: str, rows: list[dict]) -> None:
    """Create character_voice_chunks table with given rows."""
    db = lancedb.connect(tmp_path)
    if rows:
        for r in rows:
            if "vector" not in r:
                r["vector"] = [0.0] * VECTOR_DIM
        tbl = db.create_table(TABLE_NAME, data=rows, mode="overwrite")
    else:
        schema = pa.schema([
            pa.field("character_id", pa.string()),
            pa.field("era", pa.string()),
            pa.field("text", pa.string()),
            pa.field("chunk_id", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), VECTOR_DIM)),
        ])
        tbl = db.create_table(TABLE_NAME, schema=schema, mode="overwrite")


class _DummyEncoder:
    def encode(self, texts, show_progress_bar: bool = False):
        return [[0.0] * VECTOR_DIM for _ in texts]


class TestCharacterVoiceRetriever(unittest.TestCase):
    """Test voice snippet retrieval and fallback logic."""

    def setUp(self) -> None:
        self._encoder_patcher = patch(
            "backend.app.rag.character_voice_retriever.get_encoder",
            return_value=_DummyEncoder(),
        )
        self._encoder_patcher.start()

    def tearDown(self) -> None:
        self._encoder_patcher.stop()

    def test_missing_table_returns_empty(self) -> None:
        """When character_voice_chunks table does not exist, return empty dict."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create DB with only lore_chunks (no voice table)
            db = lancedb.connect(tmp)
            schema = pa.schema([
                pa.field("id", pa.string()),
                pa.field("text", pa.string()),
            ])
            db.create_table("lore_chunks", schema=schema, mode="overwrite")
            result = get_voice_snippets(
                character_ids=["comp-kira", "luke_skywalker"],
                era="LOTF",
                k=6,
                db_path=tmp,
            )
            self.assertEqual(result, {"comp-kira": [], "luke_skywalker": []})

    def test_empty_character_ids_returns_empty_dict(self) -> None:
        """Empty character_ids returns {}."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_voice_table(tmp, [])
            result = get_voice_snippets([], "LOTF", k=6, db_path=tmp)
            self.assertEqual(result, {})

    def test_empty_era_returns_empty_results(self) -> None:
        """Empty era returns empty snippets per character."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_voice_table(tmp, [
                {"character_id": "comp-kira", "era": "LOTF", "text": "We must act.", "chunk_id": "v1"},
            ])
            result = get_voice_snippets(["comp-kira"], "", k=6, db_path=tmp)
            self.assertEqual(result.get("comp-kira", []), [])

    def test_era_scoped_returns_matching(self) -> None:
        """Filter by (character_id, era) returns matching snippets. With >= k/2 results, no widen."""
        with tempfile.TemporaryDirectory() as tmp:
            rows = [
                {"character_id": "comp-kira", "era": "LOTF", "text": "The Force guides us.", "chunk_id": "v1"},
                {"character_id": "comp-kira", "era": "LOTF", "text": "Trust the Order.", "chunk_id": "v2"},
                {"character_id": "comp-kira", "era": "LOTF", "text": "We must act.", "chunk_id": "v3"},
                {"character_id": "comp-kira", "era": "Prequel", "text": "Old era line.", "chunk_id": "v4"},
            ]
            _make_voice_table(tmp, rows)
            db = lancedb.connect(tmp)
            table = db.open_table(TABLE_NAME)
            with patch("backend.app.rag.character_voice_retriever.get_lancedb_table", return_value=table), \
                 patch.object(table, "to_arrow", side_effect=AssertionError("full scan")):
                result = get_voice_snippets(["comp-kira"], "LOTF", k=6, db_path=tmp)
            kira = result.get("comp-kira", [])
            self.assertEqual(len(kira), 3)
            texts = [s.text for s in kira]
            self.assertIn("The Force guides us.", texts)
            self.assertIn("Trust the Order.", texts)
            self.assertIn("We must act.", texts)
            self.assertNotIn("Old era line.", texts)

    def test_fallback_widens_to_any_era(self) -> None:
        """If < k/2 era-scoped results, widen to any era."""
        with tempfile.TemporaryDirectory() as tmp:
            rows = [
                {"character_id": "comp-vex", "era": "Other", "text": "Only from Other era.", "chunk_id": "v1"},
            ]
            _make_voice_table(tmp, rows)
            result = get_voice_snippets(["comp-vex"], "LOTF", k=6, db_path=tmp)
            vex = result.get("comp-vex", [])
            self.assertEqual(len(vex), 1)
            self.assertEqual(vex[0].text, "Only from Other era.")
            self.assertEqual(vex[0].era, "Other")

    def test_nonexistent_db_path_returns_empty(self) -> None:
        """When DB path does not exist, return empty per character."""
        result = get_voice_snippets(
            ["comp-kira"],
            "LOTF",
            k=6,
            db_path="/nonexistent/path/xyz123",
        )
        self.assertEqual(result.get("comp-kira", []), [])


class TestNarratorWithVoiceRetriever(unittest.TestCase):
    """Narrator must run when voice table is missing (voice_retriever returns empty)."""

    def test_narrator_runs_when_voice_table_missing(self) -> None:
        """NarratorAgent.generate completes when voice retriever returns empty (missing table)."""
        from backend.app.core.agents.narrator import NarratorAgent
        from backend.app.models.state import GameState

        def empty_voice_retriever(cids, era, k=6):
            return {cid: [] for cid in (cids or [])}

        narrator = NarratorAgent(
            llm=None,
            lore_retriever=lambda q, top_k=6, era=None, related_npcs=None, **_kw: [],
            voice_retriever=empty_voice_retriever,
        )
        from backend.app.models.state import MechanicOutput

        state = GameState(
            campaign_id="c1",
            player_id="p1",
            turn_number=1,
            current_location="loc-tavern",
            campaign={"time_period": "LOTF", "party": ["comp-kira"]},
            present_npcs=[{"id": "npc-1", "name": "Barkeep", "role": "Barkeep"}],
            mechanic_result=MechanicOutput(action_type="TALK", events=[], narrative_facts=[]),
        )
        output = narrator.generate(state)
        self.assertIsNotNone(output)
        self.assertIn("text", dir(output))
        self.assertTrue(len(output.text) > 0)
