"""Unit tests for ingestion tagger schema parsing."""
import sys
import unittest
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from ingestion.tagger import apply_tagger_to_chunks, tag_chunk


class _DummyLLM:
    def complete(self, system_prompt: str, user_prompt: str, json_mode: bool = False) -> str:
        return (
            '{'
            '"doc_type":"sourcebook",'
            '"section_kind":"lore",'
            '"entities":{"characters":["Luke"],"factions":["Rebels"],"planets":["Tatooine"],"items":["Lightsaber"]},'
            '"timeline":{"era":"LOTF","start":"40 ABY","end":null,"confidence":0.6},'
            '"summary_1s":"A short summary.",'
            '"injection_risk":"low"'
            '}'
        )


class TestIngestionTagger(unittest.TestCase):
    def test_tagger_schema_parses(self) -> None:
        result = tag_chunk("Luke walks into Mos Eisley.", llm=_DummyLLM())
        self.assertIsNotNone(result.output)
        output = result.output
        self.assertEqual(output.doc_type, "sourcebook")
        self.assertEqual(output.section_kind, "lore")
        self.assertEqual(output.entities.characters, ["Luke"])
        self.assertEqual(output.timeline.era, "LOTF")
        self.assertEqual(output.summary_1s, "A short summary.")
        self.assertEqual(output.injection_risk, "low")

    def test_apply_tagger_to_chunks(self) -> None:
        chunks = [{
            "text": "Luke walks into Mos Eisley.",
            "metadata": {"doc_type": "novel", "section_kind": "lore", "era": "LOTF"},
        }]
        updated, stats = apply_tagger_to_chunks(chunks, enabled=True, llm=_DummyLLM())
        self.assertEqual(stats.get("tagged"), 1)
        meta = updated[0]["metadata"]
        self.assertEqual(meta.get("doc_type"), "sourcebook")
        self.assertIn("entities_json", meta)
        self.assertEqual(meta.get("summary_1s"), "A short summary.")
