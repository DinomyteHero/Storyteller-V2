from __future__ import annotations

from ingestion.style_pack_builder import build_style_pack


def test_build_style_pack_dry_run(tmp_path):
    src = tmp_path / "corpus"
    src.mkdir()
    (src / "novel1.txt").write_text("Chapter 1\nThe senate debated while fleets gathered.")
    (src / "novel2.txt").write_text("A bounty hunter tracked clues in a shadowy cantina alley.")

    out = tmp_path / "style"
    docs = build_style_pack(input_dir=src, output_dir=out, dry_run=True)

    assert len(docs) >= 2
    assert not out.exists()


def test_build_style_pack_writes_manifest(tmp_path):
    src = tmp_path / "corpus"
    src.mkdir()
    (src / "book.txt").write_text("Chapter 1\nA tactical squad moved under command.")

    out = tmp_path / "style"
    docs = build_style_pack(input_dir=src, output_dir=out, dry_run=False)

    assert docs
    assert (out / "_style_pack_manifest.json").exists()
