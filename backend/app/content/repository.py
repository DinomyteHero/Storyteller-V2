from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from typing import Any

from backend.app.content.index import ContentIndices, build_indices
from backend.app.content.loader import (
    default_setting_id,
    load_stacked_period_content,
    normalize_key,
    resolve_legacy_era,
    resolve_legacy_roots,
    resolve_pack_roots,
)
from backend.app.world.era_pack_models import EraPack

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContentKey:
    setting_id: str
    period_id: str


def _norm(value: str) -> str:
    return normalize_key(value)


class ContentRepository:
    """App-lifetime content repository keyed by (setting_id, period_id).

    Backward compatibility is preserved through `get_pack(era_id)`.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._pack_cache: dict[ContentKey, EraPack] = {}
        self._indices_cache: dict[ContentKey, ContentIndices] = {}

    def _key(self, setting_id: str, period_id: str) -> ContentKey:
        return ContentKey(_norm(setting_id), _norm(period_id))

    def _load_generated_pack(self, setting_id: str, period_id: str) -> EraPack | None:
        """Load a generated era pack from the DB. Returns None if not found."""
        try:
            from backend.app.config import DEFAULT_DB_PATH
            from backend.app.db.connection import get_connection

            conn = get_connection(DEFAULT_DB_PATH)
            try:
                row = conn.execute(
                    "SELECT era_pack_json FROM generated_era_packs "
                    "WHERE setting_id = ? AND period_id = ? "
                    "ORDER BY version DESC LIMIT 1",
                    (setting_id, period_id),
                ).fetchone()
                if not row:
                    return None
                data = json.loads(row["era_pack_json"])
                if not isinstance(data, dict):
                    return None
                return EraPack.model_validate(data)
            finally:
                conn.close()
        except Exception:
            logger.warning(
                "Failed to load generated pack for %s/%s from DB",
                setting_id, period_id, exc_info=True,
            )
            return None

    def get_content(self, setting_id: str, period_id: str) -> EraPack:
        key = self._key(setting_id, period_id)
        with self._lock:
            cached = self._pack_cache.get(key)
            if cached is not None:
                return cached

            try:
                merged = load_stacked_period_content(setting_id=key.setting_id, period_id=key.period_id)
                pack = EraPack.model_validate(merged)
            except FileNotFoundError:
                pack = self._load_generated_pack(key.setting_id, key.period_id)
                if pack is None:
                    raise

            self._pack_cache[key] = pack
            self._indices_cache[key] = build_indices(pack)
            return pack

    def get_indices(self, setting_id: str, period_id: str) -> ContentIndices:
        key = self._key(setting_id, period_id)
        with self._lock:
            if key not in self._indices_cache:
                self.get_content(setting_id, period_id)
            return self._indices_cache[key]

    # Backward-compatible API (legacy "era_id")
    def get_pack(self, era_id: str) -> EraPack:
        setting_id, period_id = resolve_legacy_era(era_id)
        return self.get_content(setting_id, period_id)

    def get_pack_by_alias(self, *, setting_id: str | None = None, period_id: str | None = None, era_id: str | None = None) -> EraPack:
        if setting_id and period_id:
            return self.get_content(setting_id, period_id)
        if era_id:
            return self.get_pack(era_id)
        return self.get_content(default_setting_id(), "rebellion")

    def load_all_packs(self) -> list[EraPack]:
        packs: list[EraPack] = []
        seen: set[ContentKey] = set()
        for root in resolve_pack_roots():
            if not root.exists() or not root.is_dir():
                continue
            for setting_dir in sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.name.lower()):
                periods_dir = setting_dir / "periods"
                if not periods_dir.exists() or not periods_dir.is_dir():
                    continue
                for period_dir in sorted([p for p in periods_dir.iterdir() if p.is_dir()], key=lambda p: p.name.lower()):
                    key = self._key(setting_dir.name, period_dir.name)
                    if key in seen:
                        continue
                    seen.add(key)
                    packs.append(self.get_content(key.setting_id, key.period_id))

        if packs:
            return packs

        default_setting = default_setting_id()
        for legacy_root in resolve_legacy_roots():
            if not legacy_root.exists() or not legacy_root.is_dir():
                continue
            for d in sorted([p for p in legacy_root.iterdir() if p.is_dir()], key=lambda p: p.name.lower()):
                key = self._key(default_setting, d.name)
                if key in seen:
                    continue
                seen.add(key)
                try:
                    packs.append(self.get_content(key.setting_id, key.period_id))
                except FileNotFoundError:
                    continue
        return packs

    def _list_generated_catalog_entries(self) -> list[dict[str, Any]]:
        """Query generated_era_packs table and return catalog entries."""
        entries: list[dict[str, Any]] = []
        try:
            from backend.app.config import DEFAULT_DB_PATH
            from backend.app.db.connection import get_connection

            conn = get_connection(DEFAULT_DB_PATH)
            try:
                rows = conn.execute(
                    "SELECT setting_id, period_id, display_name, summary, era_pack_json "
                    "FROM generated_era_packs "
                    "ORDER BY setting_id, period_id, version DESC",
                ).fetchall()
                seen: set[tuple[str, str]] = set()
                for row in rows:
                    sid = str(row["setting_id"]).strip()
                    pid = str(row["period_id"]).strip()
                    if (sid, pid) in seen:
                        continue
                    seen.add((sid, pid))
                    try:
                        data = json.loads(row["era_pack_json"])
                    except (json.JSONDecodeError, TypeError):
                        data = {}
                    md = data.get("metadata") if isinstance(data, dict) else {}
                    if not isinstance(md, dict):
                        md = {}
                    bgs = data.get("backgrounds") or [] if isinstance(data, dict) else []
                    locs = data.get("locations") or [] if isinstance(data, dict) else []
                    comps = data.get("companions") or [] if isinstance(data, dict) else []
                    quests = data.get("quests") or [] if isinstance(data, dict) else []
                    sr = data.get("setting_rules") or {} if isinstance(data, dict) else {}
                    if not isinstance(sr, dict):
                        sr = {}
                    sn = str(sr.get("setting_name") or data.get("setting_name") or sid.replace("_", " ").title()) if isinstance(data, dict) else sid.replace("_", " ").title()
                    dn = str(row["display_name"] or "").strip() or str(md.get("display_name") or "").strip() or pid.replace("_", " ").title()
                    # Generated packs are playable if they have backgrounds (locations are generated by CampaignBibleAgent)
                    playable = bool(bgs)
                    reasons: list[str] = []
                    if not bgs:
                        reasons.append("no_backgrounds")
                    entries.append({
                        "setting_id": sid,
                        "setting_display_name": sn,
                        "period_id": pid,
                        "period_display_name": dn,
                        "legacy_era_id": f"{sid}__{pid}",
                        "source": "generated_era_pack",
                        "summary": str(row["summary"] or "").strip(),
                        "playable": playable,
                        "playability_reasons": reasons,
                        "locations_count": len(locs),
                        "backgrounds_count": len(bgs),
                        "companions_count": len(comps),
                        "quests_count": len(quests),
                    })
            finally:
                conn.close()
        except Exception:
            logger.warning("Failed to list generated era packs from DB", exc_info=True)
        return entries

    def list_catalog(self) -> list[dict[str, Any]]:
        """Return discovered content entries for API/UI catalog usage.

        Each row represents a playable (or potentially playable) period.
        Static YAML packs take priority over generated packs for the same key.
        """
        entries: list[dict[str, Any]] = []
        packs = self.load_all_packs()
        seen_keys: set[tuple[str, str]] = set()
        for pack in packs:
            raw_era = str(pack.era_id or "").strip()
            setting_id, period_id = resolve_legacy_era(raw_era)
            seen_keys.add((setting_id, period_id))
            md = pack.metadata if isinstance(pack.metadata, dict) else {}
            display_name = (
                str(md.get("display_name") or "").strip()
                or raw_era.replace("_", " ").title()
                or period_id.replace("_", " ").title()
            )
            summary = str(md.get("summary") or "").strip()
            playable = bool(pack.locations) and bool(pack.backgrounds)
            reasons: list[str] = []
            if not pack.locations:
                reasons.append("no_locations")
            if not pack.backgrounds:
                reasons.append("no_backgrounds")
            if not pack.quests:
                reasons.append("no_quests")
            entries.append(
                {
                    "setting_id": setting_id,
                    "setting_display_name": str(pack.setting_name or md.get("setting_name") or setting_id.replace("_", " ").title()),
                    "period_id": period_id,
                    "period_display_name": display_name,
                    "legacy_era_id": raw_era,
                    "source": "legacy_era_pack",
                    "summary": summary,
                    "playable": playable,
                    "playability_reasons": reasons,
                    "locations_count": len(pack.locations or []),
                    "backgrounds_count": len(pack.backgrounds or []),
                    "companions_count": len(pack.companions or []),
                    "quests_count": len(pack.quests or []),
                }
            )
        # Append generated packs that don't overlap with static YAML packs
        for gen_entry in self._list_generated_catalog_entries():
            key = (gen_entry["setting_id"], gen_entry["period_id"])
            if key not in seen_keys:
                seen_keys.add(key)
                entries.append(gen_entry)
        # deterministic ordering for UI
        entries.sort(key=lambda e: (str(e.get("setting_id", "")), str(e.get("period_id", ""))))
        return entries

    def clear_cache(self) -> None:
        with self._lock:
            self._pack_cache.clear()
            self._indices_cache.clear()


CONTENT_REPOSITORY = ContentRepository()
