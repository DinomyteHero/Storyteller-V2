#!/usr/bin/env python3
"""Enrich legacy era pack YAML files to Era Pack v2 (dynamic adventure metadata).

Goals:
- Idempotent: running twice produces identical output.
- Deterministic ordering: stable encounter_table sorting and YAML formatting.
- Safe: default writes to *_v2.yaml; optional --in-place writes backups first.

This script intentionally does NOT attempt to preserve YAML comments (PyYAML limitation).
Use it primarily for data files like locations.yaml / npcs.yaml, not prose-heavy era.yaml.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml


ROOT = Path(__file__).resolve().parents[1]


ALLOWED_SCENE_TYPES = {"dialogue", "stealth", "combat", "travel", "investigation"}
ALLOWED_PATROL = {"low", "medium", "high"}
ALLOWED_SERVICES = {
    "briefing_room",
    "medbay",
    "arms_dealer",
    "slicer",
    "transport",
    "bounty_board",
    "safehouse",
}
ALLOWED_LEVER = {"low", "medium", "high", "false"}


def _read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _write_yaml(path: Path, data: Any) -> None:
    path.write_text(
        yaml.safe_dump(
            data,
            sort_keys=False,
            allow_unicode=True,
            width=120,
        ),
        encoding="utf-8",
    )


def _coerce_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _clamp_int(x: Any, lo: int, hi: int, default: int) -> int:
    try:
        v = int(x)
    except Exception:
        v = default
    return max(lo, min(hi, v))


def _infer_scene_types(tags: set[str]) -> list[str]:
    out: list[str] = []
    if tags & {"cantina", "social", "market", "marketplace", "bazaar", "crowded"}:
        out.extend(["dialogue", "investigation"])
    if tags & {"underworld", "criminal", "smuggler", "hideout"}:
        out.extend(["dialogue", "stealth"])
    if tags & {"checkpoint", "garrison", "military", "hostile", "warship", "fortress"}:
        out.extend(["combat", "stealth"])
    if tags & {"spaceport", "hangar", "docks", "cargo", "transport", "travel"}:
        out.append("travel")
    if not out:
        out = ["dialogue", "investigation"]
    # Dedup while preserving order + filter to allowed
    seen: set[str] = set()
    final: list[str] = []
    for t in out:
        t = str(t).lower().strip()
        if t not in ALLOWED_SCENE_TYPES:
            continue
        if t in seen:
            continue
        seen.add(t)
        final.append(t)
    return final


def _infer_security_level(threat_level: str | None) -> int:
    t = (threat_level or "").strip().lower()
    if t in {"low"}:
        return 20
    if t in {"moderate", "medium"}:
        return 50
    if t in {"high"}:
        return 75
    if t in {"extreme"}:
        return 90
    return 50


def _bucket_intensity(security_level: int) -> str:
    if security_level >= 80:
        return "high"
    if security_level >= 45:
        return "medium"
    return "low"


def _infer_services(tags: set[str]) -> list[str]:
    out: list[str] = []
    if tags & {"base", "command"}:
        out.append("briefing_room")
    if tags & {"base", "hospital", "medbay"}:
        out.append("medbay")
    if tags & {"underworld", "criminal", "trade", "market", "marketplace", "bazaar"}:
        out.append("arms_dealer")
        out.append("bounty_board")
    if tags & {"underworld", "criminal", "slicer", "tech"}:
        out.append("slicer")
    if tags & {"spaceport", "hangar", "docks", "transport", "mobile"}:
        out.append("transport")
    if tags & {"safe", "hidden", "safehouse", "rebel"}:
        out.append("safehouse")
    # Dedup + filter
    seen: set[str] = set()
    final: list[str] = []
    for s in out:
        s = str(s).strip()
        if s not in ALLOWED_SERVICES:
            continue
        if s in seen:
            continue
        seen.add(s)
        final.append(s)
    return final


def _infer_keywords(loc: dict) -> list[str]:
    tags = [str(t).strip() for t in _coerce_list(loc.get("tags")) if str(t).strip()]
    extras: list[str] = []
    for k in ("region", "planet", "threat_level"):
        v = loc.get(k)
        if isinstance(v, str) and v.strip():
            extras.append(v.strip())
    out = tags + extras
    # Dedup, stable order
    seen: set[str] = set()
    final: list[str] = []
    for w in out:
        low = w.lower()
        if low in seen:
            continue
        seen.add(low)
        final.append(w)
    return final[:16]


def _score_template_for_location(
    template: dict,
    *,
    location_tags: set[str],
    controlling_factions: set[str],
) -> int:
    tags = set(str(t).strip().lower() for t in _coerce_list(template.get("tags")))
    score = len(tags & set(t.lower() for t in location_tags))
    # Mild boost if template tags include a controlling faction id
    if controlling_factions and (tags & set(f.lower() for f in controlling_factions)):
        score += 2
    return score


def _generate_encounter_table(
    *,
    location_tags: set[str],
    controlling_factions: set[str],
    npc_templates: list[dict],
    limit: int = 8,
) -> list[dict]:
    scored: list[tuple[int, str, dict]] = []
    for t in npc_templates:
        if not isinstance(t, dict):
            continue
        tid = str(t.get("id") or "").strip()
        if not tid:
            continue
        score = _score_template_for_location(
            t,
            location_tags=location_tags,
            controlling_factions=controlling_factions,
        )
        if score <= 0:
            continue
        scored.append((score, tid, t))
    scored.sort(key=lambda x: (-x[0], x[1]))
    out: list[dict] = []
    for score, tid, _t in scored[:limit]:
        out.append({"template_id": tid, "weight": int(score)})
    return out


def _default_levers(tags: set[str]) -> dict[str, Any]:
    # Conservative defaults; avoid over-authoring.
    bribeable: str = "false"
    intimidatable: str = "false"
    charmable: str = "false"
    if tags & {"underworld", "criminal", "smuggler", "fixer"}:
        bribeable = "medium"
    if tags & {"guard", "enforcer", "officer", "imperial", "stormtrooper"}:
        intimidatable = "medium"
    if tags & {"diplomat", "charismatic", "leader"}:
        charmable = "high"
    return {
        "bribeable": bribeable,
        "intimidatable": intimidatable,
        "charmable": charmable,
    }


def _normalize_lever(value: Any) -> str:
    raw = str(value).strip().lower()
    return raw if raw in ALLOWED_LEVER else "false"


def _enrich_location(loc: dict, npc_templates: list[dict]) -> tuple[dict, list[str]]:
    manual: list[str] = []
    tags = set(str(t).strip() for t in _coerce_list(loc.get("tags")))
    controlling_factions = set(str(x).strip() for x in _coerce_list(loc.get("controlling_factions")))

    loc.setdefault("parent_id", None)
    loc.setdefault("scene_types", _infer_scene_types(tags))

    security = _as_dict(loc.get("security"))
    if not security:
        security = {}
    controlling_faction = security.get("controlling_faction")
    if not controlling_faction and controlling_factions:
        controlling_faction = next(iter(controlling_factions))
    security_level = security.get("security_level")
    if security_level is None:
        security_level = _infer_security_level(str(loc.get("threat_level") or "").strip())
    security_level = _clamp_int(security_level, 0, 100, 50)
    security.setdefault("controlling_faction", controlling_faction)
    security["security_level"] = security_level
    security.setdefault("patrol_intensity", _bucket_intensity(security_level))
    security.setdefault("inspection_chance", _bucket_intensity(security_level))
    # Normalize enums
    if str(security.get("patrol_intensity")).lower() not in ALLOWED_PATROL:
        security["patrol_intensity"] = _bucket_intensity(security_level)
    if str(security.get("inspection_chance")).lower() not in ALLOWED_PATROL:
        security["inspection_chance"] = _bucket_intensity(security_level)
    loc["security"] = security

    loc.setdefault("services", _infer_services(tags))
    loc.setdefault("access_points", [])
    if not _coerce_list(loc.get("access_points")):
        manual.append(f"locations.{loc.get('id')}.access_points")

    if "encounter_table" not in loc or not isinstance(loc.get("encounter_table"), list) or not loc.get("encounter_table"):
        loc["encounter_table"] = _generate_encounter_table(
            location_tags=set(t.lower() for t in tags),
            controlling_factions=set(f.lower() for f in controlling_factions),
            npc_templates=npc_templates,
        )
    if not loc.get("encounter_table"):
        manual.append(f"locations.{loc.get('id')}.encounter_table")

    loc.setdefault("keywords", _infer_keywords(loc))
    loc.setdefault("travel_links", [])
    if not _coerce_list(loc.get("travel_links")):
        manual.append(f"locations.{loc.get('id')}.travel_links")
    return loc, manual


def _enrich_npc_like(item: dict, *, faction_ids: set[str], add_spawn: bool) -> tuple[dict, list[str]]:
    manual: list[str] = []
    tags = set(str(t).strip() for t in _coerce_list(item.get("tags")))

    if add_spawn:
        spawn = _as_dict(item.get("spawn"))
        if not spawn:
            spawn = {
                "location_tags_any": [t for t in sorted(tags) if t and t not in faction_ids],
                "location_types_any": [],
                "min_alert": 0,
                "max_alert": 100,
            }
        else:
            spawn.setdefault("location_tags_any", [])
            spawn.setdefault("location_types_any", [])
            spawn["min_alert"] = _clamp_int(spawn.get("min_alert"), 0, 100, 0)
            spawn["max_alert"] = _clamp_int(spawn.get("max_alert"), 0, 100, 100)
        item["spawn"] = spawn

    levers = _as_dict(item.get("levers"))
    if not levers:
        levers = _default_levers(tags)
    levers["bribeable"] = _normalize_lever(levers.get("bribeable"))
    levers["intimidatable"] = _normalize_lever(levers.get("intimidatable"))
    levers["charmable"] = _normalize_lever(levers.get("charmable"))
    item["levers"] = levers

    authority = _as_dict(item.get("authority"))
    if not authority:
        authority = {"clearance_level": 0, "can_grant_access": []}
    authority["clearance_level"] = _clamp_int(authority.get("clearance_level"), 0, 5, 0)
    authority.setdefault("can_grant_access", [])
    item["authority"] = authority

    knowledge = _as_dict(item.get("knowledge"))
    if not knowledge:
        knowledge = {"rumors": [], "quest_facts": [], "secrets": []}
    knowledge.setdefault("rumors", [])
    knowledge.setdefault("quest_facts", [])
    knowledge.setdefault("secrets", [])
    item["knowledge"] = knowledge
    if not knowledge.get("rumors") and not knowledge.get("quest_facts") and not knowledge.get("secrets"):
        manual.append(f"npcs.{item.get('id')}.knowledge")

    return item, manual


@dataclass
class PackResult:
    era_dir: Path
    wrote: list[Path]
    manual: list[str]


def _detect_pack_dirs(pack_root: Path) -> list[Path]:
    out: list[Path] = []
    if not pack_root.exists():
        return out
    for d in sorted([p for p in pack_root.iterdir() if p.is_dir()], key=lambda p: p.name.lower()):
        if any((d / f"era{ext}").exists() for ext in (".yaml", ".yml")):
            out.append(d)
    return out


def enrich_pack_dir(
    era_dir: Path,
    *,
    in_place: bool,
    suffix: str,
    backup_ext: str,
    dry_run: bool,
) -> PackResult:
    wrote: list[Path] = []
    manual: list[str] = []

    era_yaml = era_dir / "era.yaml"
    if not era_yaml.exists():
        raise FileNotFoundError(f"Missing era.yaml in {era_dir}")

    # Load factions for faction-id filtering in NPC spawn rules.
    factions_yaml = era_dir / "factions.yaml"
    faction_ids: set[str] = set()
    if factions_yaml.exists():
        fdata = _read_yaml(factions_yaml)
        factions_list = _coerce_list(_as_dict(fdata).get("factions")) if isinstance(fdata, dict) else _coerce_list(fdata)
        for f in factions_list:
            if isinstance(f, dict) and f.get("id"):
                faction_ids.add(str(f["id"]).strip())

    # Load templates for encounter generation.
    npcs_yaml = era_dir / "npcs.yaml"
    npc_templates: list[dict] = []
    npcs_data: dict = {}
    if npcs_yaml.exists():
        raw = _read_yaml(npcs_yaml) or {}
        npcs_data = _as_dict(raw)
        pack = _as_dict(npcs_data.get("npcs")) if "npcs" in npcs_data else npcs_data
        npc_templates = [t for t in _coerce_list(pack.get("templates")) if isinstance(t, dict)]

    def _humanize_loc_id(loc_id: str) -> str:
        s = (loc_id or "").strip()
        for prefix in ("loc-", "loc_", "location-", "location_"):
            if s.lower().startswith(prefix):
                s = s[len(prefix):]
                break
        s = s.replace("_", " ").replace("-", " ").strip()
        return s.title() if s else (loc_id or "Unknown Location")

    # Load + enrich locations (write after we see missing refs from NPCs).
    locations_yaml = era_dir / "locations.yaml"
    loc_doc: dict = {}
    loc_doc_has_key = False
    new_locs: list[dict] = []
    if locations_yaml.exists():
        raw = _read_yaml(locations_yaml) or {}
        loc_doc = _as_dict(raw)
        loc_doc_has_key = "locations" in loc_doc
        locs = _coerce_list(loc_doc.get("locations")) if loc_doc_has_key else _coerce_list(raw)
        for loc in locs:
            if not isinstance(loc, dict):
                continue
            enriched, needs = _enrich_location(loc, npc_templates)
            new_locs.append(enriched)
            manual.extend(needs)

    # --- npcs.yaml ---
    missing_location_ids: set[str] = set()
    if npcs_yaml.exists():
        raw = _read_yaml(npcs_yaml) or {}
        doc = _as_dict(raw)
        pack = _as_dict(doc.get("npcs")) if "npcs" in doc else doc
        anchors = [x for x in _coerce_list(pack.get("anchors")) if isinstance(x, dict)]
        rotating = [x for x in _coerce_list(pack.get("rotating")) if isinstance(x, dict)]
        templates = [x for x in _coerce_list(pack.get("templates")) if isinstance(x, dict)]

        new_anchors: list[dict] = []
        new_rotating: list[dict] = []
        new_templates: list[dict] = []

        for item in anchors:
            enriched, needs = _enrich_npc_like(item, faction_ids=faction_ids, add_spawn=False)
            new_anchors.append(enriched)
            manual.extend(needs)
            if enriched.get("default_location_id"):
                missing_location_ids.add(str(enriched.get("default_location_id")).strip())
            for hl in _coerce_list(enriched.get("home_locations")):
                if hl:
                    missing_location_ids.add(str(hl).strip())
        for item in rotating:
            enriched, needs = _enrich_npc_like(item, faction_ids=faction_ids, add_spawn=True)
            new_rotating.append(enriched)
            manual.extend(needs)
            if enriched.get("default_location_id"):
                missing_location_ids.add(str(enriched.get("default_location_id")).strip())
            for hl in _coerce_list(enriched.get("home_locations")):
                if hl:
                    missing_location_ids.add(str(hl).strip())
        for item in templates:
            enriched, needs = _enrich_npc_like(item, faction_ids=faction_ids, add_spawn=True)
            new_templates.append(enriched)
            manual.extend(needs)

        out_pack = {"anchors": new_anchors, "rotating": new_rotating, "templates": new_templates}
        out_doc = {"npcs": out_pack} if "npcs" in doc else out_pack

        out_path = npcs_yaml if in_place else npcs_yaml.with_name(f"{npcs_yaml.stem}{suffix}{npcs_yaml.suffix}")
        if not dry_run:
            if in_place:
                bak = npcs_yaml.with_suffix(npcs_yaml.suffix + backup_ext)
                if not bak.exists():
                    shutil.copy2(npcs_yaml, bak)
            _write_yaml(out_path, out_doc)
        wrote.append(out_path)

    # Also ensure faction home_locations exist.
    if factions_yaml.exists():
        fdata = _read_yaml(factions_yaml) or {}
        factions_list = _coerce_list(_as_dict(fdata).get("factions")) if isinstance(fdata, dict) else _coerce_list(fdata)
        for f in factions_list:
            if not isinstance(f, dict):
                continue
            for hl in _coerce_list(f.get("home_locations")):
                if hl:
                    missing_location_ids.add(str(hl).strip())

    # Add stub locations for any referenced-but-missing ids.
    existing_loc_ids = {str(l.get("id")).strip() for l in new_locs if isinstance(l, dict) and l.get("id")}
    for loc_id in sorted(missing_location_ids):
        if not loc_id or loc_id in existing_loc_ids:
            continue
        stub = {
            "id": loc_id,
            "name": _humanize_loc_id(loc_id),
            "tags": ["stub"],
            "region": None,
            "controlling_factions": [],
            "planet": None,
            "description": None,
            "threat_level": "moderate",
        }
        enriched, needs = _enrich_location(stub, npc_templates)
        new_locs.append(enriched)
        manual.extend([f"locations.{loc_id}.STUB_CREATED"] + needs)
        existing_loc_ids.add(loc_id)

    # Write locations.yaml now that stubs are appended.
    if locations_yaml.exists():
        out_doc: Any = {"locations": new_locs} if loc_doc_has_key else new_locs
        out_path = locations_yaml if in_place else locations_yaml.with_name(f"{locations_yaml.stem}{suffix}{locations_yaml.suffix}")
        if not dry_run:
            if in_place:
                bak = locations_yaml.with_suffix(locations_yaml.suffix + backup_ext)
                if not bak.exists():
                    shutil.copy2(locations_yaml, bak)
            _write_yaml(out_path, out_doc)
        wrote.append(out_path)

    return PackResult(era_dir=era_dir, wrote=wrote, manual=sorted(set(manual)))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Enrich era pack YAMLs to v2 (safe defaults + deterministic output).")
    ap.add_argument("--pack-dir", type=str, default="data/static/era_packs", help="Era pack root directory")
    ap.add_argument("--era", type=str, default=None, help="Only enrich a single era directory name (e.g. rebellion)")
    ap.add_argument("--in-place", action="store_true", help="Write in-place (creates .bak backups once)")
    ap.add_argument("--suffix", type=str, default="_v2", help="Suffix for output files when not using --in-place")
    ap.add_argument("--backup-ext", type=str, default=".bak", help="Backup extension when using --in-place")
    ap.add_argument("--dry-run", action="store_true", help="Do not write; only report what would change")
    args = ap.parse_args(argv)

    pack_root = (ROOT / args.pack_dir).resolve()
    if not pack_root.exists():
        print(f"ERROR: pack dir does not exist: {pack_root}")
        return 2

    pack_dirs = _detect_pack_dirs(pack_root)
    if args.era:
        pack_dirs = [d for d in pack_dirs if d.name.lower() == args.era.strip().lower()]
    if not pack_dirs:
        print("No era pack directories found.")
        return 1

    results: list[PackResult] = []
    for d in pack_dirs:
        res = enrich_pack_dir(
            d,
            in_place=bool(args.in_place),
            suffix=str(args.suffix),
            backup_ext=str(args.backup_ext),
            dry_run=bool(args.dry_run),
        )
        results.append(res)

    # Report
    for r in results:
        rel = r.era_dir.relative_to(ROOT) if r.era_dir.is_relative_to(ROOT) else r.era_dir
        print(f"\n== {rel} ==")
        for p in r.wrote:
            p_rel = p.relative_to(ROOT) if p.is_relative_to(ROOT) else p
            print(f"WROTE: {p_rel}")
        if r.manual:
            print("MANUAL FILL NEEDED:")
            for item in r.manual[:200]:
                print(f"  - {item}")
            if len(r.manual) > 200:
                print(f"  ... ({len(r.manual) - 200} more)")
        else:
            print("MANUAL FILL NEEDED: (none)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
