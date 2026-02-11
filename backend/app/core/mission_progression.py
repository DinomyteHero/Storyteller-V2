"""Deterministic scene budget + objective progression."""
from __future__ import annotations

from typing import Any


def ensure_scene_and_objectives(world_state: dict[str, Any]) -> dict[str, Any]:
    ws = dict(world_state or {})
    ws.setdefault("scene", {})
    scene = ws["scene"] if isinstance(ws["scene"], dict) else {}
    scene.setdefault("scene_id", "scene-1")
    scene.setdefault("beats_remaining", 4)
    ws["scene"] = scene
    objectives = ws.get("active_objectives")
    if not isinstance(objectives, list) or not objectives:
        ws["active_objectives"] = [
            {
                "id": "obj-main-1",
                "description": "Secure leverage in the current sector.",
                "success_conditions": ["Find one actionable clue", "Survive the scene"],
                "progress_state": "in_progress",
            }
        ]
    return ws


def advance_scene_budget(world_state: dict[str, Any], turn_number: int) -> tuple[dict[str, Any], str | None]:
    ws = ensure_scene_and_objectives(world_state)
    scene = ws.get("scene", {})
    beats_remaining = int(scene.get("beats_remaining", 4)) - 1
    next_scene_hint = None
    if beats_remaining <= 0:
        current_id = str(scene.get("scene_id") or "scene-1")
        prefix, _, n = current_id.rpartition("-")
        try:
            next_num = int(n) + 1
            next_id = f"{prefix or 'scene'}-{next_num}"
        except ValueError:
            next_id = f"scene-{turn_number + 1}"
        scene["scene_id"] = next_id
        scene["beats_remaining"] = 4
        next_scene_hint = "Scene transition triggered by beat budget."
    else:
        scene["beats_remaining"] = beats_remaining
    ws["scene"] = scene
    return ws, next_scene_hint


def apply_objective_progress(world_state: dict[str, Any], state_delta: dict[str, Any]) -> dict[str, Any]:
    ws = ensure_scene_and_objectives(world_state)
    objectives = list(ws.get("active_objectives") or [])
    objective_updates = list((state_delta or {}).get("objectives") or [])
    if objective_updates and objectives:
        # Mark first active objective complete deterministically when state delta reports objective update.
        for obj in objectives:
            if obj.get("progress_state") != "completed":
                obj["progress_state"] = "completed"
                obj.setdefault("reward", {"credits": 25})
                break
        # Add follow-up objective
        next_idx = len(objectives) + 1
        objectives.append(
            {
                "id": f"obj-main-{next_idx}",
                "description": "Follow up on newly unlocked lead.",
                "success_conditions": ["Act on the lead"],
                "progress_state": "in_progress",
            }
        )
    ws["active_objectives"] = objectives
    return ws
