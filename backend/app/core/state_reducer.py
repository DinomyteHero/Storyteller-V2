"""Deterministic state reducer for rehydrating state from events. No LLM calls."""

import copy
from typing import Any


# Canonical state dict shape (for type hints / documentation)
# state = {
#   "campaign": {"id": str, "world_flags": dict},
#   "characters": {character_id: {"location_id": str|None, "hp_current": int, "stats": dict, "relationship_score": int|None, "role": str, "name": str}},
#   "inventory": {owner_id: {item_name: {"quantity": int, "attributes": dict}}},
#   "turn_number": int,
#   "unhandled_events": list[dict],  # optional, for unknown event types
# }


def initial_state() -> dict:
    """Return empty canonical state (campaign, characters, inventory, turn_number)."""
    return {
        "campaign": {"id": "", "world_flags": {}},
        "characters": {},
        "inventory": {},
        "turn_number": 0,
    }


def _ensure_character(state: dict, character_id: str) -> None:
    """Ensure state["characters"][character_id] exists with default fields."""
    if character_id not in state["characters"]:
        state["characters"][character_id] = {
            "location_id": None,
            "hp_current": 0,
            "stats": {},
            "relationship_score": None,
            "role": "",
            "name": "",
        }


def _ensure_inventory_entry(state: dict, owner_id: str, item_name: str, attributes: dict) -> None:
    """Ensure state['inventory'][owner_id][item_name] exists."""
    if owner_id not in state["inventory"]:
        state["inventory"][owner_id] = {}
    if item_name not in state["inventory"][owner_id]:
        state["inventory"][owner_id][item_name] = {"quantity": 0, "attributes": attributes}


def apply_event(state: dict, event: dict) -> dict:
    """Apply a single event to state. Returns a NEW dict; does not mutate input.

    event: dict with "event_type" and "payload".
    Unknown event types are appended to state["unhandled_events"].
    """
    state = copy.deepcopy(state)
    if "unhandled_events" not in state:
        state["unhandled_events"] = []

    event_type = event.get("event_type", "")
    payload = event.get("payload") or {}

    if event_type == "MOVE":
        cid = payload.get("character_id")
        to_loc = payload.get("to_location")
        if cid is not None:
            _ensure_character(state, cid)
            state["characters"][cid]["location_id"] = to_loc

    elif event_type == "DAMAGE":
        cid = payload.get("character_id")
        amount = payload.get("amount", 0)
        if cid is not None and isinstance(amount, (int, float)):
            _ensure_character(state, cid)
            state["characters"][cid]["hp_current"] = max(
                0,
                state["characters"][cid]["hp_current"] - int(amount),
            )

    elif event_type == "HEAL":
        cid = payload.get("character_id")
        amount = payload.get("amount", 0)
        if cid is not None and isinstance(amount, (int, float)):
            _ensure_character(state, cid)
            state["characters"][cid]["hp_current"] = (
                state["characters"][cid]["hp_current"] + int(amount)
            )

    elif event_type in ("ITEM_GET", "ITEM_LOSE"):
        owner_id = payload.get("owner_id")
        item_name = payload.get("item_name")
        quantity_delta = payload.get("quantity_delta", 0)
        attributes = payload.get("attributes") or {}
        if event_type == "ITEM_LOSE":
            quantity_delta = -abs(quantity_delta) if quantity_delta else 0
        elif event_type == "ITEM_GET":
            quantity_delta = abs(quantity_delta) if quantity_delta else 0
        if owner_id is not None and item_name is not None:
            _ensure_inventory_entry(state, owner_id, item_name, attributes)
            state["inventory"][owner_id][item_name]["quantity"] += quantity_delta
            if state["inventory"][owner_id][item_name]["quantity"] <= 0:
                del state["inventory"][owner_id][item_name]
                if not state["inventory"][owner_id]:
                    del state["inventory"][owner_id]

    elif event_type == "FLAG_SET":
        key = payload.get("key")
        value = payload.get("value")
        if key is not None:
            state["campaign"]["world_flags"][str(key)] = value

    elif event_type == "RELATIONSHIP":
        npc_id = payload.get("npc_id")
        delta = payload.get("delta", 0)
        if npc_id is not None and isinstance(delta, (int, float)):
            _ensure_character(state, npc_id)
            current = state["characters"][npc_id]["relationship_score"]
            if current is None:
                current = 0
            state["characters"][npc_id]["relationship_score"] = current + int(delta)

    else:
        state["unhandled_events"].append(event)

    return state


def reduce_events(state: dict, events: list[dict]) -> dict:
    """Fold a list of events into state. Returns a new state; does not mutate input."""
    for event in events:
        state = apply_event(state, event)
    return state
