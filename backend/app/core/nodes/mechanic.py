"""Mechanic node factory."""
from __future__ import annotations

from typing import Any

from backend.app.core.agents import MechanicAgent
from backend.app.models.state import MechanicOutput
from backend.app.time_economy import DIALOGUE_ONLY_MINUTES
from backend.app.core.nodes import dict_to_state


def make_mechanic_node():
    """Factory: mechanic node is conn-free (pure deterministic logic)."""
    mechanic = MechanicAgent()

    def mechanic_node(state: dict[str, Any]) -> dict[str, Any]:
        intent = state.get("intent")
        if intent == "ACTION":
            gs = dict_to_state(state)
            result = mechanic.resolve(gs)
            return {**state, "mechanic_result": result.model_dump(mode="json")}
        return {
            **state,
            "mechanic_result": MechanicOutput(
                action_type="TALK", events=[], narrative_facts=[], time_cost_minutes=DIALOGUE_ONLY_MINUTES
            ).model_dump(mode="json"),
        }

    return mechanic_node
