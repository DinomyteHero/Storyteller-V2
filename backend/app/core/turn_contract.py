"""Build strict turn contract objects from pipeline state."""
from __future__ import annotations

from typing import Any

from backend.app.models.turn_contract import Choice, ChoiceCost, Intent, Outcome, StateDelta, TurnContract


RISK_MAP = {"SAFE": "low", "RISKY": "med", "DANGEROUS": "high"}


def derive_intent_from_text(text: str) -> Intent:
    low = (text or "").lower()
    intent_type = "INVESTIGATE"
    if any(k in low for k in ["talk", "ask", "say"]):
        intent_type = "TALK"
    elif any(k in low for k in ["move", "go", "travel"]):
        intent_type = "MOVE"
    elif any(k in low for k in ["attack", "fight", "shoot"]):
        intent_type = "FIGHT"
    elif any(k in low for k in ["sneak", "hide", "stealth"]):
        intent_type = "SNEAK"
    elif any(k in low for k in ["hack", "slice"]):
        intent_type = "HACK"
    return Intent(intent_type=intent_type, user_utterance=text, params={})


def choice_from_suggestion(index: int, suggestion: dict[str, Any]) -> Choice:
    intent = suggestion.get("intent")
    parsed_intent = Intent.model_validate(intent) if isinstance(intent, dict) else derive_intent_from_text(suggestion.get("intent_text") or suggestion.get("label") or "")
    return Choice(
        id=suggestion.get("id") or f"choice_{index+1}",
        label=suggestion.get("label") or f"Choice {index+1}",
        intent=parsed_intent,
        risk=RISK_MAP.get((suggestion.get("risk_level") or "SAFE").upper(), "med"),
        cost=ChoiceCost(time_minutes=int(suggestion.get("time_cost_minutes") or 5)),
    )


def build_turn_contract(state: dict[str, Any], next_scene_hint: str | None = None) -> TurnContract:
    mechanic = state.get("mechanic_result") or {}
    outcome = mechanic.get("outcome") or {"check": mechanic.get("action_type") or "NONE", "result": "PARTIAL"}
    state_delta = mechanic.get("state_delta") or {"time_minutes": int(mechanic.get("time_cost_minutes") or 0)}

    suggestions = list(state.get("suggested_actions") or [])
    choices = [choice_from_suggestion(i, s if isinstance(s, dict) else getattr(s, "model_dump", lambda **kw: {})()) for i, s in enumerate(suggestions[:4])]
    while len(choices) < 2:
        pad_idx = len(choices) + 1
        choices.append(
            Choice(
                id=f"fallback_{pad_idx}",
                label="Regroup and reassess",
                intent=Intent(intent_type="REST", params={}),
                risk="low",
                cost=ChoiceCost(time_minutes=5),
            )
        )

    scene_frame = state.get("scene_frame") or {}
    scene_goal = scene_frame.get("player_objective") or "Advance the current objective"
    obstacle = scene_frame.get("immediate_situation") or "Uncertain opposition"
    stakes = "Mission momentum, safety, and reputation"

    return TurnContract(
        scene_goal=scene_goal,
        obstacle=obstacle,
        stakes=stakes,
        choices=choices,
        outcome=Outcome.model_validate(outcome),
        state_delta=StateDelta.model_validate(state_delta),
        narration=state.get("final_text") or "",
        next_scene_hint=next_scene_hint,
    )
