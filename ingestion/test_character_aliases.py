"""Unit tests for character alias extraction."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from ingestion.character_aliases import extract_characters, reload_aliases


class TestCharacterAliases(unittest.TestCase):
    """Test extract_characters with word-boundary and fallback behavior."""

    def setUp(self) -> None:
        reload_aliases()

    def test_luke_matches_luke_skywalker(self) -> None:
        """'Luke' in text should produce luke_skywalker."""
        result = extract_characters("Luke spoke to the council.")
        self.assertIn("luke_skywalker", result)

    def test_lukewarm_does_not_match(self) -> None:
        """'Lukewarm' should NOT match Luke (word boundary)."""
        result = extract_characters("The water was lukewarm.")
        self.assertNotIn("luke_skywalker", result)

    def test_luke_skywalker_full_name_matches(self) -> None:
        """'Luke Skywalker' should match luke_skywalker."""
        result = extract_characters("Luke Skywalker trained the students.")
        self.assertIn("luke_skywalker", result)

    def test_master_skywalker_matches(self) -> None:
        """'Master Skywalker' should match luke_skywalker."""
        result = extract_characters("Master Skywalker entered the room.")
        self.assertIn("luke_skywalker", result)

    def test_leia_matches_leia_organa(self) -> None:
        """'Leia' should produce leia_organa."""
        result = extract_characters("Leia negotiated with the Rebels.")
        self.assertIn("leia_organa", result)

    def test_case_insensitive(self) -> None:
        """Matching is case-insensitive."""
        result = extract_characters("LUKE was there.")
        self.assertIn("luke_skywalker", result)

    def test_empty_text_returns_empty(self) -> None:
        """Empty or whitespace-only text returns []."""
        self.assertEqual(extract_characters(""), [])
        self.assertEqual(extract_characters("   "), [])

    def test_missing_alias_file_returns_empty(self) -> None:
        """If alias file is missing, returns [] (no guess)."""
        prev = os.environ.get("CHARACTER_ALIASES_PATH")
        try:
            os.environ["CHARACTER_ALIASES_PATH"] = str(Path(__file__).parent / "nonexistent_aliases_xyz.yml")
            reload_aliases()
            result = extract_characters("Luke was here.")
            self.assertEqual(result, [])
        finally:
            if prev is not None:
                os.environ["CHARACTER_ALIASES_PATH"] = prev
            else:
                os.environ.pop("CHARACTER_ALIASES_PATH", None)
            reload_aliases()

    def test_custom_alias_file_via_env(self) -> None:
        """CHARACTER_ALIASES_PATH overrides default path."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write("""
han_solo:
  - "Han"
  - "Han Solo"
""")
            path = f.name
        try:
            prev = os.environ.get("CHARACTER_ALIASES_PATH")
            os.environ["CHARACTER_ALIASES_PATH"] = path
            reload_aliases()
            result = extract_characters("Han Solo flew the Falcon.")
            self.assertIn("han_solo", result)
        finally:
            os.unlink(path)
            if prev is not None:
                os.environ["CHARACTER_ALIASES_PATH"] = prev
            else:
                os.environ.pop("CHARACTER_ALIASES_PATH", None)
            reload_aliases()

    def test_ingestion_chunk_gets_empty_characters_metadata(self) -> None:
        """Ingestion produces chunks with empty characters[] (facets feature removed)."""
        from ingestion import ingest as ingest_module

        with tempfile.TemporaryDirectory() as tmp:
            txt = Path(tmp) / "test.txt"
            txt.write_text("Luke met Leia in the corridor. Lukewarm tea was served.")
            chunks = ingest_module.ingest_txt(txt, era="LOTF", source_type="novel")
            self.assertGreaterEqual(len(chunks), 1)
            m = chunks[0]["metadata"]
            # Character facets feature removed - characters[] is always empty
            self.assertEqual(m["characters"], [])
