"""LangGraph node helpers and shared utilities."""
from __future__ import annotations

from typing import Any

from backend.app.models.state import GameState


def state_to_dict(state: GameState) -> dict[str, Any]:
    """Convert GameState to dict for graph (include all keys for merging)."""
    return state.model_dump(mode="json")


def dict_to_state(data: dict[str, Any]) -> GameState:
    """Convert dict back to GameState."""
    return GameState.model_validate(data)
