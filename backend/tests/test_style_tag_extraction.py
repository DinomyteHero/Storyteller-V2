"""Tests for style tag extraction from style ingestion."""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from backend.app.rag.style_ingest import _extract_tags


class TestExtractTags:
    def test_empty_text(self):
        assert _extract_tags("") == []

    def test_single_tone_keyword(self):
        tags = _extract_tags("The scene has a dark atmosphere.")
        assert "dark" in tags

    def test_multiple_tone_keywords(self):
        tags = _extract_tags("A gritty, cinematic portrayal of war.")
        assert "gritty" in tags
        assert "cinematic" in tags

    def test_pacing_keyword(self):
        tags = _extract_tags("The narrative is fast-paced and thrilling.")
        assert "fast-paced" in tags

    def test_mixed_tone_and_pacing(self):
        tags = _extract_tags("An epic slow-burn tale with atmospheric world-building.")
        assert "epic" in tags
        assert "slow-burn" in tags
        assert "atmospheric" in tags

    def test_case_insensitive(self):
        tags = _extract_tags("DARK and GRITTY storytelling.")
        assert "dark" in tags
        assert "gritty" in tags

    def test_no_matching_keywords(self):
        tags = _extract_tags("The quick brown fox jumped over the lazy dog.")
        assert tags == []

    def test_returns_sorted_deduplicated(self):
        tags = _extract_tags("dark dark dark cinematic cinematic")
        assert tags == sorted(set(tags))
        assert len(tags) == 2

    def test_pulpy_keyword(self):
        tags = _extract_tags("A pulpy adventure in the outer rim.")
        assert "pulpy" in tags

    def test_dialogue_driven(self):
        tags = _extract_tags("The story is dialogue-driven with rich character interactions.")
        assert "dialogue-driven" in tags

    def test_tense_keyword(self):
        tags = _extract_tags("The tense standoff continued for hours.")
        assert "tense" in tags

    def test_suspenseful_keyword(self):
        tags = _extract_tags("A suspenseful thriller set in deep space.")
        assert "suspenseful" in tags

    def test_literary_keyword(self):
        tags = _extract_tags("A literary exploration of morality.")
        assert "literary" in tags
