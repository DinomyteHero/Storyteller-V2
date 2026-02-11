#!/usr/bin/env python3
"""Audit era pack data quality and generate a fix report."""

import sys
import yaml
from pathlib import Path
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.app.world.era_pack_loader import load_era_pack
from backend.app.world.era_pack_models import ALLOWED_SCENE_TYPES, ALLOWED_BYPASS_METHODS


def audit_yaml_syntax(era_dir: Path) -> list[dict]:
    """Check for YAML syntax errors (duplicate anchors, parsing failures)."""
    issues = []
    for yaml_file in era_dir.glob("*.yaml"):
        try:
            with open(yaml_file, 'r', encoding='utf-8') as f:
                yaml.safe_load(f)
        except yaml.YAMLError as e:
            issues.append({
                "file": yaml_file.name,
                "type": "YAML_SYNTAX_ERROR",
                "message": str(e)
            })
    return issues


def audit_era_pack_loading(era_id: str, era_dir: Path) -> dict:
    """Attempt to load era pack and capture validation errors."""
    result = {
        "era_id": era_id,
        "yaml_syntax_issues": audit_yaml_syntax(era_dir),
        "load_success": False,
        "validation_errors": [],
        "backgrounds_count": 0,
        "locations_count": 0,
    }

    try:
        pack = load_era_pack(era_id)
        result["load_success"] = True
        result["backgrounds_count"] = len(pack.backgrounds or [])
        result["locations_count"] = len(pack.locations or [])
    except Exception as e:
        result["validation_errors"].append({
            "type": type(e).__name__,
            "message": str(e)[:500]
        })

    return result


def main():
    era_packs_dir = project_root / "data" / "static" / "era_packs"

    # Find all era pack directories
    era_dirs = [d for d in era_packs_dir.iterdir() if d.is_dir() and (d / "era.yaml").exists()]

    print("=" * 80)
    print("ERA PACK DATA QUALITY AUDIT")
    print("=" * 80)

    all_results = []
    for era_dir in sorted(era_dirs):
        era_id = era_dir.name.upper()
        print(f"\n### {era_id} ({era_dir.name})")

        result = audit_era_pack_loading(era_id, era_dir)
        all_results.append(result)

        # Print YAML syntax issues
        if result["yaml_syntax_issues"]:
            print(f"  [X] YAML Syntax Errors: {len(result['yaml_syntax_issues'])}")
            for issue in result["yaml_syntax_issues"]:
                print(f"    - {issue['file']}: {issue['message'][:100]}")
        else:
            print(f"  [OK] YAML syntax valid")

        # Print load status
        if result["load_success"]:
            print(f"  [OK] Loaded successfully")
            print(f"    - Backgrounds: {result['backgrounds_count']}")
            print(f"    - Locations: {result['locations_count']}")
        else:
            print(f"  [X] Failed to load")
            for err in result["validation_errors"]:
                print(f"    - {err['type']}: {err['message'][:100]}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    total = len(all_results)
    successful = sum(1 for r in all_results if r["load_success"])
    yaml_errors = sum(1 for r in all_results if r["yaml_syntax_issues"])

    print(f"Total era packs: {total}")
    print(f"Successfully loaded: {successful}/{total}")
    print(f"YAML syntax errors: {yaml_errors}")
    print(f"Validation failures: {total - successful}")

    # Priority fixes
    print("\n" + "=" * 80)
    print("PRIORITY FIXES")
    print("=" * 80)

    for result in all_results:
        if result["yaml_syntax_issues"]:
            print(f"\n{result['era_id']}: Fix YAML syntax errors first")
            for issue in result["yaml_syntax_issues"]:
                print(f"  - {issue['file']}: {issue['message'][:200]}")
        elif not result["load_success"]:
            print(f"\n{result['era_id']}: Fix validation errors")
            for err in result["validation_errors"]:
                print(f"  - {err['type']}: {err['message'][:200]}")


if __name__ == "__main__":
    main()
