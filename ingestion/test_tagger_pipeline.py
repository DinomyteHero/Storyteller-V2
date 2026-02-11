"""Pipeline test: tagger metadata fields persist in LanceDB rows."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from shared.config import EMBEDDING_DIMENSION
from ingestion.store import LanceStore
from ingestion.tagger import apply_tagger_to_chunks


class _DummyLLM:
    def complete(self, system_prompt: str, user_prompt: str, json_mode: bool = False) -> str:
        return (
            '{'
            '"doc_type":"wiki",'
            '"section_kind":"location",'
            '"entities":{"characters":[],"factions":["Rebels"],"planets":["Tatooine"],"items":[]},'
            '"timeline":{"era":"LOTF","start":null,"end":null,"confidence":0.4},'
            '"summary_1s":"A location summary.",'
            '"injection_risk":"med"'
            '}'
        )


class TestTaggerPipeline(unittest.TestCase):
    def test_metadata_fields_written(self) -> None:
        chunks = [{
            "text": "Tatooine is a desert world.",
            "metadata": {"era": "LOTF", "doc_type": "novel", "section_kind": "lore", "characters": []},
        }]
        tagged, _stats = apply_tagger_to_chunks(chunks, enabled=True, llm=_DummyLLM())

        with tempfile.TemporaryDirectory() as tmp:
            with patch("ingestion.store.embed_texts", return_value=[[0.0] * EMBEDDING_DIMENSION]):
                store = LanceStore(tmp)
                store.add_chunks(tagged)
                data = store.table.to_arrow().to_pydict()

        self.assertIn("entities_json", data)
        self.assertIn("summary_1s", data)
        self.assertIn("injection_risk", data)
        self.assertIn("timeline_start", data)
        self.assertIn("timeline_end", data)
        self.assertIn("timeline_confidence", data)
        self.assertTrue(data["summary_1s"][0])
        self.assertEqual(data["injection_risk"][0], "med")
