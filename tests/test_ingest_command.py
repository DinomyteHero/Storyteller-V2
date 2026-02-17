"""Unit tests for storyteller ingest command return-code behavior."""
from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from storyteller.commands import ingest as ingest_cmd


def _args(tmp_path) -> SimpleNamespace:
    return SimpleNamespace(
        input=str(tmp_path),
        era=None,
        source_type=None,
        planet=None,
        faction=None,
        collection=None,
        book_title=None,
        out_db="./data/lancedb",
        era_pack=None,
        tag_npcs=None,
        npc_tagging_mode=None,
        skip_checks=True,
        ingest_root=None,
        no_venv=True,
        yes=False,
    )


def test_run_propagates_lore_pipeline_exit_code():
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "sample.txt").write_text("lore input")
        args = _args(tmp)
        with patch.object(ingest_cmd, "_run_lore", return_value=7):
            assert ingest_cmd.run(args) == 7
