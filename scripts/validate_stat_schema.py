#!/usr/bin/env python3
"""Validate that era pack backgrounds only use stats defined in their stat_schema.

Phase 5: Multi-universe validation script.

Checks:
1. All era packs with a rule_system_id have a corresponding stat_schema file.
2. Background starting_stats and choice effect stat_bonus keys are valid stat IDs.
3. Reports any mismatches (stat name used in background but not in schema).

Usage::

    python scripts/validate_stat_schema.py
    python scripts/validate_stat_schema.py --pack-id forgotten_realms
    python scripts/validate_stat_schema.py --strict  # exit 1 on any mismatch
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Add repo root to path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def validate_era_pack_stats(pack_id: str) -> list[str]:
    """Validate stat references in an era pack against its stat schema.

    Returns:
        List of error strings. Empty list means the pack is valid.
    """
    errors: list[str] = []

    try:
        from backend.app.content.repository import CONTENT_REPOSITORY
        pack = CONTENT_REPOSITORY.get_pack(pack_id)
    except Exception as e:
        return [f"[{pack_id}] Failed to load era pack: {e}"]

    if pack is None:
        return [f"[{pack_id}] Era pack not found"]

    rule_system_id = getattr(pack.setting_rules, "rule_system_id", None)
    if not rule_system_id:
        logger.info("[%s] No rule_system_id — skipping stat schema validation", pack_id)
        return []

    # Load stat schema
    try:
        from backend.app.world.stat_schema_loader import load_stat_schema, get_stat_ids
        schema = load_stat_schema(rule_system_id)
        valid_stat_ids = set(get_stat_ids(rule_system_id))
        logger.info("[%s] Stat schema '%s' loaded: %d stats", pack_id, rule_system_id, len(valid_stat_ids))
    except FileNotFoundError as e:
        return [f"[{pack_id}] Stat schema '{rule_system_id}' not found: {e}"]
    except Exception as e:
        return [f"[{pack_id}] Failed to load stat schema '{rule_system_id}': {e}"]

    # Validate background starting_stats
    for bg in pack.backgrounds or []:
        bg_id = bg.id
        for stat_name, _val in (bg.starting_stats or {}).items():
            if stat_name not in valid_stat_ids:
                errors.append(
                    f"[{pack_id}] background[{bg_id}].starting_stats has unknown stat: '{stat_name}' "
                    f"(valid: {sorted(valid_stat_ids)})"
                )

        # Validate choice effect stat_bonus
        for question in (bg.questions or []):
            for choice in (question.choices or []):
                effects = choice.effects if hasattr(choice, "effects") else {}
                if not effects:
                    continue
                stat_bonus = (
                    effects.stat_bonus if hasattr(effects, "stat_bonus")
                    else (effects.get("stat_bonus") if isinstance(effects, dict) else {})
                ) or {}
                for stat_name in stat_bonus:
                    if stat_name not in valid_stat_ids:
                        errors.append(
                            f"[{pack_id}] background[{bg_id}].questions[{question.id}]"
                            f".choices[{choice.label}].effects.stat_bonus has unknown stat: '{stat_name}' "
                            f"(valid: {sorted(valid_stat_ids)})"
                        )

    return errors


def discover_pack_ids() -> list[str]:
    """Discover all available era pack IDs."""
    try:
        from backend.app.content.repository import CONTENT_REPOSITORY
        catalog = CONTENT_REPOSITORY.list_catalog()
        period_ids = list({row.get("period_id", "") for row in catalog if row.get("period_id")})
        if period_ids:
            return period_ids
    except Exception:
        pass

    # Fallback: scan era_packs directory
    era_packs_dir = _ROOT / "data" / "static" / "era_packs"
    if not era_packs_dir.exists():
        return []
    return [d.name for d in era_packs_dir.iterdir() if d.is_dir() and not d.name.startswith("_")]


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate era pack stat schema references.")
    ap.add_argument("--pack-id", type=str, default="", help="Validate a specific pack ID only")
    ap.add_argument("--strict", action="store_true", help="Exit 1 on any validation error")
    args = ap.parse_args()

    if args.pack_id:
        pack_ids = [args.pack_id]
    else:
        pack_ids = discover_pack_ids()

    if not pack_ids:
        logger.warning("No era packs found to validate")
        return 0

    logger.info("Validating stat schemas for %d era packs: %s", len(pack_ids), pack_ids)

    all_errors: list[str] = []
    for pack_id in sorted(pack_ids):
        errors = validate_era_pack_stats(pack_id)
        if errors:
            for err in errors:
                logger.error(err)
            all_errors.extend(errors)
        else:
            logger.info("[%s] Stat schema validation: OK", pack_id)

    if all_errors:
        logger.error("Validation FAILED: %d errors found", len(all_errors))
        if args.strict:
            return 1
    else:
        logger.info("All era packs passed stat schema validation.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
