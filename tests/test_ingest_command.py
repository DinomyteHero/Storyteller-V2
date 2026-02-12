"""Unit tests for storyteller ingest command return-code behavior."""
from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from storyteller.commands import ingest as ingest_cmd


def _args(tmp_path, pipeline: str) -> SimpleNamespace:
    return SimpleNamespace(
        pipeline=pipeline,
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
        allow_legacy=False,
    )


def test_run_propagates_lore_pipeline_exit_code():
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "sample.txt").write_text("lore input")
        args = _args(tmp, pipeline="lore")
        with patch.object(ingest_cmd, "_run_lore", return_value=7):
            assert ingest_cmd.run(args) == 7


def test_run_propagates_simple_pipeline_exit_code():
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "sample.txt").write_text("simple input")
        args = _args(tmp, pipeline="simple")
        args.allow_legacy = True
        with patch.object(ingest_cmd, "_run_simple", return_value=3):
            assert ingest_cmd.run(args) == 3

def test_run_uses_ingest_root_defaults_when_input_and_db_omitted(tmp_path):
    ingest_root = tmp_path / "portable_ingest"
    lore_dir = ingest_root / "lore"
    lore_dir.mkdir(parents=True)
    (lore_dir / "sample.txt").write_text("portable lore")

    args = _args(lore_dir, pipeline="simple")
    args.allow_legacy = True
    args.input = None
    args.out_db = None
    args.ingest_root = str(ingest_root)

    seen = {}

    def _fake_simple(passed_args):
        seen["input"] = passed_args._resolved_input
        seen["db"] = passed_args._resolved_out_db
        return 0

    with patch.object(ingest_cmd, "_run_simple", side_effect=_fake_simple):
        assert ingest_cmd.run(args) == 0

    assert seen["input"] == str(lore_dir.resolve())
    assert seen["db"] == str((ingest_root / "lancedb").resolve())


def test_simple_pipeline_requires_allow_legacy(tmp_path):
    (tmp_path / "sample.txt").write_text("simple input")
    args = _args(tmp_path, pipeline="simple")
    args.allow_legacy = False
    assert ingest_cmd.run(args) == 1


def test_simple_pipeline_allowed_with_flag(tmp_path):
    (tmp_path / "sample.txt").write_text("simple input")
    args = _args(tmp_path, pipeline="simple")
    args.allow_legacy = True
    with patch.object(ingest_cmd, "_run_simple", return_value=0):
        assert ingest_cmd.run(args) == 0
