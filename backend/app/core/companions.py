"""Companion definitions and campaign seeding for KOTOR/ME-style party system."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from shared.cache import clear_cache, get_cache_value, set_cache_value

_COMPANIONS_CACHE_KEY = "companions_cache"


def _companions_path() -> Path:
    """Resolve path to data/companions.yaml relative to project root."""
    # backend/app/core/companions.py -> project_root/data/companions.yaml
    root = Path(__file__).resolve().parent.parent.parent.parent
    return root / "data" / "companions.yaml"


def load_companions(era: str | None = None) -> list[dict[str, Any]]:
    """Load companion definitions, optionally filtered by era.

    Load order:
    1. Check era pack dir: data/static/era_packs/{era}/companions.yaml
    2. Fall back to data/companions.yaml (global pool)
    3. Filter by era field if present and era is specified
    """
    cached = get_cache_value(_COMPANIONS_CACHE_KEY, lambda: None)
    if cached is None:
        all_comps: list[dict[str, Any]] = []
        # Load global pool
        path = _companions_path()
        if path.exists():
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            global_comps = data.get("companions", []) if isinstance(data, dict) else []
            all_comps.extend(c for c in global_comps if isinstance(c, dict) and c.get("id"))

        # Also check era pack companions (additive, with V2.20 fields)
        root = Path(__file__).resolve().parent.parent.parent.parent
        era_packs_dir = root / "data" / "static" / "era_packs"
        if era_packs_dir.is_dir():
            seen_ids = {c["id"] for c in all_comps}
            for era_dir in era_packs_dir.iterdir():
                if not era_dir.is_dir():
                    continue
                era_comp_path = era_dir / "companions.yaml"
                if era_comp_path.exists():
                    with open(era_comp_path, encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                    era_comps = data.get("companions", []) if isinstance(data, dict) else []
                    for c in era_comps:
                        if isinstance(c, dict) and c.get("id"):
                            if c["id"] not in seen_ids:
                                all_comps.append(c)
                                seen_ids.add(c["id"])
                            else:
                                # Merge era-pack fields into existing companion
                                for existing in all_comps:
                                    if existing.get("id") == c["id"]:
                                        for key in ("enables_affordances", "blocks_affordances",
                                                     "influence", "banter", "recruitment",
                                                     "role_in_party", "voice", "personal_quest_id"):
                                            if key in c and key not in existing:
                                                existing[key] = c[key]
                                        break
        cached = set_cache_value(_COMPANIONS_CACHE_KEY, all_comps)

    if not era:
        return cached
    # Filter: companions with no era field are available to all eras
    era_upper = era.upper()
    return [c for c in cached if not c.get("era") or str(c["era"]).upper() == era_upper]


def clear_companions_cache() -> None:
    """Clear cached companions (useful for tests)."""
    clear_cache(_COMPANIONS_CACHE_KEY)


def get_companion_by_id(comp_id: str) -> dict[str, Any] | None:
    """Return companion definition by id, or None."""
    for c in load_companions():
        if c.get("id") == comp_id:
            return c
    return None


def recruit_companion(
    world_state: dict[str, Any],
    comp_id: str,
) -> bool:
    """Add a companion to the party by ID. Returns True if recruited, False if already in party or unknown.

    Called when an NPC matching a companion definition reaches ALLY affinity threshold,
    or when a recruitment event triggers during gameplay.
    """
    comp = get_companion_by_id(comp_id)
    if not comp:
        return False
    party = world_state.get("party") or []
    if comp_id in party:
        return False
    party.append(comp_id)
    world_state["party"] = party
    world_state.setdefault("party_affinity", {})[comp_id] = int(comp.get("default_affinity", 0))
    world_state.setdefault("party_traits", {})[comp_id] = dict(comp.get("traits") or {})
    world_state.setdefault("loyalty_progress", {})[comp_id] = 0
    return True


def build_initial_companion_state(world_time_minutes: int = 0, era: str | None = None) -> dict[str, Any]:
    """Build companion/alignment/reputation state for new campaign.

    Party starts EMPTY. Companions are met and recruited organically through
    gameplay — via encounters, quests, and player choices. This avoids the
    'thrust into the middle' feeling of having unknown party members at start.
    """
    return {
        "campaign_start_world_time_minutes": world_time_minutes,
        "party": [],
        "party_affinity": {},
        "party_traits": {},
        "loyalty_progress": {},
        "alignment": {
            "light_dark": 0,
            "paragon_renegade": 0,
        },
        "faction_reputation": {},
        "news_feed": [],
        "banter_queue": [],
    }
