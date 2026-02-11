from __future__ import annotations

import copy
import os
import re
from pathlib import Path
from typing import Any, Iterable

import yaml


def normalize_key(value: str) -> str:
    raw = (value or "").strip().lower()
    raw = re.sub(r"[^a-z0-9]+", "_", raw)
    return raw.strip("_")


def default_setting_id() -> str:
    return normalize_key(os.environ.get("DEFAULT_SETTING_ID", "star_wars_legends"))


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _abs(path_value: str) -> Path:
    p = Path(path_value)
    return p if p.is_absolute() else _repo_root() / p


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _coerce_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def deep_merge(base: Any, incoming: Any) -> Any:
    if isinstance(base, dict) and isinstance(incoming, dict):
        out = copy.deepcopy(base)
        for k, v in incoming.items():
            if k in out:
                out[k] = deep_merge(out[k], v)
            else:
                out[k] = copy.deepcopy(v)
        return out
    if isinstance(base, list) and isinstance(incoming, list):
        if all(isinstance(i, dict) and i.get("id") for i in (base + incoming)):
            return merge_list_by_id(base, incoming)
        return copy.deepcopy(incoming)
    return copy.deepcopy(incoming)


def merge_list_by_id(base: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    index_by_id: dict[str, int] = {}

    def _rebuild_index() -> None:
        index_by_id.clear()
        for idx, existing in enumerate(out):
            existing_id = str(existing.get("id") or "")
            if existing_id:
                index_by_id[existing_id] = idx

    def _apply(item: dict[str, Any]) -> None:
        item_id = str(item.get("id") or "")
        if not item_id:
            out.append(copy.deepcopy(item))
            return
        if item.get("disabled") is True:
            if item_id in index_by_id:
                out.pop(index_by_id[item_id])
                _rebuild_index()
            return
        if item_id in index_by_id:
            out[index_by_id[item_id]] = deep_merge(out[index_by_id[item_id]], item)
        else:
            out.append(copy.deepcopy(item))
            index_by_id[item_id] = len(out) - 1

    for i in base:
        if isinstance(i, dict):
            _apply(i)
    for i in incoming:
        if isinstance(i, dict):
            _apply(i)
    return out


def resolve_extends(items: list[dict[str, Any]], *, section_name: str) -> list[dict[str, Any]]:
    by_id = {str(i.get("id")): i for i in items if isinstance(i, dict) and i.get("id")}
    resolved: dict[str, dict[str, Any]] = {}
    in_stack: set[str] = set()

    def _visit(item_id: str) -> dict[str, Any]:
        if item_id in resolved:
            return resolved[item_id]
        if item_id in in_stack:
            raise ValueError(f"{section_name} extends cycle detected at '{item_id}'")
        item = by_id.get(item_id)
        if item is None:
            raise ValueError(f"{section_name} missing id '{item_id}'")

        in_stack.add(item_id)
        base_id = item.get("extends")
        if base_id:
            base_key = str(base_id)
            if base_key not in by_id:
                raise ValueError(f"{section_name}[{item_id}] extends missing base '{base_id}'")
            merged = deep_merge(_visit(base_key), {k: v for k, v in item.items() if k != "extends"})
        else:
            merged = copy.deepcopy(item)
        in_stack.remove(item_id)
        resolved[item_id] = merged
        return merged

    return [_visit(str(obj["id"])) for obj in items if isinstance(obj, dict) and obj.get("id")]


def parse_legacy_era_mapping() -> dict[str, tuple[str, str]]:
    mapping_path_raw = os.environ.get("ERA_TO_SETTING_PERIOD_MAP", "").strip()
    if not mapping_path_raw:
        return {}
    mapping_path = _abs(mapping_path_raw)
    if not mapping_path.exists():
        return {}
    data = _load_yaml(mapping_path)
    if not isinstance(data, dict):
        return {}
    out: dict[str, tuple[str, str]] = {}
    for legacy_era, value in data.items():
        if isinstance(value, dict):
            setting_id = normalize_key(str(value.get("setting_id") or default_setting_id()))
            period_id = normalize_key(str(value.get("period_id") or legacy_era))
            out[normalize_key(str(legacy_era))] = (setting_id, period_id)
    return out


def resolve_legacy_era(era_id: str) -> tuple[str, str]:
    era_key = normalize_key(era_id)
    mapped = parse_legacy_era_mapping().get(era_key)
    if mapped:
        return mapped
    return (default_setting_id(), era_key)


def _load_list_section(dir_path: Path, key: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for ext in (".yaml", ".yml"):
        fp = dir_path / f"{key}{ext}"
        if fp.exists() and fp.is_file():
            data = _load_yaml(fp)
            data = data.get(key) if isinstance(data, dict) and key in data else data
            items.extend([x for x in _coerce_list(data) if isinstance(x, dict)])
    section_dir = dir_path / key
    if section_dir.exists() and section_dir.is_dir():
        for fp in sorted(section_dir.glob("*.yml")) + sorted(section_dir.glob("*.yaml")):
            data = _load_yaml(fp)
            data = data.get(key) if isinstance(data, dict) and key in data else data
            items.extend([x for x in _coerce_list(data) if isinstance(x, dict)])
    return items


def _load_mapping_section(dir_path: Path, key: str) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for ext in (".yaml", ".yml"):
        fp = dir_path / f"{key}{ext}"
        if fp.exists() and fp.is_file():
            data = _load_yaml(fp)
            data = data.get(key) if isinstance(data, dict) and key in data else data
            if isinstance(data, dict):
                merged = deep_merge(merged, data)
    section_dir = dir_path / key
    if section_dir.exists() and section_dir.is_dir():
        for fp in sorted(section_dir.glob("*.yml")) + sorted(section_dir.glob("*.yaml")):
            data = _load_yaml(fp)
            data = data.get(key) if isinstance(data, dict) and key in data else data
            if isinstance(data, dict):
                merged = deep_merge(merged, data)
    return merged


def _load_npcs(dir_path: Path) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {"anchors": [], "rotating": [], "templates": []}
    for ext in (".yaml", ".yml"):
        fp = dir_path / f"npcs{ext}"
        if fp.exists() and fp.is_file():
            data = _load_yaml(fp)
            data = data.get("npcs") if isinstance(data, dict) and "npcs" in data else data
            if isinstance(data, dict):
                for bucket in out:
                    out[bucket].extend([x for x in _coerce_list(data.get(bucket)) if isinstance(x, dict)])
    npcs_dir = dir_path / "npcs"
    if npcs_dir.exists() and npcs_dir.is_dir():
        for bucket in out:
            out[bucket].extend(_load_list_section(npcs_dir, bucket))
    return out


def _load_period_dir(period_dir: Path) -> dict[str, Any]:
    base: dict[str, Any] = {}
    for stem in ("manifest", "era", "pack"):
        for ext in (".yaml", ".yml"):
            fp = period_dir / f"{stem}{ext}"
            if fp.exists() and fp.is_file():
                data = _load_yaml(fp)
                if isinstance(data, dict):
                    base = copy.deepcopy(data)
                    break
        if base:
            break
    if not base:
        raise FileNotFoundError(f"No manifest/era/pack file found in {period_dir}")

    for section in ("factions", "locations", "backgrounds", "quests", "events", "rumors", "facts", "companions"):
        current = [x for x in _coerce_list(base.get(section)) if isinstance(x, dict)]
        current.extend(_load_list_section(period_dir, section))
        if current:
            base[section] = current

    for section in ("namebanks", "meters"):
        current = base.get(section) if isinstance(base.get(section), dict) else {}
        merged = _load_mapping_section(period_dir, section)
        base[section] = deep_merge(current, merged)

    missions = base.get("missions") if isinstance(base.get("missions"), dict) else {}
    mission_templates = [x for x in _coerce_list(missions.get("templates")) if isinstance(x, dict)]
    mission_templates.extend(_load_list_section(period_dir, "missions"))
    if mission_templates:
        missions["templates"] = mission_templates
        base["missions"] = missions

    npcs = base.get("npcs") if isinstance(base.get("npcs"), dict) else {}
    loaded_npcs = _load_npcs(period_dir)
    for bucket in ("anchors", "rotating", "templates"):
        items = [x for x in _coerce_list(npcs.get(bucket)) if isinstance(x, dict)]
        items.extend(loaded_npcs.get(bucket, []))
        npcs[bucket] = items
    base["npcs"] = npcs

    return base


def _candidate_new_layout_dirs(pack_root: Path, setting_key: str, period_key: str) -> Iterable[Path]:
    yield pack_root / setting_key / "periods" / period_key
    if (pack_root / setting_key / "periods").exists():
        for d in (pack_root / setting_key / "periods").iterdir():
            if d.is_dir() and normalize_key(d.name) == period_key:
                yield d


def _candidate_legacy_layout_dirs(pack_root: Path, period_key: str) -> Iterable[Path]:
    yield pack_root / period_key
    if pack_root.exists() and pack_root.is_dir():
        for d in pack_root.iterdir():
            if d.is_dir() and normalize_key(d.name) == period_key:
                yield d


def _candidate_legacy_files(pack_root: Path, period_key: str) -> Iterable[Path]:
    for ext in (".yaml", ".yml"):
        yield pack_root / f"{period_key}{ext}"


def resolve_pack_roots() -> list[Path]:
    raw = os.environ.get("SETTING_PACK_PATHS", "").strip()
    if raw:
        return [_abs(p.strip()) for p in raw.split(";") if p.strip()]
    return [_abs("./data/static/setting_packs/core"), _abs("./data/static/setting_packs/addons"), _abs("./data/static/setting_packs/overrides")]


def resolve_legacy_roots() -> list[Path]:
    raw = os.environ.get("ERA_PACK_DIR", "./data/static/era_packs")
    return [_abs(raw)]


def load_stacked_period_content(setting_id: str, period_id: str) -> dict[str, Any]:
    setting_key = normalize_key(setting_id)
    period_key = normalize_key(period_id)
    merged: dict[str, Any] = {}
    found = False

    for root in resolve_pack_roots():
        for period_dir in _candidate_new_layout_dirs(root, setting_key, period_key):
            if period_dir.exists() and period_dir.is_dir():
                found = True
                merged = deep_merge(merged, _load_period_dir(period_dir))
                break

    # fallback to legacy era packs if setting layout is missing
    if not found and setting_key == default_setting_id():
        for root in resolve_legacy_roots():
            for d in _candidate_legacy_layout_dirs(root, period_key):
                if d.exists() and d.is_dir():
                    found = True
                    merged = deep_merge(merged, _load_period_dir(d))
                    break
            if not found:
                for f in _candidate_legacy_files(root, period_key):
                    if f.exists() and f.is_file():
                        data = _load_yaml(f)
                        if isinstance(data, dict):
                            found = True
                            merged = deep_merge(merged, data)
                            break

    if not found:
        raise FileNotFoundError(f"No setting pack found for setting='{setting_id}' period='{period_id}'")

    if "era_id" not in merged:
        merged["era_id"] = period_key.upper()

    npcs = merged.get("npcs") if isinstance(merged.get("npcs"), dict) else {}
    npcs["templates"] = resolve_extends(
        [x for x in _coerce_list(npcs.get("templates")) if isinstance(x, dict)],
        section_name="npcs.templates",
    )
    merged["npcs"] = npcs

    missions = merged.get("missions") if isinstance(merged.get("missions"), dict) else {}
    templates = [x for x in _coerce_list(missions.get("templates")) if isinstance(x, dict)]
    if templates:
        missions["templates"] = resolve_extends(templates, section_name="missions.templates")

    # keep mission templates in metadata for compatibility with EraPack schema
    metadata = merged.get("metadata") if isinstance(merged.get("metadata"), dict) else {}
    metadata["setting_id"] = setting_key
    metadata["period_id"] = period_key
    metadata["mission_templates"] = missions.get("templates", [])
    merged["metadata"] = metadata

    merged.pop("setting_id", None)
    merged.pop("period_id", None)
    merged.pop("missions", None)

    return merged
