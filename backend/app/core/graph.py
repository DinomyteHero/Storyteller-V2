"""LangGraph pipeline: input GameState -> updated GameState with final_text and suggested_actions.
Clock-Tick: WorldSimNode before Director."""
from __future__ import annotations

import os
import sqlite3
from typing import Any

from langgraph.graph import END, StateGraph
from backend.app.models.state import GameState
from backend.app.core.nodes import dict_to_state, state_to_dict
from backend.app.core.nodes.router import meta_node, router_node
from backend.app.core.nodes.mechanic import make_mechanic_node
from backend.app.core.nodes.encounter import make_encounter_node
from backend.app.core.nodes.world_sim import make_world_sim_node
from backend.app.core.nodes.companion import companion_reaction_node
from backend.app.core.nodes.arc_planner import arc_planner_node
from backend.app.core.nodes.scene_frame import scene_frame_node
from backend.app.core.nodes.director import make_director_node
from backend.app.core.nodes.narrator import make_narrator_node
from backend.app.core.nodes.narrative_validator import narrative_validator_node
from backend.app.core.nodes.suggestion_refiner import make_suggestion_refiner_node
from backend.app.core.nodes.commit import make_commit_node
# Lazy singleton: compiled on first use so module import is side-effect-free.
# The compiled graph contains no connection references -- conn is injected via
# state["__runtime_conn"] at each invocation so there is no stale-capture risk.
_COMPILED_GRAPH: Any = None


def build_graph() -> StateGraph:
    """Build the LangGraph pipeline (connection-agnostic).

    Nodes that need DB access read ``state["__runtime_conn"]`` at invocation
    time rather than capturing a connection in their closure. This key holds a
    non-serializable runtime handle and MUST NOT be persisted or checkpointed.

    Topology:
        router -> (META->commit | TALK->encounter->... | ACTION->mechanic->encounter->...->commit) -> END.
        Full ACTION path: router->mechanic->encounter->world_sim->companion_reaction->arc_planner->scene_frame->director->narrator->narrative_validator->suggestion_refiner->commit.
    """
    graph = StateGraph(dict)

    graph.add_node("router", router_node)
    graph.add_node("meta", meta_node)
    graph.add_node("mechanic", make_mechanic_node())
    graph.add_node("encounter", make_encounter_node())
    graph.add_node("world_sim", make_world_sim_node())
    graph.add_node("companion_reaction", companion_reaction_node)
    graph.add_node("arc_planner", arc_planner_node)
    graph.add_node("scene_frame", scene_frame_node)
    graph.add_node("director", make_director_node())
    graph.add_node("narrator", make_narrator_node())
    graph.add_node("narrative_validator", narrative_validator_node)
    graph.add_node("suggestion_refiner", make_suggestion_refiner_node())
    graph.add_node("commit", make_commit_node())

    graph.set_entry_point("router")

    def router_edges(s):
        intent = s.get("intent")
        if intent == "META":
            return "meta"
        if intent == "TALK":
            return "encounter"
        return "mechanic"

    graph.add_conditional_edges(
        "router",
        router_edges,
        {"meta": "meta", "encounter": "encounter", "mechanic": "mechanic"},
    )
    graph.add_edge("meta", "commit")
    graph.add_edge("mechanic", "encounter")
    graph.add_edge("encounter", "world_sim")
    graph.add_edge("world_sim", "companion_reaction")
    graph.add_edge("companion_reaction", "arc_planner")
    graph.add_edge("arc_planner", "scene_frame")
    graph.add_edge("scene_frame", "director")
    graph.add_edge("director", "narrator")
    graph.add_edge("narrator", "narrative_validator")
    graph.add_edge("narrative_validator", "suggestion_refiner")
    graph.add_edge("suggestion_refiner", "commit")
    graph.add_edge("commit", END)

    return graph


def _get_compiled_graph():
    """Return the compiled LangGraph, building it on first call (lazy singleton)."""
    global _COMPILED_GRAPH
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return build_graph().compile()
    if _COMPILED_GRAPH is None:
        _COMPILED_GRAPH = build_graph().compile()
    return _COMPILED_GRAPH


def run_turn(conn: sqlite3.Connection, state: GameState) -> GameState:
    """Run the compiled graph for one turn; return updated GameState with final_text and suggested_actions.

    The DB connection is injected into the state dict as ``__runtime_conn`` so that nodes which
    need it (encounter, world_sim, commit) can read it at invocation time without the graph
    capturing a stale connection in closures. This key is a non-serializable runtime handle and
    MUST NOT be persisted or checkpointed. It is stripped from the result before converting back
    to GameState.
    """
    import logging
    import time

    _logger = logging.getLogger(__name__)
    initial = state_to_dict(state)
    initial["__runtime_conn"] = conn
    t0 = time.monotonic()
    result = _get_compiled_graph().invoke(initial)
    elapsed = time.monotonic() - t0
    result.pop("__runtime_conn", None)
    _logger.info(
        "Turn completed in %.2fs (campaign=%s, turn=%d, intent=%s)",
        elapsed,
        state.campaign_id or "unknown",
        state.turn_number or 0,
        state.intent or "unknown",
    )
    return dict_to_state(result)
