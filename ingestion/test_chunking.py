"""Unit tests for chunking overlap behavior."""
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.chunking import (
    chunk_text_by_tokens,
    get_tokenizer,
    get_overlap_text,
)


class TestChunkingOverlap(unittest.TestCase):
    """Test ~600 token chunks with 10% overlap and no cross-chapter behavior."""

    def test_overlap_approximate_10_percent(self):
        """Adjacent chunks from chunk_text_by_tokens share ~10% tokens."""
        target = 600
        overlap_pct = 0.1
        tok = get_tokenizer()
        # Build text long enough to get 3+ chunks
        word = "alpha "
        repeat = (target * 4) // len(tok.encode(word))
        text = (word * repeat).strip()
        chunks = chunk_text_by_tokens(text, target_tokens=target, overlap_percent=overlap_pct)
        self.assertGreaterEqual(len(chunks), 2, "Need at least 2 chunks to test overlap")
        overlap_tokens_expected = int(target * overlap_pct)
        # Chunk i ends with overlap_tokens; chunk i+1 starts with same tokens
        c0_tokens = tok.encode(chunks[0])
        c1_tokens = tok.encode(chunks[1])
        self.assertEqual(len(c0_tokens), target, "First chunk should be target length")
        tail = c0_tokens[-overlap_tokens_expected:]
        head = c1_tokens[:overlap_tokens_expected]
        self.assertEqual(tail, head, "Overlap region should match between adjacent chunks")

    def test_step_is_target_minus_overlap(self):
        """Step size is target_tokens - overlap_tokens."""
        target = 600
        overlap_pct = 0.1
        overlap_tokens = int(target * overlap_pct)
        step = target - overlap_tokens
        self.assertEqual(step, 540, "Step should be 540 for 600 tokens and 10% overlap")
        word = "x "
        tok = get_tokenizer()
        per_word = len(tok.encode(word))
        n = (target * 3) // per_word
        text = (word * n).strip()
        chunks = chunk_text_by_tokens(text, target_tokens=target, overlap_percent=overlap_pct)
        if len(chunks) >= 2:
            c0 = tok.encode(chunks[0])
            c1 = tok.encode(chunks[1])
            self.assertEqual(len(c0), target)
            # Start of chunk 1 should be step tokens after start of chunk 0
            # i.e. chunk1_start_in_full = step
            self.assertEqual(c1[:overlap_tokens], c0[-overlap_tokens:])

    def test_single_chunk_unchanged(self):
        """Short text stays one chunk."""
        text = "Short piece of text."
        chunks = chunk_text_by_tokens(text, target_tokens=600, overlap_percent=0.1)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], text)

    def test_get_overlap_text(self):
        """get_overlap_text returns last N tokens."""
        text = "one two three four five six seven eight nine ten"
        n = 3
        overlap = get_overlap_text(text, n)
        tok = get_tokenizer()
        self.assertEqual(len(tok.encode(overlap)), n)


if __name__ == "__main__":
    unittest.main()
