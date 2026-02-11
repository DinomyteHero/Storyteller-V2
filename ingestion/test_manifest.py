"""Tests for ingestion manifest writing."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from ingestion.manifest import write_run_manifest


class TestIngestionManifest(unittest.TestCase):
    def test_manifest_written_with_required_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_env = os.environ.get("MANIFESTS_DIR")
            os.environ["MANIFESTS_DIR"] = tmp
            try:
                manifest_path = write_run_manifest(
                    run_type="lore",
                    input_files=[{"path": "file.txt", "sha256": "abc"}],
                    chunking={"target_tokens": 600, "overlap_percent": 0.1},
                    embedding_model="test-embed",
                    embedding_dim=384,
                    tagger_enabled=True,
                    tagger_model="test-tagger",
                    output_table="lore_chunks",
                    vectordb_path="./data/lancedb",
                    counts={"chunks": 10, "failed": 1},
                )
                self.assertTrue(manifest_path.exists())
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                for key in (
                    "run_id",
                    "input_files",
                    "chunking",
                    "embedding",
                    "tagger",
                    "output",
                    "counts",
                ):
                    self.assertIn(key, payload)
                self.assertIn("model", payload["embedding"])
                self.assertIn("dimension", payload["embedding"])
                self.assertIn("enabled", payload["tagger"])
                self.assertIn("model", payload["tagger"])
                self.assertIn("table_name", payload["output"])
                self.assertIn("vectordb_path", payload["output"])
                self.assertIn("chunks", payload["counts"])
                self.assertIn("failed", payload["counts"])
            finally:
                if old_env is None:
                    os.environ.pop("MANIFESTS_DIR", None)
                else:
                    os.environ["MANIFESTS_DIR"] = old_env
