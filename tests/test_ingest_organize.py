from __future__ import annotations

from ingestion.organize import organize_documents


def test_organize_documents_dry_run(tmp_path):
    src = tmp_path / "raw"
    src.mkdir()
    (src / "Heir to the Empire.txt").write_text("Chapter 1\nHan said... Leia asked...")

    out = tmp_path / "organized"
    results = organize_documents(input_dir=src, output_dir=out, dry_run=True)

    assert len(results) == 1
    assert results[0].source.name == "Heir to the Empire.txt"
    assert "organized" in str(results[0].destination)
    assert not out.exists()


def test_organize_documents_copy_mode(tmp_path):
    src = tmp_path / "raw"
    src.mkdir()
    file = src / "sourcebook_reference.txt"
    file.write_text("Equipment:\nBlaster")

    out = tmp_path / "organized"
    results = organize_documents(input_dir=src, output_dir=out, dry_run=False, copy_mode=True)

    assert len(results) == 1
    assert file.exists()
    assert results[0].destination.exists()
