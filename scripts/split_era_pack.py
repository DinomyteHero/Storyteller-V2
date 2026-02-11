#!/usr/bin/env python3
"""Split a monolithic Era Pack YAML file into a folder-per-era modular layout.

This is a convenience tool for migrating legacy `data/static/era_packs/<era>.yaml`
files into:

  data/static/era_packs/<era_key>/
    era.yaml
    factions.yaml
    locations.yaml
    npcs.yaml
    namebanks.yaml

The loader supports both layouts; directory packs take precedence when both exist.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


def _write_yaml(path: Path, data: object) -> None:
    path.write_text(
        yaml.safe_dump(
            data,
            sort_keys=False,
            allow_unicode=True,
            width=120,
        ),
        encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Split an Era Pack YAML file into a modular folder.")
    ap.add_argument("--input", type=str, required=True, help="Input era pack YAML file (legacy).")
    ap.add_argument("--output-dir", type=str, required=True, help="Output directory for modular pack files.")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing files in output-dir.")
    args = ap.parse_args()

    in_path = Path(args.input)
    out_dir = Path(args.output_dir)
    if not in_path.exists():
        print(f"ERROR: input does not exist: {in_path}")
        return 2
    data = yaml.safe_load(in_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        print("ERROR: input YAML must be a dict at top-level.")
        return 2

    out_dir.mkdir(parents=True, exist_ok=True)
    targets = [
        out_dir / "era.yaml",
        out_dir / "factions.yaml",
        out_dir / "locations.yaml",
        out_dir / "npcs.yaml",
        out_dir / "namebanks.yaml",
    ]
    if not args.overwrite:
        existing = [p for p in targets if p.exists()]
        if existing:
            print("ERROR: output files already exist (pass --overwrite to replace):")
            for p in existing:
                print(f"  - {p}")
            return 2

    era_id = data.get("era_id")
    style_ref = data.get("style_ref")
    _write_yaml(out_dir / "era.yaml", {"era_id": era_id, "style_ref": style_ref})
    _write_yaml(out_dir / "factions.yaml", {"factions": data.get("factions") or []})
    _write_yaml(out_dir / "locations.yaml", {"locations": data.get("locations") or []})
    _write_yaml(out_dir / "npcs.yaml", {"npcs": data.get("npcs") or {}})
    _write_yaml(out_dir / "namebanks.yaml", {"namebanks": data.get("namebanks") or {}})

    print(f"Wrote modular era pack: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

