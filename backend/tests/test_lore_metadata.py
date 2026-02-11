"""Tests for lore chunk metadata: ingestion, retrieval, backward compat."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure project root on path
_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import lancedb
import pyarrow as pa

from backend.app.rag.lore_retriever import retrieve_lore
from shared.lore_metadata import DOC_TYPE_NOVEL, SECTION_KIND_LORE, default_section_kind

TABLE_NAME = "lore_chunks"
VECTOR_DIM = 384


class _DummyEncoder:
    def encode(self, texts, show_progress_bar: bool = False):
        return [_Vec([0.0] * VECTOR_DIM) for _ in texts]


class _Vec(list):
    def tolist(self):
        return list(self)


def _make_encoder():
    return _DummyEncoder()


def _vec_to_list(vec):
    return vec.tolist() if hasattr(vec, "tolist") else list(vec)


def _make_old_schema_db(tmp_path: str, num_chunks: int = 2) -> None:
    """Create DB with OLD schema (no doc_type, section_kind, characters_json)."""
    db = lancedb.connect(tmp_path)
    schema = pa.schema([
        pa.field("id", pa.string()),
        pa.field("vector", pa.list_(pa.float32(), VECTOR_DIM)),
        pa.field("text", pa.string()),
        pa.field("era", pa.string()),
        pa.field("source_type", pa.string()),
        pa.field("book_title", pa.string()),
        pa.field("chapter_title", pa.string()),
        pa.field("chapter_index", pa.int32()),
        pa.field("chunk_id", pa.string()),
        pa.field("chunk_index", pa.int32()),
    ])
    table = db.create_table(TABLE_NAME, schema=schema, mode="overwrite")
    enc = _make_encoder()
    texts = ["Old schema chunk one.", "Old schema chunk two."][:num_chunks]
    vecs = enc.encode(texts, show_progress_bar=False)
    rows = []
    for i, (text, vec) in enumerate(zip(texts, vecs)):
        rows.append({
            "id": f"old_{i}",
            "vector": _vec_to_list(vec),
            "text": text,
            "era": "LOTF",
            "source_type": "novel",
            "book_title": "Old Book",
            "chapter_title": "Ch1",
            "chapter_index": 0,
            "chunk_id": f"old_{i}",
            "chunk_index": i,
        })
    table.add(rows)


def _make_new_schema_db(tmp_path: str, num_chunks: int = 3) -> None:
    """Create DB with NEW schema (doc_type, section_kind, characters_json)."""
    db = lancedb.connect(tmp_path)
    schema = pa.schema([
        pa.field("id", pa.string()),
        pa.field("vector", pa.list_(pa.float32(), VECTOR_DIM)),
        pa.field("text", pa.string()),
        pa.field("era", pa.string()),
        pa.field("time_period", pa.string()),
        pa.field("source_type", pa.string()),
        pa.field("book_title", pa.string()),
        pa.field("chapter_title", pa.string()),
        pa.field("chapter_index", pa.int32()),
        pa.field("chunk_id", pa.string()),
        pa.field("chunk_index", pa.int32()),
        pa.field("doc_type", pa.string()),
        pa.field("section_kind", pa.string()),
        pa.field("characters_json", pa.string()),
    ])
    table = db.create_table(TABLE_NAME, schema=schema, mode="overwrite")
    enc = _make_encoder()
    texts = [
        "Luke Skywalker trained new students on Tatooine.",
        "The Jedi Council met on Coruscant.",
        "Leia Organa negotiated with the Rebellion.",
    ][:num_chunks]
    vecs = enc.encode(texts, show_progress_bar=False)
    rows = []
    for i, (text, vec) in enumerate(zip(texts, vecs)):
        chars = ["Luke Skywalker", "Leia Organa"][: (i + 1)] if i < 2 else []
        rows.append({
            "id": f"new_{i}",
            "vector": _vec_to_list(vec),
            "text": text,
            "era": "LOTF",
            "time_period": "LOTF",
            "source_type": "novel",
            "book_title": "New Book",
            "chapter_title": "Ch1",
            "chapter_index": 0,
            "chunk_id": f"new_{i}",
            "chunk_index": i,
            "doc_type": DOC_TYPE_NOVEL if i < 2 else "sourcebook",
            "section_kind": SECTION_KIND_LORE if i < 2 else "rules",
            "characters_json": json.dumps(chars),
        })
    table.add(rows)


class TestLoreMetadataRetrieval(unittest.TestCase):
    """Test lore_retriever with new metadata and backward compat."""

    def test_retrieval_works_when_filters_missing(self) -> None:
        """Retrieval returns results when no filters are passed."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_new_schema_db(tmp, num_chunks=2)
            chunks = retrieve_lore("Jedi training", top_k=5, db_path=tmp)
            self.assertGreaterEqual(len(chunks), 1)
            c = chunks[0]
            self.assertIn("text", c)
            self.assertIn("metadata", c)
            self.assertIn("score", c)
            self.assertEqual(c["metadata"]["doc_type"], DOC_TYPE_NOVEL)
            self.assertEqual(c["metadata"]["section_kind"], SECTION_KIND_LORE)

    def test_retrieval_filter_by_doc_type(self) -> None:
        """Filtering by doc_type returns only matching chunks."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_new_schema_db(tmp, num_chunks=3)
            chunks = retrieve_lore("Council", top_k=5, doc_type=DOC_TYPE_NOVEL, db_path=tmp)
            self.assertGreaterEqual(len(chunks), 1)
            for c in chunks:
                self.assertEqual(c["metadata"]["doc_type"], DOC_TYPE_NOVEL)

    def test_retrieval_filter_by_section_kind(self) -> None:
        """Filtering by section_kind returns only matching chunks."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_new_schema_db(tmp, num_chunks=3)
            chunks = retrieve_lore("rules", top_k=5, section_kind="rules", db_path=tmp)
            self.assertGreaterEqual(len(chunks), 1)
            for c in chunks:
                self.assertEqual(c["metadata"]["section_kind"], "rules")

    def test_retrieval_filter_by_characters(self) -> None:
        """Filtering by characters (contains-match) returns matching chunks."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_new_schema_db(tmp, num_chunks=3)
            chunks = retrieve_lore("Leia", top_k=5, characters="Leia Organa", db_path=tmp)
            self.assertGreaterEqual(len(chunks), 1)
            for c in chunks:
                self.assertIn("Leia Organa", c["metadata"]["characters"])

    def test_old_db_no_crash(self) -> None:
        """Querying old DB without new columns does not crash."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_old_schema_db(tmp, num_chunks=2)
            chunks = retrieve_lore("schema", top_k=5, db_path=tmp)
            self.assertGreaterEqual(len(chunks), 1)
            c = chunks[0]
            self.assertIn("text", c)
            self.assertIn("metadata", c)
            self.assertEqual(c["metadata"].get("doc_type", ""), "")
            self.assertEqual(c["metadata"].get("section_kind", ""), "")
            self.assertEqual(c["metadata"].get("characters", []), [])


class TestLoreMetadataIngestion(unittest.TestCase):
    """Test that ingestion produces chunk rows with new metadata fields."""

    def test_lance_store_add_chunks_includes_new_fields(self) -> None:
        """LanceStore.add_chunks produces rows with doc_type, section_kind, characters_json."""
        from ingestion.store import LanceStore

        with tempfile.TemporaryDirectory() as tmp:
            store = LanceStore(tmp)
            chunks = [
                {
                    "text": "Test chunk content.",
                    "metadata": {
                        "era": "LOTF",
                        "time_period": "LOTF",
                        "source_type": "novel",
                        "book_title": "Test",
                        "chapter_title": "Ch1",
                        "chapter_index": 0,
                        "chunk_id": "c1",
                        "chunk_index": 0,
                        "doc_type": "novel",
                        "section_kind": "lore",
                        "characters": ["Luke"],
                    },
                },
            ]
            store.add_chunks(chunks)
            db = lancedb.connect(tmp)
            tbl = db.open_table("lore_chunks")
            arr = tbl.to_arrow()
            self.assertEqual(arr.num_rows, 1)
            d = arr.to_pydict()
            self.assertEqual(d["doc_type"][0], "novel")
            self.assertEqual(d["section_kind"][0], "lore")
            self.assertIn("characters_json", d)
            parsed = json.loads(d["characters_json"][0])
            self.assertEqual(parsed, ["Luke"])

    def test_ingest_produces_default_metadata(self) -> None:
        """ingest.py produces chunks with default doc_type/section_kind when not set."""
        from ingestion.ingest import ingest_txt
        from ingestion.store import LanceStore

        with tempfile.TemporaryDirectory() as tmp:
            txt_path = Path(tmp) / "sample.txt"
            txt_path.write_text("Short sample text for ingestion.")
            chunks = ingest_txt(txt_path, era="LOTF", source_type="novel")
            self.assertGreaterEqual(len(chunks), 1)
            m = chunks[0]["metadata"]
            self.assertEqual(m["doc_type"], "novel")  # inferred from source_type
            self.assertEqual(m["section_kind"], default_section_kind())  # default unknown
            self.assertEqual(m["characters"], [])
