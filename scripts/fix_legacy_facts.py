#!/usr/bin/env python3
"""Fix LEGACY era facts schema to match V2.20 EraFact model.

Old schema:
- id, name, category, content

New schema (V2.20):
- id, subject, predicate, object, confidence (optional)

Transformations:
1. Extract subject/predicate/object from 'name' field (best effort)
2. Remove 'name', 'category', 'content' fields
3. Add confidence=0.8 default
"""
import sys
import re
from pathlib import Path

import yaml

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from backend.app.world.era_pack_models import EraFact


def parse_fact_from_name(name: str, content: str) -> tuple[str, str, str]:
    """Parse subject/predicate/object from fact name and content.

    Returns (subject, predicate, object)

    Strategy:
    1. Extract subject from name (strip "The", clean possessives)
    2. Determine predicate from name or content
    3. Extract object from first sentence of content (cleaned)
    """
    # Clean subject extraction from name
    subject = ""
    predicate = ""
    obj = ""

    # Remove articles and clean the name for subject
    subject_candidate = name.strip()
    # Remove leading "The "
    if subject_candidate.lower().startswith("the "):
        subject_candidate = subject_candidate[4:]

    # Extract subject from possessive patterns ("X's Y" -> use X)
    possessive_match = re.match(r"(.+?)'s\s+(.+)", subject_candidate, re.IGNORECASE)
    if possessive_match:
        subject = possessive_match.group(1).strip()
        # Use the possessed thing as part of object
        obj_hint = possessive_match.group(2).strip()
    else:
        # Try to extract subject before a verb
        verb_patterns = [
            (r"(.+?)\s+(is|are|was|were)\s+(.+)", "is"),
            (r"(.+?)\s+(has|have|had)\s+(.+)", "has"),
            (r"(.+?)\s+(remains?|stays?)\s+(.+)", "remains"),
            (r"(.+?)\s+(contains?|holds?)\s+(.+)", "contains"),
            (r"(.+?)\s+(can|could|may|might)\s+(.+)", "can"),
            (r"(.+?)\s+(predates?|precedes?)\s+(.+)", "predates"),
            (r"(.+?)\s+(survives?|endures?)\s+(.+)", "survives"),
            (r"(.+?)\s+(refuses?|rejects?)\s+(.+)", "refuses"),
            (r"(.+?)\s+(profits?|benefits?)\s+(.+)", "profits"),
            (r"(.+?)\s+(creates?|generates?)\s+(.+)", "creates"),
            (r"(.+?)\s+(possesses?|shows?)\s+(.+)", "possesses"),
        ]

        matched = False
        for pattern, verb in verb_patterns:
            match = re.match(pattern, subject_candidate, re.IGNORECASE)
            if match:
                subject = match.group(1).strip()
                predicate = verb
                obj_hint = match.group(3).strip()
                matched = True
                break

        if not matched:
            # Fallback: use first major phrase from name as subject
            subject = subject_candidate.split(":")[0].strip() if ":" in subject_candidate else subject_candidate
            predicate = "is"

    # Extract object from content's first sentence (more informative than name)
    if content:
        # Get first sentence
        first_sentence = content.split(".")[0].strip()
        # Remove the subject if it appears at start
        if first_sentence.lower().startswith(subject.lower()):
            remaining = first_sentence[len(subject):].strip()
            # Remove verb at start
            for v in ["is", "are", "was", "were", "has", "have", "had", "can", "could", "remains", "contains"]:
                if remaining.lower().startswith(v + " "):
                    remaining = remaining[len(v)+1:].strip()
                    if not predicate:
                        predicate = v
                    break
            obj = remaining if remaining else first_sentence
        else:
            obj = first_sentence

        # Limit object length but not too short
        if len(obj) > 200:
            obj = obj[:197] + "..."

    # Final fallback if we couldn't extract
    if not obj:
        obj = obj_hint if 'obj_hint' in locals() else "unknown"

    if not predicate:
        predicate = "is"

    if not subject:
        subject = "Unknown Entity"

    return (subject, predicate, obj)


def fix_fact_schema(fact_data: dict) -> dict:
    """Transform a single fact to V2.20 schema."""
    name = fact_data.get("name", "")
    content = fact_data.get("content", "")

    # Parse subject/predicate/object
    subject, predicate, obj = parse_fact_from_name(name, content)

    # Build new schema
    new_fact = {
        "id": fact_data.get("id", ""),
        "subject": subject,
        "predicate": predicate,
        "object": obj,
        "confidence": 0.8  # Default confidence
    }

    return new_fact


def main(dry_run: bool = False):
    """Fix LEGACY facts.yaml."""
    legacy_dir = project_root / "data" / "static" / "era_packs" / "legacy"
    facts_path = legacy_dir / "facts.yaml"
    backup_path = legacy_dir / "facts.yaml.bak"

    if not facts_path.exists():
        print(f"ERROR: {facts_path} not found")
        return 1

    print(f"Reading {facts_path}...")
    with open(facts_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict) or "facts" not in data:
        print("ERROR: Invalid facts.yaml structure (expected 'facts' key)")
        return 1

    facts = data.get("facts", [])
    print(f"Found {len(facts)} facts")

    # Transform each fact
    transformed = []
    errors = []
    for i, fact in enumerate(facts):
        try:
            # Apply transformations
            transformed_fact = fix_fact_schema(fact)

            # Validate against Pydantic model
            validated = EraFact.model_validate(transformed_fact)
            transformed.append(validated.model_dump(mode="python", exclude_none=True))
            print(f"  [OK] {transformed_fact.get('id', f'fact_{i}')} - Valid")
        except Exception as e:
            errors.append((fact.get("id", f"fact_{i}"), str(e)))
            print(f"  [ERROR] {fact.get('id', f'fact_{i}')} - ERROR: {e}")

    if errors:
        print(f"\n[FAILED] {len(errors)} fact(s) failed validation:")
        for fact_id, error in errors:
            print(f"  - {fact_id}: {error}")
        return 1

    print(f"\n[SUCCESS] All {len(transformed)} facts validated successfully")

    if dry_run:
        print("\n[DRY RUN] No files modified")
        print("\nExample transformed fact:")
        import json
        print(json.dumps(transformed[0], indent=2))
        return 0

    # Backup original
    if not backup_path.exists():
        print(f"\n[BACKUP] Creating backup: {backup_path}")
        with open(backup_path, "w", encoding="utf-8") as f:
            with open(facts_path, "r", encoding="utf-8") as orig:
                f.write(orig.read())

    # Write transformed YAML
    print(f"\n[WRITE] Writing fixed facts to {facts_path}")
    output_data = {"facts": transformed}
    with open(facts_path, "w", encoding="utf-8") as f:
        yaml.dump(output_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print("[SUCCESS] LEGACY facts.yaml fixed successfully!")
    print(f"\n[SUMMARY]")
    print(f"   - Parsed subject/predicate/object from {len(transformed)} facts")
    print(f"   - Removed 'name', 'category', 'content' fields")
    print(f"   - Added confidence=0.8 default")
    print(f"\n[WARNING] Subject/predicate/object parsing is best-effort.")
    print(f"   Review facts.yaml to ensure semantic correctness.")

    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fix LEGACY era fact schema")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without modifying files")
    args = parser.parse_args()

    sys.exit(main(dry_run=args.dry_run))
