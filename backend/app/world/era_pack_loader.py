"""Era pack loader with module-level cache."""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Iterable

import yaml

from backend.app.world.era_pack_models import EraPack

logger = logging.getLogger(__name__)

_PACK_CACHE: dict[str, EraPack] = {}


def _normalize_era_key(value: str) -> str:
    """Normalize era identifiers for filenames and cache keys."""
    raw = (value or "").strip().lower()
    raw = re.sub(r"[^a-z0-9]+", "_", raw)
    return raw.strip("_")


def _resolve_pack_dir() -> Path:
    raw = os.environ.get("ERA_PACK_DIR", "./data/static/era_packs").strip()
    p = Path(raw) if raw else Path("./data/static/era_packs")
    if p.is_absolute():
        return p
    root = Path(__file__).resolve().parents[3]
    return root / p


def _candidate_files(pack_dir: Path, era_key: str) -> Iterable[Path]:
    """Yield candidate pack files for the given era key."""
    for ext in (".yaml", ".yml"):
        yield pack_dir / f"{era_key}{ext}"
    # Fallback: case-insensitive match on stem
    for p in pack_dir.glob("*.yml"):
        if _normalize_era_key(p.stem) == era_key:
            yield p
    for p in pack_dir.glob("*.yaml"):
        if _normalize_era_key(p.stem) == era_key:
            yield p


def _candidate_dirs(pack_dir: Path, era_key: str) -> Iterable[Path]:
    """Yield candidate pack directories for the given era key."""
    yield pack_dir / era_key
    for p in pack_dir.iterdir():
        if p.is_dir() and _normalize_era_key(p.name) == era_key:
            yield p


def _read_yaml(path: Path) -> object:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _coerce_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _merge_mapping_lists(base: dict, incoming: dict) -> dict:
    """Merge two dict[str, list] structures, deduping items while preserving order."""
    out = dict(base or {})
    for k, v in (incoming or {}).items():
        if not isinstance(k, str):
            continue
        if not isinstance(v, list):
            continue
        existing = out.get(k)
        if not isinstance(existing, list):
            out[k] = list(v)
            continue
        seen = set(existing)
        for item in v:
            if item in seen:
                continue
            existing.append(item)
            seen.add(item)
        out[k] = existing
    return out


def _dedup_by_id(items: list[dict], *, id_key: str = "id") -> list[dict]:
    """Deduplicate a list of dicts by `id` while preserving order (later items overwrite earlier)."""
    out: list[dict] = []
    index_by_id: dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_id = item.get(id_key)
        if not raw_id:
            out.append(item)
            continue
        key = str(raw_id)
        if key in index_by_id:
            out[index_by_id[key]] = item
        else:
            index_by_id[key] = len(out)
            out.append(item)
    return out


def _load_dict_section(dir_path: Path, section_key: str) -> dict:
    """Load a dict section from `{section_key}.yml|yaml` and `{section_key}/**/*.yml|yaml`.

    Later files override earlier keys (shallow merge). This is intentionally different from
    `_load_mapping_section` (which merges dict[str, list] like namebanks).
    """
    merged: dict = {}
    for ext in (".yaml", ".yml"):
        fp = dir_path / f"{section_key}{ext}"
        if fp.exists() and fp.is_file():
            data = _read_yaml(fp)
            if isinstance(data, dict) and section_key in data and isinstance(data.get(section_key), dict):
                merged.update(data.get(section_key) or {})
            elif isinstance(data, dict):
                merged.update(data)
    section_dir = dir_path / section_key
    if section_dir.exists() and section_dir.is_dir():
        for fp in sorted(section_dir.glob("*.yml")) + sorted(section_dir.glob("*.yaml")):
            data = _read_yaml(fp)
            if isinstance(data, dict) and section_key in data and isinstance(data.get(section_key), dict):
                merged.update(data.get(section_key) or {})
            elif isinstance(data, dict):
                merged.update(data)
    return merged


def _load_list_section(dir_path: Path, section_key: str) -> list[dict]:
    """Load a list section from `{section_key}.yml|yaml` and `{section_key}/**/*.yml|yaml`."""
    items: list[dict] = []
    for ext in (".yaml", ".yml"):
        fp = dir_path / f"{section_key}{ext}"
        if fp.exists() and fp.is_file():
            data = _read_yaml(fp)
            if isinstance(data, dict) and section_key in data:
                items.extend(_coerce_list(data.get(section_key)))
            else:
                items.extend(_coerce_list(data))
    section_dir = dir_path / section_key
    if section_dir.exists() and section_dir.is_dir():
        for fp in sorted(section_dir.glob("*.yml")) + sorted(section_dir.glob("*.yaml")):
            data = _read_yaml(fp)
            if isinstance(data, dict) and section_key in data:
                items.extend(_coerce_list(data.get(section_key)))
            else:
                items.extend(_coerce_list(data))
    return [i for i in items if isinstance(i, dict)]


def _load_mapping_section(dir_path: Path, section_key: str) -> dict:
    """Load a dict section from `{section_key}.yml|yaml` and `{section_key}/**/*.yml|yaml`."""
    merged: dict = {}
    for ext in (".yaml", ".yml"):
        fp = dir_path / f"{section_key}{ext}"
        if fp.exists() and fp.is_file():
            data = _read_yaml(fp)
            if isinstance(data, dict) and section_key in data:
                data = data.get(section_key)
            if isinstance(data, dict):
                merged = _merge_mapping_lists(merged, data)
    section_dir = dir_path / section_key
    if section_dir.exists() and section_dir.is_dir():
        for fp in sorted(section_dir.glob("*.yml")) + sorted(section_dir.glob("*.yaml")):
            data = _read_yaml(fp)
            if isinstance(data, dict) and section_key in data:
                data = data.get(section_key)
            if isinstance(data, dict):
                merged = _merge_mapping_lists(merged, data)
    return merged


def _load_faction_relationships(dir_path: Path) -> dict | None:
    """Load optional `faction_relationships` mapping from factions.yaml (if present)."""
    for ext in (".yaml", ".yml"):
        fp = dir_path / f"factions{ext}"
        if fp.exists() and fp.is_file():
            data = _read_yaml(fp)
            if isinstance(data, dict) and isinstance(data.get("faction_relationships"), dict):
                return data.get("faction_relationships") or {}
    return None


def _load_npcs_section(dir_path: Path) -> dict:
    """Load `npcs` from `npcs.yml|yaml` and `npcs/{anchors,rotating,templates}/*`."""
    merged = {"anchors": [], "rotating": [], "templates": []}

    def _merge_pack(pack: object) -> None:
        if not isinstance(pack, dict):
            return
        for key in ("anchors", "rotating", "templates"):
            merged[key].extend(_coerce_list(pack.get(key)))

    for ext in (".yaml", ".yml"):
        fp = dir_path / f"npcs{ext}"
        if fp.exists() and fp.is_file():
            data = _read_yaml(fp)
            if isinstance(data, dict) and "npcs" in data:
                _merge_pack(data.get("npcs"))
            else:
                _merge_pack(data)

    npcs_dir = dir_path / "npcs"
    if npcs_dir.exists() and npcs_dir.is_dir():
        for key in ("anchors", "rotating", "templates"):
            for ext in (".yaml", ".yml"):
                fp = npcs_dir / f"{key}{ext}"
                if fp.exists() and fp.is_file():
                    data = _read_yaml(fp)
                    if isinstance(data, dict) and key in data:
                        merged[key].extend(_coerce_list(data.get(key)))
                    else:
                        merged[key].extend(_coerce_list(data))
            bucket_dir = npcs_dir / key
            if bucket_dir.exists() and bucket_dir.is_dir():
                for fp in sorted(bucket_dir.glob("*.yml")) + sorted(bucket_dir.glob("*.yaml")):
                    data = _read_yaml(fp)
                    if isinstance(data, dict) and key in data:
                        merged[key].extend(_coerce_list(data.get(key)))
                    else:
                        merged[key].extend(_coerce_list(data))

    # Normalize to list[dict] and dedupe by id
    for key in ("anchors", "rotating", "templates"):
        merged[key] = _dedup_by_id([i for i in merged[key] if isinstance(i, dict)])
    return merged


def _load_pack_from_dir(dir_path: Path) -> EraPack:
    """Load an era pack from a modular directory."""
    base: dict | None = None
    for stem in ("era", "pack"):
        for ext in (".yaml", ".yml"):
            fp = dir_path / f"{stem}{ext}"
            if fp.exists() and fp.is_file():
                data = _read_yaml(fp)
                if isinstance(data, dict):
                    base = dict(data)
                    break
        if base is not None:
            break
    if base is None:
        raise FileNotFoundError(f"No base era pack file found in {dir_path} (expected era.yaml or pack.yaml)")

    # Merge sections from base + modular files.
    factions = _coerce_list(base.get("factions"))
    factions.extend(_load_list_section(dir_path, "factions"))

    locations = _coerce_list(base.get("locations"))
    locations.extend(_load_list_section(dir_path, "locations"))

    namebanks = {}
    if isinstance(base.get("namebanks"), dict):
        namebanks = _merge_mapping_lists(namebanks, base.get("namebanks") or {})
    namebanks = _merge_mapping_lists(namebanks, _load_mapping_section(dir_path, "namebanks"))

    npcs = {"anchors": [], "rotating": [], "templates": []}
    if isinstance(base.get("npcs"), dict):
        npcs = {
            "anchors": _coerce_list((base.get("npcs") or {}).get("anchors")),
            "rotating": _coerce_list((base.get("npcs") or {}).get("rotating")),
            "templates": _coerce_list((base.get("npcs") or {}).get("templates")),
        }
    loaded_npcs = _load_npcs_section(dir_path)
    for k in ("anchors", "rotating", "templates"):
        npcs[k].extend(_coerce_list(loaded_npcs.get(k)))
        npcs[k] = _dedup_by_id([i for i in npcs[k] if isinstance(i, dict)])

    backgrounds = _coerce_list(base.get("backgrounds"))
    backgrounds.extend(_load_list_section(dir_path, "backgrounds"))
    backgrounds = _dedup_by_id([i for i in backgrounds if isinstance(i, dict)])

    quests = _coerce_list(base.get("quests"))
    quests.extend(_load_list_section(dir_path, "quests"))
    quests = _dedup_by_id([i for i in quests if isinstance(i, dict)])

    events = _coerce_list(base.get("events"))
    events.extend(_load_list_section(dir_path, "events"))
    events = _dedup_by_id([i for i in events if isinstance(i, dict)])

    rumors = _coerce_list(base.get("rumors"))
    rumors.extend(_load_list_section(dir_path, "rumors"))
    rumors = _dedup_by_id([i for i in rumors if isinstance(i, dict)])

    facts = _coerce_list(base.get("facts"))
    facts.extend(_load_list_section(dir_path, "facts"))
    facts = _dedup_by_id([i for i in facts if isinstance(i, dict)])

    companions = _coerce_list(base.get("companions"))
    companions.extend(_load_list_section(dir_path, "companions"))
    companions = _dedup_by_id([i for i in companions if isinstance(i, dict)])

    meters = {}
    if isinstance(base.get("meters"), dict):
        meters.update(base.get("meters") or {})
    meters.update(_load_dict_section(dir_path, "meters"))

    base["factions"] = _dedup_by_id([i for i in factions if isinstance(i, dict)])
    base["locations"] = _dedup_by_id([i for i in locations if isinstance(i, dict)])
    base["namebanks"] = namebanks
    base["npcs"] = npcs
    base["backgrounds"] = backgrounds
    base["quests"] = quests
    base["events"] = events
    base["rumors"] = rumors
    base["facts"] = facts
    base["companions"] = companions
    if meters:
        base["meters"] = meters
    faction_relationships = _load_faction_relationships(dir_path)
    if faction_relationships is not None:
        base["faction_relationships"] = faction_relationships
    return EraPack.model_validate(base)


def load_era_pack(era: str) -> EraPack:
    """Load an EraPack by era id, validating with Pydantic and caching by era key."""
    if not era or not str(era).strip():
        raise ValueError("era is required to load an era pack")
    era_key = _normalize_era_key(era)
    if era_key in _PACK_CACHE:
        return _PACK_CACHE[era_key]

    pack_dir = _resolve_pack_dir()
    if not pack_dir.exists():
        raise FileNotFoundError(f"ERA_PACK_DIR does not exist: {pack_dir}")

    # Prefer modular directory packs when present.
    for candidate in _candidate_dirs(pack_dir, era_key):
        if candidate.exists() and candidate.is_dir():
            pack = _load_pack_from_dir(candidate)
            pack_key = _normalize_era_key(pack.era_id)
            _PACK_CACHE[era_key] = pack
            _PACK_CACHE[pack_key] = pack
            logger.info("Loaded era pack (dir): %s (%s)", pack.era_id, candidate.name)
            return pack

    pack_path: Path | None = None
    for candidate in _candidate_files(pack_dir, era_key):
        if candidate.exists() and candidate.is_file():
            pack_path = candidate
            break
    if pack_path is None:
        raise FileNotFoundError(f"No era pack found for '{era}' in {pack_dir}")

    data = yaml.safe_load(pack_path.read_text(encoding="utf-8"))
    pack = EraPack.model_validate(data)
    pack_key = _normalize_era_key(pack.era_id)
    _PACK_CACHE[era_key] = pack
    _PACK_CACHE[pack_key] = pack
    logger.info("Loaded era pack: %s (%s)", pack.era_id, pack_path.name)
    return pack


def get_era_pack(era: str | None) -> EraPack | None:
    """Return an EraPack or None if not found."""
    if not era or not str(era).strip():
        return None
    try:
        return load_era_pack(era)
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.error("Failed to load era pack '%s': %s", era, e, exc_info=True)
        return None


def load_all_era_packs(pack_dir: Path | None = None) -> list[EraPack]:
    """Load all era packs from the given directory (or ERA_PACK_DIR)."""
    pack_dir = pack_dir or _resolve_pack_dir()
    if not pack_dir.exists():
        return []

    packs: list[EraPack] = []
    loaded_keys: set[str] = set()

    # Directory packs first (they override file packs of the same normalized key).
    for d in sorted([p for p in pack_dir.iterdir() if p.is_dir()], key=lambda p: p.name.lower()):
        try:
            if not any((d / f"era{ext}").exists() for ext in (".yaml", ".yml")) and not any((d / f"pack{ext}").exists() for ext in (".yaml", ".yml")):
                continue
            pack = _load_pack_from_dir(d)
            k = _normalize_era_key(pack.era_id)
            if k in loaded_keys:
                continue
            packs.append(pack)
            loaded_keys.add(k)
        except Exception as e:
            logger.error("Failed to load era pack dir %s: %s", d.name, e)
            raise

    # File packs (legacy)
    for p in sorted(pack_dir.glob("*.yml")) + sorted(pack_dir.glob("*.yaml")):
        try:
            stem_key = _normalize_era_key(p.stem)
            if stem_key in loaded_keys:
                continue
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
            pack = EraPack.model_validate(data)
            k = _normalize_era_key(pack.era_id)
            if k in loaded_keys:
                continue
            packs.append(pack)
            loaded_keys.add(k)
        except Exception as e:
            logger.error("Failed to load era pack %s: %s", p.name, e)
            raise

    return packs


def clear_era_pack_cache() -> None:
    """Clear cached era packs (useful for tests)."""
    _PACK_CACHE.clear()
