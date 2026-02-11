#!/usr/bin/env python3
"""Validate setting packs after stacking/merging with legacy-era fallback."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.content.loader import default_setting_id, normalize_key, resolve_pack_roots
from backend.app.content.repository import CONTENT_REPOSITORY


def _discover_targets() -> list[tuple[str, str]]:
    targets: set[tuple[str, str]] = set()
    for root in resolve_pack_roots():
        if not root.exists() or not root.is_dir():
            continue
        for setting_dir in root.iterdir():
            periods_dir = setting_dir / "periods"
            if not setting_dir.is_dir() or not periods_dir.exists() or not periods_dir.is_dir():
                continue
            for period_dir in periods_dir.iterdir():
                if period_dir.is_dir():
                    targets.add((normalize_key(setting_dir.name), normalize_key(period_dir.name)))

    if targets:
        return sorted(targets)

    legacy_root = ROOT / os.environ.get("ERA_PACK_DIR", "./data/static/era_packs")
    if legacy_root.exists() and legacy_root.is_dir():
        for d in legacy_root.iterdir():
            if d.is_dir():
                targets.add((default_setting_id(), normalize_key(d.name)))
    return sorted(targets)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate setting packs")
    parser.add_argument("--paths", type=str, default=None, help="Semicolon-separated SETTING_PACK_PATHS override")
    args = parser.parse_args()

    if args.paths:
        os.environ["SETTING_PACK_PATHS"] = args.paths

    targets = _discover_targets()
    if not targets:
        print("No setting/period packs found to validate.")
        return 1

    failures = 0
    for setting_id, period_id in targets:
        try:
            pack = CONTENT_REPOSITORY.get_content(setting_id, period_id)
            CONTENT_REPOSITORY.get_indices(setting_id, period_id)
            print(
                f"OK  {setting_id}/{period_id}: "
                f"locations={len(pack.locations)} npcs={len(pack.npcs.anchors)+len(pack.npcs.rotating)} quests={len(pack.quests)}"
            )
        except Exception as exc:
            failures += 1
            print(f"ERR {setting_id}/{period_id}: {exc}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
