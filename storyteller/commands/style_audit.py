"""`storyteller style-audit` — inspect active vs orphan style assets."""
from __future__ import annotations

from pathlib import Path

from backend.app.rag.style_mappings import (
    ARCHETYPE_STYLE_MAP,
    BASE_STYLE_MAP,
    ERA_STYLE_MAP,
    GENRE_STYLE_MAP,
)
from backend.app.config import STYLE_DATA_DIR

_SKIP_STEMS = {"PROMPT_TEMPLATE", "README"}


def _all_style_files(style_root: Path) -> list[Path]:
    return sorted(p for p in style_root.rglob("*.md") if p.is_file())


def _mapped_source_stems() -> set[str]:
    return set(BASE_STYLE_MAP) | set(ERA_STYLE_MAP) | set(GENRE_STYLE_MAP) | set(ARCHETYPE_STYLE_MAP)


def register(subparsers) -> None:
    p = subparsers.add_parser("style-audit", help="Audit style assets (active mappings vs orphan files)")
    p.add_argument("--style-dir", type=str, default=str(STYLE_DATA_DIR), help="Style root dir (default: STYLE_DATA_DIR)")
    p.set_defaults(func=run)


def run(args) -> int:
    style_root = Path(args.style_dir).expanduser().resolve()
    if not style_root.is_dir():
        print(f"ERROR: style dir not found: {style_root}")
        return 1

    files = _all_style_files(style_root)
    mapped = _mapped_source_stems()

    active: list[Path] = []
    templates: list[Path] = []
    orphan: list[Path] = []

    for f in files:
        stem = f.stem
        if stem in _SKIP_STEMS:
            templates.append(f)
        elif stem in mapped:
            active.append(f)
        else:
            orphan.append(f)

    print(f"Style root: {style_root}")
    print(f"Mapped stems: {len(mapped)}")
    print(f"Active files: {len(active)}")
    print(f"Template/ignored files: {len(templates)}")
    print(f"Orphan files: {len(orphan)}")

    if active:
        print("\nActive style files:")
        for f in active:
            print(f"  - {f.relative_to(style_root)}")

    if templates:
        print("\nTemplate/ignored files (not ingested):")
        for f in templates:
            print(f"  - {f.relative_to(style_root)}")

    if orphan:
        print("\nOrphan files (not referenced by style mappings):")
        for f in orphan:
            print(f"  - {f.relative_to(style_root)}")
        print("\nRecommendation: remove/move orphan files or add explicit mapping.")
        return 2

    print("\nNo orphan style files found. base/era/genre are active in current layered retrieval.")
    return 0
