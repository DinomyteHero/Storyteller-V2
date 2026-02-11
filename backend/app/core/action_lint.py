"""Deterministic linting for suggested actions."""
from __future__ import annotations

import logging
import re
from typing import Any

from backend.app.constants import SUGGESTED_ACTIONS_TARGET
from backend.app.models.state import (
    ActionSuggestion,
    ACTION_CATEGORY_SOCIAL,
    ACTION_CATEGORY_EXPLORE,
    ACTION_CATEGORY_COMMIT,
    ACTION_RISK_SAFE,
    STRATEGY_TAG_OPTIMAL,
    STRATEGY_TAG_ALTERNATIVE,
    TONE_TAG_PARAGON,
    TONE_TAG_INVESTIGATE,
    TONE_TAG_RENEGADE,
    TONE_TAG_NEUTRAL,
    ROUTER_ROUTE_TALK,
    ROUTER_ACTION_CLASS_DIALOGUE_ONLY,
)

logger = logging.getLogger(__name__)

_TALKY_VERBS = (
    "talk",
    "ask",
    "speak",
    "say",
    "tell",
    "question",
    "persuade",
    "convince",
    "negotiate",
    "listen",
    "greet",
    "explain",
)

_CHARACTER_VERBS = (
    "talk",
    "ask",
    "speak",
    "say",
    "tell",
    "question",
    "persuade",
    "convince",
    "threaten",
    "interrogate",
    "bribe",
    "charm",
    "attack",
    "help",
    "follow",
    "give",
    "trade",
    "barter",
    "hire",
)

_TRAVEL_VERBS = (
    "travel",
    "leave",
    "exit",
    "escape",
    "retreat",
    "flee",
    "run away",
    "depart",
    "go to",
    "head to",
    "move to",
)

_ITEM_VERBS = (
    "equip",
    "draw",
    "reload",
    "wear",
    "wield",
    "activate",
    "apply",
    "drink",
    "eat",
    "throw",
    "use",
)


def lint_actions(
    actions: list[ActionSuggestion | dict],
    game_state: Any | None = None,
    router_output: Any | None = None,
    mechanic_output: Any | None = None,
    encounter_context: dict | None = None,
) -> tuple[list[ActionSuggestion], list[str]]:
    """Lint suggested actions for mechanical consistency. Returns (actions, lint_notes)."""
    normalized: list[ActionSuggestion] = []
    notes: list[str] = []

    for a in (actions or []):
        if isinstance(a, ActionSuggestion):
            normalized.append(a)
        elif isinstance(a, dict):
            try:
                normalized.append(ActionSuggestion.model_validate(a))
            except Exception as e:
                logger.debug("ActionLint: failed to normalize action payload: %s", e)
                notes.append("dropped invalid action payload")
        else:
            notes.append("dropped invalid action payload")

    present_names = _present_npc_names(game_state)
    inventory_names = _inventory_item_names(game_state)
    talk_only = _is_talk_only(game_state, router_output)
    in_combat = _is_combat(mechanic_output, encounter_context)

    kept: list[ActionSuggestion] = []
    removed_by_reason = {
        "character": 0,
        "item": 0,
        "talk": 0,
        "combat": 0,
    }

    for action in normalized:
        label_text = str(action.label or "")
        text = _action_text(action)
        if _references_missing_character(label_text, present_names):
            removed_by_reason["character"] += 1
            continue
        if _uses_missing_item(text, inventory_names):
            removed_by_reason["item"] += 1
            continue
        if talk_only and not _is_talky(action):
            removed_by_reason["talk"] += 1
            continue
        if in_combat and _is_travel_action(text):
            removed_by_reason["combat"] += 1
            continue
        kept.append(action)

    if len(kept) > SUGGESTED_ACTIONS_TARGET:
        kept = kept[:SUGGESTED_ACTIONS_TARGET]

    padded, pad_count = _pad_to_target(kept, target=SUGGESTED_ACTIONS_TARGET, game_state=game_state)
    kept = padded

    removed_total = sum(removed_by_reason.values())
    if removed_total > 0:
        parts = []
        for key, count in removed_by_reason.items():
            if count:
                parts.append(f"{key}={count}")
        detail = f" ({', '.join(parts)})" if parts else ""
        notes.append(f"removed {removed_total} invalid actions{detail}")
    if pad_count > 0:
        notes.append(f"padded with safe options (added {pad_count})")

    return kept, notes


def _present_npc_names(game_state: Any | None) -> set[str]:
    names: set[str] = set()
    if game_state is None:
        return names
    present = _get_field(game_state, "present_npcs", []) or []
    if isinstance(present, list):
        for npc in present:
            name = None
            if isinstance(npc, dict):
                name = npc.get("name")
            else:
                name = getattr(npc, "name", None)
            if name:
                full = str(name).strip()
                if full:
                    names.add(full.lower())
                    # Also allow parts of multi-word names (e.g., "Lando" from "Lando Calrissian")
                    for part in full.split():
                        if len(part) >= 3:
                            names.add(part.lower())
    return names


def _inventory_item_names(game_state: Any | None) -> set[str]:
    items: set[str] = set()
    if game_state is None:
        return items
    player = _get_field(game_state, "player", None)
    inventory = None
    if isinstance(player, dict):
        inventory = player.get("inventory")
    elif player is not None:
        inventory = getattr(player, "inventory", None)
    for item in (inventory or []):
        if isinstance(item, dict):
            name = item.get("item_name")
        else:
            name = getattr(item, "item_name", None)
        if name:
            items.add(str(name).lower())
    return items


def _is_talk_only(game_state: Any | None, router_output: Any | None) -> bool:
    route = None
    action_class = None
    intent = None
    if router_output is None and game_state is not None:
        router_output = _get_field(game_state, "router_output", None)
    if router_output is not None:
        if isinstance(router_output, dict):
            route = router_output.get("route")
            action_class = router_output.get("action_class")
        else:
            route = getattr(router_output, "route", None)
            action_class = getattr(router_output, "action_class", None)
    if game_state is not None:
        intent = _get_field(game_state, "intent", None)
    return (
        intent == "TALK"
        or (route == ROUTER_ROUTE_TALK and action_class == ROUTER_ACTION_CLASS_DIALOGUE_ONLY)
    )


def _is_combat(mechanic_output: Any | None, encounter_context: dict | None) -> bool:
    if encounter_context and encounter_context.get("in_combat"):
        return True
    if mechanic_output is None:
        return False
    action_type = None
    events = None
    if isinstance(mechanic_output, dict):
        action_type = mechanic_output.get("action_type")
        events = mechanic_output.get("events") or []
    else:
        action_type = getattr(mechanic_output, "action_type", None)
        events = getattr(mechanic_output, "events", None) or []
    if (action_type or "").upper() in ("ATTACK", "COMBAT"):
        return True
    for ev in events:
        t = ev.get("event_type") if isinstance(ev, dict) else getattr(ev, "event_type", "")
        if (t or "").upper() == "DAMAGE":
            return True
    return False


def _action_text(action: ActionSuggestion) -> str:
    return f"{action.label} {action.intent_text}".strip()


def _is_talky(action: ActionSuggestion) -> bool:
    if action.category == ACTION_CATEGORY_SOCIAL:
        return True
    text = _action_text(action).lower()
    return any(v in text for v in _TALKY_VERBS)


def _is_travel_action(text: str) -> bool:
    lower = text.lower()
    return any(v in lower for v in _TRAVEL_VERBS)


def _references_missing_character(text: str, present_names: set[str]) -> bool:
    if not present_names:
        return False
    if not text or not text.strip():
        return False
    lower = text.lower()
    if not any(v in lower for v in _CHARACTER_VERBS):
        return False
    # If any present name token is mentioned, assume it is valid.
    if any(name and name in lower for name in present_names):
        return False

    # Only drop when the label explicitly targets a *named* character after an interaction verb.
    # Avoid false positives from capitalized words in dialogue quotes (e.g., "Maybe", "What", "Enough").
    m = re.search(
        r"\b(?:talk\s+(?:to|with)|speak\s+(?:to|with)|ask|question|press|confront|threaten|help|follow|show|thank)\s+"
        r"([A-Z][A-Za-z0-9'-]+(?:\s+[A-Z][A-Za-z0-9'-]+){0,2})",
        text,
    )
    if not m:
        return False
    candidate = m.group(1).strip().lower()
    if not candidate:
        return False
    if candidate in present_names:
        return False
    # Don't flag generic role references like "the scholar", "the bartender", "the pilot"
    # These are valid scene descriptions, not hallucinated character names.
    _GENERIC_PREFIXES = {"the ", "a ", "an ", "some ", "that ", "this "}
    if any(candidate.startswith(p) for p in _GENERIC_PREFIXES):
        return False
    parts = [p for p in candidate.split() if p]
    return not any(p in present_names for p in parts)


def _uses_missing_item(text: str, inventory_names: set[str]) -> bool:
    if not inventory_names:
        # If inventory is empty, only flag explicit item usage.
        return _explicit_item_reference(text)
    lower = text.lower()
    if any(name in lower for name in inventory_names):
        return False
    # If no inventory item name appears but action explicitly references an item, drop it.
    return _explicit_item_reference(text)


def _explicit_item_reference(text: str) -> bool:
    lower = text.lower()
    if not any(v in lower for v in _ITEM_VERBS):
        return False
    # Look for a quoted or possessive item reference after item verbs.
    if re.search(r'("|\')\w.+?("|\')', text):
        return True
    if re.search(r"\bmy\s+[A-Za-z][A-Za-z0-9- ]+", text, flags=re.I):
        return True
    if re.search(r"\b(?:%s)\b[^\n]{0,30}\b([A-Z][A-Za-z0-9-]+)" % "|".join(_ITEM_VERBS), text):
        return True
    return False


def _proper_nouns(text: str) -> set[str]:
    nouns = set(re.findall(r"\b[A-Z][a-z]{2,}\b", text))
    stop = set(_CHARACTER_VERBS) | set(_TALKY_VERBS) | {"the", "this", "that"}
    out = set()
    for n in nouns:
        if n.lower() in stop:
            continue
        out.add(n.lower())
    return out


def _contextual_defaults(game_state: Any | None) -> list[ActionSuggestion]:
    """Build context-aware fallback suggestions using location and NPC names."""
    npc_name = None
    loc_name = "the area"
    if game_state is not None:
        present = _get_field(game_state, "present_npcs", []) or []
        if isinstance(present, list):
            for npc in present:
                name = npc.get("name") if isinstance(npc, dict) else getattr(npc, "name", None)
                if name:
                    npc_name = str(name)
                    break
        loc_raw = _get_field(game_state, "current_location", None)
        if loc_raw and isinstance(loc_raw, str):
            # Simple humanization: strip loc- prefix, replace hyphens
            cleaned = loc_raw
            for prefix in ("loc-", "loc_"):
                if cleaned.lower().startswith(prefix):
                    cleaned = cleaned[len(prefix):]
                    break
            cleaned = cleaned.replace("-", " ").replace("_", " ").strip()
            if cleaned:
                loc_name = f"the {cleaned}" if " " not in cleaned else cleaned

    social_label = f"Ask {npc_name} about the situation" if npc_name else "Talk to someone nearby"
    social_intent = f"Say: 'What can you tell me about what's going on here?'" if npc_name else "Say: 'I'm looking for information. Can anyone help?'"
    return [
        # SOCIAL — contextual
        ActionSuggestion(
            label=social_label,
            intent_text=social_intent,
            category=ACTION_CATEGORY_SOCIAL,
            risk_level=ACTION_RISK_SAFE,
            strategy_tag=STRATEGY_TAG_ALTERNATIVE,
            tone_tag=TONE_TAG_PARAGON,
            intent_style="calm",
            consequence_hint=f"may learn something from {npc_name}" if npc_name else "may gain trust",
        ),
        # EXPLORE — observe the scene (1.3: guaranteed passive option)
        ActionSuggestion(
            label="Wait and observe",
            intent_text=f"Take a moment to watch and listen, absorbing the details of {loc_name} before acting.",
            category=ACTION_CATEGORY_EXPLORE,
            risk_level=ACTION_RISK_SAFE,
            strategy_tag=STRATEGY_TAG_ALTERNATIVE,
            tone_tag=TONE_TAG_INVESTIGATE,
            intent_style="patient",
            consequence_hint="notice something others missed",
        ),
        # COMMIT — contextual
        ActionSuggestion(
            label=f"Head deeper into {loc_name}",
            intent_text=f"Move further into {loc_name} with purpose.",
            category=ACTION_CATEGORY_COMMIT,
            risk_level=ACTION_RISK_SAFE,
            strategy_tag=STRATEGY_TAG_ALTERNATIVE,
            tone_tag=TONE_TAG_RENEGADE,
            intent_style="firm",
            consequence_hint="may trigger a new encounter",
        ),
        # EXPLORE — survey surroundings
        ActionSuggestion(
            label=f"Survey {loc_name}",
            intent_text=f"Study the layout of {loc_name}, noting exits and anything unusual.",
            category=ACTION_CATEGORY_EXPLORE,
            risk_level=ACTION_RISK_SAFE,
            strategy_tag=STRATEGY_TAG_OPTIMAL,
            tone_tag=TONE_TAG_INVESTIGATE,
            intent_style="probing",
            consequence_hint="spot something others missed",
        ),
    ]


def _pad_to_target(actions: list[ActionSuggestion], target: int = SUGGESTED_ACTIONS_TARGET, game_state: Any | None = None) -> tuple[list[ActionSuggestion], int]:
    target = int(target) if isinstance(target, int) else SUGGESTED_ACTIONS_TARGET
    target = max(1, target)
    if len(actions) >= target:
        return actions[:target], 0
    defaults = _contextual_defaults(game_state)
    out = list(actions)
    has_alt = any(a.strategy_tag == STRATEGY_TAG_ALTERNATIVE for a in out)
    existing_labels = {str(a.label or "").strip().lower() for a in out}
    existing_intents = {str(a.intent_text or "").strip().lower() for a in out}

    def _try_add(d: ActionSuggestion) -> bool:
        nonlocal has_alt
        label_key = str(d.label or "").strip().lower()
        intent_key = str(d.intent_text or "").strip().lower()
        if not label_key or not intent_key:
            return False
        if label_key in existing_labels or intent_key in existing_intents:
            return False
        strategy = d.strategy_tag
        if not has_alt:
            strategy = STRATEGY_TAG_ALTERNATIVE
            has_alt = True
        out.append(
            ActionSuggestion(
                label=d.label,
                intent_text=d.intent_text,
                category=d.category,
                risk_level=d.risk_level,
                strategy_tag=strategy,
                tone_tag=d.tone_tag,
                intent_style=d.intent_style,
                consequence_hint=d.consequence_hint,
            )
        )
        existing_labels.add(label_key)
        existing_intents.add(intent_key)
        return True

    # Ensure at least one of each core category exists.
    required = (ACTION_CATEGORY_SOCIAL, ACTION_CATEGORY_EXPLORE, ACTION_CATEGORY_COMMIT)
    present = {a.category for a in out}
    for cat in required:
        if len(out) >= target:
            break
        if cat in present:
            continue
        for d in defaults:
            if d.category == cat and _try_add(d):
                present.add(cat)
                break

    for d in defaults:
        if len(out) >= target:
            break
        _try_add(d)

    return out[:target], max(0, len(out[:target]) - len(actions))


def _get_field(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
