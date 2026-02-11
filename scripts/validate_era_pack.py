#!/usr/bin/env python3
"""Validate all Era Pack YAML files with Pydantic models."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.world.era_pack_loader import load_all_era_packs


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate Era Pack YAML files.")
    ap.add_argument("--dir", type=str, default=None, help="Era pack directory (default: ERA_PACK_DIR)")
    args = ap.parse_args()

    pack_dir = Path(args.dir) if args.dir else None
    try:
        packs = load_all_era_packs(pack_dir)
    except Exception as e:
        print(f"ERROR: {e}")
        return 1
    if not packs:
        print("No era packs found to validate.")
        return 1
    print(f"Validated {len(packs)} era pack(s).")
    for p in packs:
        print(f"  - {p.era_id}: {len(p.factions)} factions, {len(p.locations)} locations, "
              f"{len(p.npcs.anchors)} anchors, {len(p.npcs.rotating)} rotating, {len(p.npcs.templates)} templates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
