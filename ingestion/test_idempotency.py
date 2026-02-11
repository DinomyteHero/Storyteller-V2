"""Tests for ingestion idempotency, stable chunk IDs, and deduplication."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure project root on path
_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Use dummy embeddings for tests (fast, no model download)
os.environ["STORYTELLER_DUMMY_EMBEDDINGS"] = "1"

from ingestion.store import stable_chunk_id, file_doc_id, LanceStore


@pytest.fixture
def tmp_dir() -> Path:
    """Replacement for pytest's tmp_path in restricted environments."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


class TestStableChunkId:
    """Tests for stable_chunk_id determinism."""

    def test_same_input_same_id(self):
        id1 = stable_chunk_id("hello world", source="test.txt", chunk_index=0)
        id2 = stable_chunk_id("hello world", source="test.txt", chunk_index=0)
        assert id1 == id2

    def test_different_text_different_id(self):
        id1 = stable_chunk_id("hello world", source="test.txt", chunk_index=0)
        id2 = stable_chunk_id("hello mars", source="test.txt", chunk_index=0)
        assert id1 != id2

    def test_different_source_different_id(self):
        id1 = stable_chunk_id("hello world", source="test.txt", chunk_index=0)
        id2 = stable_chunk_id("hello world", source="other.txt", chunk_index=0)
        assert id1 != id2

    def test_different_index_different_id(self):
        id1 = stable_chunk_id("hello world", source="test.txt", chunk_index=0)
        id2 = stable_chunk_id("hello world", source="test.txt", chunk_index=1)
        assert id1 != id2

    def test_id_is_hex_string(self):
        cid = stable_chunk_id("text", source="src", chunk_index=0)
        assert isinstance(cid, str)
        assert len(cid) == 16
        int(cid, 16)  # should not raise


class TestLanceStoreDedup:
    """Tests for deduplication in LanceStore.add_chunks."""

    def _make_store(self, tmp_dir: Path) -> LanceStore:
        return LanceStore(str(tmp_dir / "test_lance"))

    def _make_chunk(self, text: str, chunk_id: str) -> dict:
        return {
            "text": text,
            "metadata": {
                "chunk_id": chunk_id,
                "era": "test",
                "time_period": "test",
                "source_type": "test",
                "book_title": "test",
                "chapter_title": "",
                "chapter_index": 0,
                "chunk_index": 0,
                "doc_type": "test",
                "section_kind": "general",
                "characters": [],
            },
        }

    def test_add_chunks_returns_counts(self, tmp_dir):
        store = self._make_store(tmp_dir)
        cid = stable_chunk_id("test text", source="test", chunk_index=0)
        chunks = [self._make_chunk("test text", cid)]
        result = store.add_chunks(chunks)
        assert result["added"] == 1
        assert result["skipped"] == 0

    def test_dedup_skips_existing(self, tmp_dir):
        store = self._make_store(tmp_dir)
        cid = stable_chunk_id("test text", source="test", chunk_index=0)
        chunks = [self._make_chunk("test text", cid)]

        # First add
        r1 = store.add_chunks(chunks)
        assert r1["added"] == 1

        # Second add should skip
        r2 = store.add_chunks(chunks)
        assert r2["added"] == 0
        assert r2["skipped"] == 1

    def test_dedup_allows_new_chunks(self, tmp_dir):
        store = self._make_store(tmp_dir)
        cid1 = stable_chunk_id("text one", source="test", chunk_index=0)
        cid2 = stable_chunk_id("text two", source="test", chunk_index=1)

        r1 = store.add_chunks([self._make_chunk("text one", cid1)])
        assert r1["added"] == 1

        # Add both - one existing, one new
        r2 = store.add_chunks([
            self._make_chunk("text one", cid1),
            self._make_chunk("text two", cid2),
        ])
        assert r2["added"] == 1
        assert r2["skipped"] == 1

    def test_dedup_disabled(self, tmp_dir):
        store = self._make_store(tmp_dir)
        cid = stable_chunk_id("test text", source="test", chunk_index=0)
        chunks = [self._make_chunk("test text", cid)]

        store.add_chunks(chunks)
        r2 = store.add_chunks(chunks, dedupe=False)
        # With dedupe disabled, should add even duplicates
        assert r2["added"] == 1
        assert r2["skipped"] == 0

    def test_empty_chunks(self, tmp_dir):
        store = self._make_store(tmp_dir)
        result = store.add_chunks([])
        assert result["added"] == 0
        assert result["skipped"] == 0


class TestCrossDocCollision:
    """Same chunk text across different documents must not collide."""

    def test_same_text_different_doc_id(self):
        """Identical text in different docs produces different IDs."""
        boilerplate = "Copyright 2025 All rights reserved."
        id_a = stable_chunk_id(boilerplate, source="book_a.epub", chunk_index=0, doc_id="book_a")
        id_b = stable_chunk_id(boilerplate, source="book_b.epub", chunk_index=0, doc_id="book_b")
        assert id_a != id_b

    def test_same_text_same_doc_different_position(self):
        """Repeated text at different positions in the same doc produces different IDs."""
        repeated = "Chapter break."
        id_0 = stable_chunk_id(repeated, source="novel.txt", chunk_index=0, doc_id="novel")
        id_5 = stable_chunk_id(repeated, source="novel.txt", chunk_index=5, doc_id="novel")
        assert id_0 != id_5

    def test_backward_compat_no_doc_id(self):
        """Omitting doc_id still produces a stable deterministic ID."""
        id1 = stable_chunk_id("text", source="s", chunk_index=0)
        id2 = stable_chunk_id("text", source="s", chunk_index=0)
        assert id1 == id2


class TestDedupDoesNotFullScan:
    """Structural test: dedup uses local cache, not full table scan."""

    def _make_store(self, tmp_dir):
        return LanceStore(str(tmp_dir / "test_lance"))

    def test_id_cache_populated_after_add(self, tmp_dir):
        store = self._make_store(tmp_dir)
        cid = stable_chunk_id("hello", source="a", chunk_index=0)
        chunk = {
            "text": "hello",
            "metadata": {
                "chunk_id": cid, "era": "", "time_period": "", "source_type": "",
                "book_title": "", "chapter_title": "", "chapter_index": 0,
                "chunk_index": 0, "doc_type": "", "section_kind": "general",
                "characters": [],
            },
        }
        store.add_chunks([chunk])
        # The local cache should now contain the ID
        assert store._id_cache is not None
        assert cid in store._id_cache

    def test_existing_ids_for_returns_subset(self, tmp_dir):
        store = self._make_store(tmp_dir)
        cid = stable_chunk_id("data", source="b", chunk_index=0)
        chunk = {
            "text": "data",
            "metadata": {
                "chunk_id": cid, "era": "", "time_period": "", "source_type": "",
                "book_title": "", "chapter_title": "", "chapter_index": 0,
                "chunk_index": 0, "doc_type": "", "section_kind": "general",
                "characters": [],
            },
        }
        store.add_chunks([chunk])
        found = store._existing_ids_for({cid, "nonexistent"})
        assert cid in found
        assert "nonexistent" not in found


class TestPdfSkipInSimpleIngest:
    """Test that simple ingest correctly skips PDF files."""

    def test_pdf_returns_empty(self, tmp_dir):
        from ingestion.ingest import ingest_file
        pdf_file = tmp_dir / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake content")
        result = ingest_file(pdf_file, era="test", source_type="test")
        assert result == []


class TestFileDocIdPortability:
    """file_doc_id should be stable, portable, and collision-resistant."""

    def test_relative_path_gives_same_id_regardless_of_root_location(self, tmp_dir):
        """Two trees with identical relative layout produce identical doc_ids."""
        root_a = tmp_dir / "tree_a" / "data"
        root_b = tmp_dir / "tree_b" / "data"
        root_a.mkdir(parents=True)
        root_b.mkdir(parents=True)
        content = b"Hello world"
        (root_a / "book.txt").write_bytes(content)
        (root_b / "book.txt").write_bytes(content)

        id_a = file_doc_id(root_a / "book.txt", input_dir=root_a)
        id_b = file_doc_id(root_b / "book.txt", input_dir=root_b)
        assert id_a == id_b

    def test_different_content_different_id(self, tmp_dir):
        """Same relative path but different file size produces different IDs."""
        root = tmp_dir / "data"
        root.mkdir()
        f = root / "book.txt"
        f.write_bytes(b"short")
        id1 = file_doc_id(f, input_dir=root)
        f.write_bytes(b"much longer content here that changes the size")
        id2 = file_doc_id(f, input_dir=root)
        assert id1 != id2

    def test_different_relative_path_different_id(self, tmp_dir):
        """Different filenames in same root produce different IDs."""
        root = tmp_dir / "data"
        root.mkdir()
        (root / "a.txt").write_bytes(b"same")
        (root / "b.txt").write_bytes(b"same")
        id_a = file_doc_id(root / "a.txt", input_dir=root)
        id_b = file_doc_id(root / "b.txt", input_dir=root)
        assert id_a != id_b

    def test_subfolder_layout_preserved(self, tmp_dir):
        """Subfolder structure is part of the ID."""
        root = tmp_dir / "data"
        (root / "sub").mkdir(parents=True)
        root.mkdir(exist_ok=True)
        (root / "book.txt").write_bytes(b"x")
        (root / "sub" / "book.txt").write_bytes(b"x")
        id_top = file_doc_id(root / "book.txt", input_dir=root)
        id_sub = file_doc_id(root / "sub" / "book.txt", input_dir=root)
        assert id_top != id_sub

    def test_no_input_dir_falls_back_to_absolute(self, tmp_dir):
        """Without input_dir, file_doc_id still returns a valid hex ID."""
        f = tmp_dir / "book.txt"
        f.write_bytes(b"content")
        did = file_doc_id(f)
        assert isinstance(did, str)
        assert len(did) == 16
        int(did, 16)  # valid hex

    def test_deterministic_across_calls(self, tmp_dir):
        """Same args produce same ID every time."""
        root = tmp_dir / "data"
        root.mkdir()
        (root / "f.txt").write_bytes(b"stable")
        id1 = file_doc_id(root / "f.txt", input_dir=root)
        id2 = file_doc_id(root / "f.txt", input_dir=root)
        assert id1 == id2
