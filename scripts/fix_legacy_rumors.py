#!/usr/bin/env python3
"""Fix LEGACY era rumors schema to match V2.20 EraRumor model.

Old schema:
- id, name, category, reliability, content

New schema (V2.20):
- id, text, tags, scope, credibility

Transformations:
1. content → text
2. reliability (int 0-100) → credibility (rumor|likely|confirmed)
3. category → tags (convert to list)
4. Remove 'name' field
5. Add scope='global' default
"""
import sys
from pathlib import Path

import yaml

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from backend.app.world.era_pack_models import EraRumor


def map_reliability_to_credibility(reliability: int | None) -> str:
    """Map old reliability (0-100) to new credibility enum."""
    if reliability is None:
        return "rumor"
    if reliability >= 70:
        return "confirmed"
    elif reliability >= 40:
        return "likely"
    else:
        return "rumor"


def fix_rumor_schema(rumor_data: dict) -> dict:
    """Transform a single rumor to V2.20 schema."""
    # 1. content → text
    if "content" in rumor_data:
        rumor_data["text"] = rumor_data.pop("content")

    # 2. reliability → credibility
    if "reliability" in rumor_data:
        reliability = rumor_data.pop("reliability")
        rumor_data["credibility"] = map_reliability_to_credibility(reliability)

    # 3. category → tags
    tags = []
    if "category" in rumor_data:
        category = rumor_data.pop("category")
        if category:
            # Convert category to lowercase tag
            tags.append(category.lower().replace(" ", "_"))
    rumor_data["tags"] = tags

    # 4. Remove 'name' field
    rumor_data.pop("name", None)

    # 5. Add scope default
    if "scope" not in rumor_data:
        rumor_data["scope"] = "global"

    return rumor_data


def main(dry_run: bool = False):
    """Fix LEGACY rumors.yaml."""
    legacy_dir = project_root / "data" / "static" / "era_packs" / "legacy"
    rumors_path = legacy_dir / "rumors.yaml"
    backup_path = legacy_dir / "rumors.yaml.bak"

    if not rumors_path.exists():
        print(f"ERROR: {rumors_path} not found")
        return 1

    print(f"Reading {rumors_path}...")
    with open(rumors_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict) or "rumors" not in data:
        print("ERROR: Invalid rumors.yaml structure (expected 'rumors' key)")
        return 1

    rumors = data.get("rumors", [])
    print(f"Found {len(rumors)} rumors")

    # Transform each rumor
    transformed = []
    errors = []
    for i, rumor in enumerate(rumors):
        try:
            # Apply transformations
            transformed_rumor = fix_rumor_schema(rumor.copy())

            # Validate against Pydantic model
            validated = EraRumor.model_validate(transformed_rumor)
            transformed.append(validated.model_dump(mode="python", exclude_none=True))
            print(f"  [OK] {transformed_rumor.get('id', f'rumor_{i}')} - Valid")
        except Exception as e:
            errors.append((rumor.get("id", f"rumor_{i}"), str(e)))
            print(f"  [ERROR] {rumor.get('id', f'rumor_{i}')} - ERROR: {e}")

    if errors:
        print(f"\n[FAILED] {len(errors)} rumor(s) failed validation:")
        for rumor_id, error in errors:
            print(f"  - {rumor_id}: {error}")
        return 1

    print(f"\n[SUCCESS] All {len(transformed)} rumors validated successfully")

    if dry_run:
        print("\n[DRY RUN] No files modified")
        print("\nExample transformed rumor:")
        import json
        print(json.dumps(transformed[0], indent=2))
        return 0

    # Backup original
    if not backup_path.exists():
        print(f"\n[BACKUP] Creating backup: {backup_path}")
        with open(backup_path, "w", encoding="utf-8") as f:
            with open(rumors_path, "r", encoding="utf-8") as orig:
                f.write(orig.read())

    # Write transformed YAML
    print(f"\n[WRITE] Writing fixed rumors to {rumors_path}")
    output_data = {"rumors": transformed}
    with open(rumors_path, "w", encoding="utf-8") as f:
        yaml.dump(output_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print("[SUCCESS] LEGACY rumors.yaml fixed successfully!")
    print(f"\n[SUMMARY]")
    print(f"   - Renamed 'content' to 'text' in {len(transformed)} rumors")
    print(f"   - Mapped 'reliability' to 'credibility' (rumor|likely|confirmed)")
    print(f"   - Converted 'category' to 'tags' list")
    print(f"   - Removed 'name' field")
    print(f"   - Added 'scope' default")

    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fix LEGACY era rumor schema")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without modifying files")
    args = parser.parse_args()

    sys.exit(main(dry_run=args.dry_run))
