"""Simple authored passage engine (CoG-like)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from backend.app.core.mechanics_resolver import CheckConfig, resolve_check
from backend.app.models.turn_contract import Choice, ChoiceCost, Intent, Outcome, StateDelta


@dataclass
class PassageRuntime:
    pack_id: str
    episode_title: str
    passage_id: str
    mode: str


def load_episode(pack_id: str) -> dict[str, Any]:
    fp = Path("static/passages") / pack_id / "episode_01.yml"
    data = yaml.safe_load(fp.read_text(encoding="utf-8"))
    return data


def _get_value(state: dict[str, Any], key: str) -> Any:
    if key in state:
        return state[key]
    flags = state.get("flags") or {}
    if key in flags:
        return flags[key]
    return None


def predicate_ok(pred: dict[str, Any], state: dict[str, Any]) -> bool:
    op = pred.get("op")
    key = pred.get("key")
    expected = pred.get("value")
    value = _get_value(state, key)
    if op == "truthy":
        return bool(value)
    if op == "falsy":
        return not bool(value)
    if op == "==":
        return value == expected
    if op == "!=":
        return value != expected
    if op == ">=":
        return (value or 0) >= expected
    if op == "<=":
        return (value or 0) <= expected
    if op == ">":
        return (value or 0) > expected
    if op == "<":
        return (value or 0) < expected
    if op == "contains":
        return expected in (value or [])
    if op == "in":
        return value in (expected or [])
    return False


def render_template(template: str, vars_map: dict[str, Any]) -> str:
    out = template
    if_blocks = re.findall(r"\{% if ([^%]+) %\}(.*?)\{% endif %\}", out, re.S)
    for cond, body in if_blocks:
        keep = bool(_get_value(vars_map, cond.strip()))
        marker = f"{{% if {cond} %}}{body}{{% endif %}}"
        out = out.replace(marker, body if keep else "")
    for key, val in vars_map.items():
        out = out.replace("{{" + key + "}}", str(val))
    return out.strip()


def choice_available(choice: dict[str, Any], state: dict[str, Any]) -> bool:
    reqs = choice.get("requirements") or []
    return all(predicate_ok(pred, state) for pred in reqs)


def build_choices(passage: dict[str, Any], state: dict[str, Any]) -> list[Choice]:
    built: list[Choice] = []
    for idx, c in enumerate((passage.get("choices") or [])[:4]):
        req_met = choice_available(c, state)
        if not req_met:
            continue
        built.append(
            Choice(
                id=c.get("id") or f"choice_{idx+1}",
                label=(c.get("label", "Continue") or "Continue")[:80],
                intent=Intent(intent_type="PASSAGE", target_ids={"passage_id": c.get("next", "")}, params={}),
                risk="med",
                cost=ChoiceCost(time_minutes=((c.get("cost") or {}).get("time_minutes") or 5)),
                requirements_met=req_met,
            )
        )

    # TurnContract requires 2..4 choices. Synthesize deterministic fallbacks when passage authoring
    # provides fewer than 2 options after requirement filtering.
    if len(built) < 2:
        built.append(
            Choice(
                id="passage_safe",
                label="Observe and gather intel",
                intent=Intent(intent_type="INVESTIGATE", target_ids={}, params={"posture": "safe"}),
                risk="low",
                cost=ChoiceCost(time_minutes=4),
                requirements_met=True,
            )
        )
    if len(built) < 2:
        built.append(
            Choice(
                id="passage_push",
                label="Force the pace forward",
                intent=Intent(intent_type="PASSAGE", target_ids={"passage_id": passage.get("id", "")}, params={"posture": "risky"}),
                risk="high",
                cost=ChoiceCost(time_minutes=8, heat=1),
                requirements_met=True,
            )
        )
    return built[:4]


def apply_choice(episode: dict[str, Any], passage_id: str, choice_id: str, state: dict[str, Any]) -> tuple[str, Outcome, StateDelta]:
    passage = (episode.get("passages") or {}).get(passage_id) or {}
    choice = next((c for c in (passage.get("choices") or []) if c.get("id") == choice_id), None)
    if not choice:
        raise ValueError(f"Unknown choice_id {choice_id}")
    flags = state.setdefault("flags", {})
    for k, v in (choice.get("set_flags") or {}).items():
        flags[k] = v

    out = Outcome(category="SUCCESS", consequences=["Passage advanced."], tags=[])
    delta = StateDelta(time_minutes=((choice.get("cost") or {}).get("time_minutes") or 5), flags_set=dict(choice.get("set_flags") or {}))
    nxt = choice.get("next", "")
    check = choice.get("check")
    if check:
        resolved = resolve_check(CheckConfig(skill=check["skill"], dc=int(check["dc"]), advantage=bool(check.get("advantage")), disadvantage=bool(check.get("disadvantage"))))
        out = resolved
        nxt = choice.get("on_success_next") if resolved.category in {"SUCCESS", "CRIT_SUCCESS", "PARTIAL"} else choice.get("on_fail_next")
    nxt = nxt or choice.get("next")
    if isinstance(nxt, str) and nxt.startswith("PASSAGE:"):
        return nxt.split(":", 1)[1], out, delta
    if isinstance(nxt, str) and nxt.startswith("SIM_SCENE:"):
        delta.flags_set["pending_sim_scene"] = nxt.split(":", 1)[1]
        return passage_id, out, delta
    return passage_id, out, delta
