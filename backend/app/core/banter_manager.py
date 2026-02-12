"""BanterManager: controlled micro-scene injection for companion banter.

Banter triggers ONLY at safe times:
  - During travel scenes
  - After turn resolution (not during high-alert/lockdown)

Banter is 1-3 lines max, with 0-2 optional player responses.
It must NOT interrupt high-alert or lockdown scenes.
"""
from __future__ import annotations

import logging
import random
from typing import Any

from backend.app.constants import (
    BANTER_POOL,
    BANTER_MEMORY_POOL,
    BANTER_COMPANION_COOLDOWN,
    BANTER_GLOBAL_COOLDOWN,
)

logger = logging.getLogger(__name__)


def _is_safe_for_banter(scene_frame: dict | None, world_state: dict | None) -> bool:
    """Check if the current scene is safe for banter injection.

    Banter is allowed during:
    - Travel scenes
    - Exploration scenes with Quiet alert
    - Dialogue scenes with Quiet alert and Low heat

    Banter is NOT allowed during:
    - Combat scenes
    - Stealth scenes
    - Any scene with Watchful or Lockdown alert
    - Any scene with Wanted heat
    """
    if not scene_frame:
        return False

    scene_type = (scene_frame.get("allowed_scene_type") or "").lower()
    pressure = scene_frame.get("pressure") or {}
    alert = (pressure.get("alert") or "Quiet").strip()
    heat = (pressure.get("heat") or "Low").strip()

    # Never banter during combat or stealth
    if scene_type in ("combat", "stealth"):
        return False

    # Never banter during high alert
    if alert in ("Watchful", "Lockdown"):
        return False

    # Never banter when Wanted
    if heat == "Wanted":
        return False

    # Travel and exploration are always safe (if alert is Quiet)
    if scene_type in ("travel", "exploration"):
        return True

    # Dialogue: only if both Quiet and Low
    if scene_type == "dialogue" and alert == "Quiet" and heat == "Low":
        return True

    return False


def _select_banter_companion(
    party_state: Any,
    turn_number: int,
    campaign_id: str = "",
) -> str | None:
    """Pick a companion for banter, respecting cooldowns."""
    if not party_state or not party_state.active_companions:
        return None

    eligible: list[str] = []
    for cid in party_state.active_companions:
        cs = party_state.get_companion_state(cid)
        if cs and (turn_number - cs.banter_last_turn) >= BANTER_COMPANION_COOLDOWN:
            eligible.append(cid)

    if not eligible:
        return None

    # Seeded RNG for deterministic selection
    from backend.app.world.npc_generator import derive_seed
    seed = derive_seed(campaign_id, turn_number, counter=99)
    rng = random.Random(seed)
    return rng.choice(eligible)


def maybe_inject_banter(
    state: dict[str, Any],
) -> tuple[dict[str, Any], dict | None]:
    """Attempt to inject a banter micro-scene into the state.

    Returns (updated_state, banter_dict_or_None).
    banter_dict has: {speaker, text, responses: [{text, tone}]}

    Called from companion_reaction_node AFTER main reactions.
    """
    scene_frame = state.get("scene_frame")
    campaign = state.get("campaign") or {}
    turn_number = int(state.get("turn_number") or 0)
    campaign_id = state.get("campaign_id", "")

    ws = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
    if not isinstance(ws, dict):
        return state, None

    if not _is_safe_for_banter(scene_frame, ws):
        return state, None

    # Check global cooldown
    last_banter_turn = int(ws.get("last_banter_turn") or 0)
    if (turn_number - last_banter_turn) < BANTER_GLOBAL_COOLDOWN:
        return state, None

    try:
        from backend.app.core.party_state import load_party_state
        party_st = load_party_state(ws)
    except Exception:
        return state, None

    comp_id = _select_banter_companion(party_st, turn_number, campaign_id)
    if not comp_id:
        return state, None

    # Get companion data for name/style
    from backend.app.core.companions import get_companion_by_id
    comp = get_companion_by_id(comp_id)
    if not comp:
        return state, None

    name = comp.get("name", "Companion")
    style = comp.get("banter_style") or (comp.get("banter") or {}).get("style", "stoic")

    # Build banter line
    from backend.app.world.npc_generator import derive_seed
    seed = derive_seed(campaign_id, turn_number, counter=88)
    rng = random.Random(seed)

    cs = party_st.get_companion_state(comp_id)
    influence = cs.influence if cs else 0
    memories = cs.memories if cs else []

    # Memory banter for high-influence companions with memories
    if memories and influence >= 30:
        pool = BANTER_MEMORY_POOL.get(style, BANTER_MEMORY_POOL.get("stoic", []))
        if pool:
            template = rng.choice(pool)
            text = template.format(name=name, memory=memories[-1][:60])
        else:
            text = f'{name} pauses, recalling {memories[-1][:60]}.'
    else:
        style_pool = BANTER_POOL.get(style, BANTER_POOL.get("stoic", {}))
        tone_lines = style_pool.get("NEUTRAL", [])
        if tone_lines:
            template = rng.choice(tone_lines)
            text = template.format(name=name)
        else:
            text = f'{name} watches quietly.'

    # Record banter turn on companion state
    if cs:
        cs.banter_last_turn = turn_number

    # Persist updated party_state and last_banter_turn
    from backend.app.core.party_state import save_party_state
    ws = dict(ws)
    ws["last_banter_turn"] = turn_number
    save_party_state(ws, party_st)
    campaign = dict(campaign)
    campaign["world_state_json"] = ws

    banter = {
        "speaker": name,
        "companion_id": comp_id,
        "text": text,
        "responses": [],  # 0-2 optional player responses (future)
    }

    # Append to banter_queue for narrator to reference
    banter_queue = list(campaign.get("banter_queue") or [])
    banter_queue.append({"speaker": name, "text": text})
    campaign["banter_queue"] = banter_queue

    state = {**state, "campaign": campaign}
    return state, banter
