#!/usr/bin/env python3
"""Fix LEGACY era quest schema to match V2.20 EraQuest model.

Transformations:
1. Rename 'name' → 'title' at quest level
2. Rename 'stage' → 'stage_id' in all quest stages
3. Validate against EraQuest Pydantic model
"""
import sys
from pathlib import Path

import yaml

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from backend.app.world.era_pack_models import EraQuest


def fix_quest_schema(quest_data: dict) -> dict:
    """Transform a single quest to V2.20 schema."""
    # 1. Rename 'name' → 'title'
    if "name" in quest_data:
        quest_data["title"] = quest_data.pop("name")

    # 2. Rename 'stage' → 'stage_id' in all stages
    if "stages" in quest_data:
        for stage in quest_data["stages"]:
            if "stage" in stage:
                stage["stage_id"] = stage.pop("stage")

    return quest_data


def main(dry_run: bool = False):
    """Fix LEGACY quests.yaml."""
    legacy_dir = project_root / "data" / "static" / "era_packs" / "legacy"
    quests_path = legacy_dir / "quests.yaml"
    backup_path = legacy_dir / "quests.yaml.bak"

    if not quests_path.exists():
        print(f"ERROR: {quests_path} not found")
        return 1

    print(f"Reading {quests_path}...")
    with open(quests_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict) or "quests" not in data:
        print("ERROR: Invalid quests.yaml structure (expected 'quests' key)")
        return 1

    quests = data.get("quests", [])
    print(f"Found {len(quests)} quests")

    # Transform each quest
    transformed = []
    errors = []
    for i, quest in enumerate(quests):
        try:
            # Apply transformations
            transformed_quest = fix_quest_schema(quest.copy())

            # Validate against Pydantic model
            validated = EraQuest.model_validate(transformed_quest)
            transformed.append(validated.model_dump(mode="python", exclude_none=True))
            print(f"  [OK] {transformed_quest.get('id', f'quest_{i}')} - Valid")
        except Exception as e:
            errors.append((quest.get("id", f"quest_{i}"), str(e)))
            print(f"  [ERROR] {quest.get('id', f'quest_{i}')} - ERROR: {e}")

    if errors:
        print(f"\n[FAILED] {len(errors)} quest(s) failed validation:")
        for quest_id, error in errors:
            print(f"  - {quest_id}: {error}")
        return 1

    print(f"\n[SUCCESS] All {len(transformed)} quests validated successfully")

    if dry_run:
        print("\n[DRY RUN] No files modified")
        print("\nExample transformed quest:")
        import json
        print(json.dumps(transformed[0], indent=2))
        return 0

    # Backup original
    if not backup_path.exists():
        print(f"\n[BACKUP] Creating backup: {backup_path}")
        with open(backup_path, "w", encoding="utf-8") as f:
            with open(quests_path, "r", encoding="utf-8") as orig:
                f.write(orig.read())

    # Write transformed YAML
    print(f"\n[WRITE] Writing fixed quests to {quests_path}")
    output_data = {"quests": transformed}
    with open(quests_path, "w", encoding="utf-8") as f:
        yaml.dump(output_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print("[SUCCESS] LEGACY quests.yaml fixed successfully!")
    print(f"\n[SUMMARY]")
    print(f"   - Renamed 'name' to 'title' in {len(transformed)} quests")
    print(f"   - Renamed 'stage' to 'stage_id' in all stages")
    print(f"   - Validated against EraQuest Pydantic model")

    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fix LEGACY era quest schema")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without modifying files")
    args = parser.parse_args()

    sys.exit(main(dry_run=args.dry_run))
