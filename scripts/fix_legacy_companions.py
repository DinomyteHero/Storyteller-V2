#!/usr/bin/env python3
"""Fix LEGACY era companion schema to match V2.20 EraCompanion model.

Transformations:
1. personality_traits → traits dict (map to axis values)
2. banter_style → banter.style
3. recruitment_trigger → recruitment.unlock_conditions
4. special_abilities → preserve in metadata (or map to enables_affordances)
5. loyalty_progression, relationships, narrative_arc → metadata
6. Generate voice object from motivation + speech_quirk
7. Add default influence/banter configs
8. Validate voice_tags against VOICE_TAG_SPEECH_PATTERNS
"""
import sys
from pathlib import Path

import yaml

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from backend.app.world.era_pack_models import EraCompanion, EraCompanionVoice, EraCompanionInfluence, EraCompanionBanter, EraCompanionRecruitment
from backend.app.core.personality_profile import VOICE_TAG_SPEECH_PATTERNS


# Mapping invalid voice tags to valid ones
VOICE_TAG_FALLBACK_MAP = {
    "introspective": "measured",
    "conflicted": "uncertain",
    "patient": "measured",
    "precise": "clipped",
    "seductive": "smooth",
    "fanatical": "fierce",
    "intense": "fierce",
    "thoughtful": "measured",
    "mysterious": "mystical",
    "calm": "serene",
    "profound": "grave",
    "determined": "resolute",  # Not in allowed tags, but "grave" works
    "experienced": "grave",
    "confident": "clear",
    "protective": "warm",
    "surprisingly_earnest": "earnest",
    "otherworldly": "mystical",
    "cryptic": "mystical",
    "dangerous": "menacing",
    "businesslike": "professional",
    "occasionally_uncertain": "uncertain",
}


# Mapping from personality_traits to trait axes
TRAIT_AXIS_MAP = {
    # idealist_pragmatic axis (-100 = idealist, 100 = pragmatic)
    "idealistic": ("idealist_pragmatic", -60),
    "principled": ("idealist_pragmatic", -40),
    "pragmatic": ("idealist_pragmatic", 60),
    "calculating": ("idealist_pragmatic", 50),
    "analytical": ("idealist_pragmatic", 40),

    # merciful_ruthless axis (-100 = merciful, 100 = ruthless)
    "merciful": ("merciful_ruthless", -60),
    "compassionate": ("merciful_ruthless", -50),
    "ruthless": ("merciful_ruthless", 80),
    "cruel": ("merciful_ruthless", 90),
    "vengeful": ("merciful_ruthless", 70),

    # lawful_rebellious axis (-100 = lawful, 100 = rebellious)
    "honorable": ("lawful_rebellious", -60),
    "obedient": ("lawful_rebellious", -70),
    "disciplined": ("lawful_rebellious", -50),
    "rebellious": ("lawful_rebellious", 80),
    "independent": ("lawful_rebellious", 60),
    "defiant": ("lawful_rebellious", 70),

    # General positive/negative traits (map to reasonable defaults)
    "protective_of_party": ("merciful_ruthless", -30),
    "loyal": ("lawful_rebellious", -30),
    "wise": ("idealist_pragmatic", -20),
    "powerful": None,  # Not an axis trait
    "brilliant": ("idealist_pragmatic", 30),
    "remorseful": ("merciful_ruthless", -40),
    "sorrowful": None,
    "determined": None,
    "patient": None,
    "obsessive": None,
    "precise": ("idealist_pragmatic", 40),
    "honest": ("lawful_rebellious", -40),
    "challenging": None,
    "unapologetic": None,
    "philosophical": ("idealist_pragmatic", -30),
    "serene": None,
    "mysterious": None,
}


def generate_voice_object(motivation: str | None, speech_quirk: str | None) -> dict:
    """Generate a minimal EraCompanionVoice from motivation + speech_quirk."""
    # Extract first sentence from motivation as belief
    belief = ""
    if motivation:
        sentences = motivation.split(".")
        belief = sentences[0].strip() if sentences else motivation[:150]

    # Use speech_quirk as rhetorical_style hint (don't truncate)
    rhetorical_style = ""
    if speech_quirk:
        rhetorical_style = speech_quirk[:200]  # Allow longer descriptions

    return {
        "belief": belief or "Unknown belief",
        "wound": "",  # Not derivable from old data
        "taboo": "",  # Not derivable
        "rhetorical_style": rhetorical_style or "measured",
        "tell": "",  # Not derivable
    }


def map_traits_to_axes(personality_traits: list[str]) -> dict[str, int]:
    """Map personality_traits list to trait axes dict."""
    axes = {"idealist_pragmatic": 0, "merciful_ruthless": 0, "lawful_rebellious": 0}

    for trait in personality_traits or []:
        trait_lower = trait.strip().lower()
        if trait_lower in TRAIT_AXIS_MAP:
            mapping = TRAIT_AXIS_MAP[trait_lower]
            if mapping:
                axis, value = mapping
                # Average multiple values for same axis
                if axes[axis] != 0:
                    axes[axis] = (axes[axis] + value) // 2
                else:
                    axes[axis] = value

    return axes


def map_abilities_to_affordances(special_abilities: list[dict]) -> list[str]:
    """Map special_abilities to enables_affordances (best effort)."""
    affordances = []
    for ability in special_abilities or []:
        name = ability.get("name", "").lower()
        desc = ability.get("description", "").lower()

        # Pattern matching for common affordances
        if "heal" in name or "healing" in name:
            affordances.append("medic_heal")
        elif "dark side" in name or "sith" in name:
            affordances.append("dark_side_mastery")
        elif "force" in name:
            affordances.append("force_power")
        elif "slice" in desc or "hack" in desc:
            affordances.append("slice_terminal")
        elif "language" in name or "decrypt" in name:
            affordances.append("translate_ancient")
        elif "artifact" in desc or "archaeological" in name:
            affordances.append("identify_artifact")

    return list(set(affordances))  # Deduplicate


def validate_voice_tags(voice_tags: list[str]) -> tuple[list[str], list[str]]:
    """Validate voice_tags against VOICE_TAG_SPEECH_PATTERNS.

    Maps invalid tags to valid fallbacks where possible.
    Returns (valid_tags, invalid_tags)
    """
    valid = []
    invalid = []
    for tag in voice_tags or []:
        tag_lower = tag.strip().lower()
        if tag_lower in VOICE_TAG_SPEECH_PATTERNS:
            valid.append(tag_lower)
        elif tag_lower in VOICE_TAG_FALLBACK_MAP:
            # Map to valid fallback
            valid.append(VOICE_TAG_FALLBACK_MAP[tag_lower])
        else:
            invalid.append(tag)
    return valid, invalid


def fix_companion_schema(companion_data: dict) -> tuple[dict, list[str]]:
    """Transform a single companion to V2.20 schema.

    Returns (transformed_companion, warnings)
    """
    warnings = []

    # Validate and fix voice_tags
    if "voice_tags" in companion_data:
        original_tags = companion_data["voice_tags"][:]
        valid_tags, invalid_tags = validate_voice_tags(companion_data["voice_tags"])
        if invalid_tags:
            warnings.append(f"Invalid voice_tags: {invalid_tags} - removed")
        if len(valid_tags) != len(original_tags):
            # Some tags were mapped to fallbacks
            mapped = [t for t in valid_tags if t not in [x.lower() for x in original_tags]]
            if mapped:
                warnings.append(f"Mapped voice_tags to fallbacks: {mapped}")
        companion_data["voice_tags"] = valid_tags

    # Transform: personality_traits → traits
    if "personality_traits" in companion_data:
        personality_traits = companion_data.pop("personality_traits")
        companion_data["traits"] = map_traits_to_axes(personality_traits)

    # Transform: banter_style → banter.style
    banter_style = companion_data.pop("banter_style", None)
    companion_data["banter"] = {
        "frequency": "normal",
        "style": banter_style or "warm",
        "triggers": []
    }

    # Transform: recruitment_trigger → recruitment.unlock_conditions
    recruitment_trigger = companion_data.pop("recruitment_trigger", None)
    companion_data["recruitment"] = {
        "unlock_conditions": recruitment_trigger or "",
        "first_meeting_location": None,
        "first_scene_template": None
    }

    # Generate: voice object from motivation + speech_quirk
    companion_data["voice"] = generate_voice_object(
        companion_data.get("motivation"),
        companion_data.get("speech_quirk")
    )

    # Add: default influence config
    companion_data["influence"] = {
        "starts_at": 0,
        "min": -100,
        "max": 100,
        "triggers": []
    }

    # Transform: special_abilities → enables_affordances + metadata
    special_abilities = companion_data.pop("special_abilities", None)
    if special_abilities:
        companion_data["enables_affordances"] = map_abilities_to_affordances(special_abilities)
        # Preserve in metadata for reference
        if "metadata" not in companion_data:
            companion_data["metadata"] = {}
        companion_data["metadata"]["legacy_special_abilities"] = special_abilities

    # Preserve: loyalty_progression, relationships, narrative_arc in metadata
    if "metadata" not in companion_data:
        companion_data["metadata"] = {}

    for old_field in ["loyalty_progression", "relationships", "narrative_arc"]:
        if old_field in companion_data:
            companion_data["metadata"][f"legacy_{old_field}"] = companion_data.pop(old_field)

    return companion_data, warnings


def main(dry_run: bool = False):
    """Fix LEGACY companions.yaml."""
    legacy_dir = project_root / "data" / "static" / "era_packs" / "legacy"
    companions_path = legacy_dir / "companions.yaml"
    backup_path = legacy_dir / "companions.yaml.bak"

    if not companions_path.exists():
        print(f"ERROR: {companions_path} not found")
        return 1

    print(f"Reading {companions_path}...")
    with open(companions_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict) or "companions" not in data:
        print("ERROR: Invalid companions.yaml structure (expected 'companions' key)")
        return 1

    companions = data.get("companions", [])
    print(f"Found {len(companions)} companions")

    # Transform each companion
    transformed = []
    errors = []
    all_warnings = []
    for i, companion in enumerate(companions):
        try:
            # Apply transformations
            transformed_comp, warnings = fix_companion_schema(companion.copy())

            # Validate against Pydantic model
            validated = EraCompanion.model_validate(transformed_comp)
            transformed.append(validated.model_dump(mode="python", exclude_none=True))

            status = "Valid"
            if warnings:
                status = f"Valid (with {len(warnings)} warnings)"
                all_warnings.extend([(transformed_comp.get('id', f'comp_{i}'), w) for w in warnings])
            print(f"  [OK] {transformed_comp.get('id', f'comp_{i}')} - {status}")
        except Exception as e:
            errors.append((companion.get("id", f"comp_{i}"), str(e)))
            print(f"  [ERROR] {companion.get('id', f'comp_{i}')} - ERROR: {e}")

    if errors:
        print(f"\n[FAILED] {len(errors)} companion(s) failed validation:")
        for comp_id, error in errors:
            print(f"  - {comp_id}: {error}")
        return 1

    print(f"\n[SUCCESS] All {len(transformed)} companions validated successfully")

    if all_warnings:
        print(f"\n[WARNINGS] {len(all_warnings)} warning(s):")
        for comp_id, warning in all_warnings[:10]:  # Show first 10
            print(f"  - {comp_id}: {warning}")
        if len(all_warnings) > 10:
            print(f"  ... and {len(all_warnings) - 10} more warnings")

    if dry_run:
        print("\n[DRY RUN] No files modified")
        print("\nExample transformed companion:")
        import json
        print(json.dumps(transformed[0], indent=2))
        return 0

    # Backup original
    if not backup_path.exists():
        print(f"\n[BACKUP] Creating backup: {backup_path}")
        with open(backup_path, "w", encoding="utf-8") as f:
            with open(companions_path, "r", encoding="utf-8") as orig:
                f.write(orig.read())

    # Write transformed YAML
    print(f"\n[WRITE] Writing fixed companions to {companions_path}")
    output_data = {"companions": transformed}
    with open(companions_path, "w", encoding="utf-8") as f:
        yaml.dump(output_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print("[SUCCESS] LEGACY companions.yaml fixed successfully!")
    print(f"\n[SUMMARY]")
    print(f"   - Transformed {len(transformed)} companions to V2.20 schema")
    print(f"   - personality_traits -> traits dict")
    print(f"   - banter_style -> banter.style")
    print(f"   - recruitment_trigger -> recruitment.unlock_conditions")
    print(f"   - Generated voice objects from motivation + speech_quirk")
    print(f"   - special_abilities -> enables_affordances + metadata")
    print(f"   - Preserved old fields in metadata dict")
    print(f"   - Validated all voice_tags against VOICE_TAG_SPEECH_PATTERNS")

    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fix LEGACY era companion schema")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without modifying files")
    args = parser.parse_args()

    sys.exit(main(dry_run=args.dry_run))
