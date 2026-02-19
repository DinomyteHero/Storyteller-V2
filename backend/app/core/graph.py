"""LangGraph pipeline: input GameState -> updated GameState with final_text and suggested_actions.
Clock-Tick: WorldSimNode before Director."""
from __future__ import annotations

import os
import sqlite3
import time
from typing import Any

from langgraph.graph import END, StateGraph
from backend.app.models.state import GameState
from backend.app.core.nodes import dict_to_state, state_to_dict
from backend.app.core.nodes.router import meta_node, router_node
from backend.app.core.nodes.mechanic import make_mechanic_node
from backend.app.core.nodes.encounter import make_encounter_node
from backend.app.core.nodes.world_sim import make_world_sim_node
from backend.app.core.nodes.companion import companion_reaction_node
from backend.app.core.nodes.moments import moments_node
from backend.app.core.nodes.arc_planner import arc_planner_node
from backend.app.core.nodes.scene_frame import scene_frame_node
from backend.app.core.nodes.director import make_director_node
from backend.app.core.nodes.narrator import make_narrator_node
from backend.app.core.nodes.narrative_validator import narrative_validator_node
from backend.app.core.nodes.choice_crafter_node import make_choice_crafter_node
from backend.app.core.nodes.commit import make_commit_node
from backend.app.core.agents.base import get_llm_timings, reset_llm_timings
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
        Full ACTION path: router->mechanic->encounter->world_sim->companion_reaction->moments->arc_planner->scene_frame->director->narrator->narrative_validator->choice_crafter->commit.
    """
    graph = StateGraph(dict)

    graph.add_node("router", router_node)
    graph.add_node("meta", meta_node)
    graph.add_node("mechanic", make_mechanic_node())
    graph.add_node("encounter", make_encounter_node())
    graph.add_node("world_sim", make_world_sim_node())
    graph.add_node("companion_reaction", companion_reaction_node)
    graph.add_node("moments", moments_node)
    graph.add_node("arc_planner", arc_planner_node)
    graph.add_node("scene_frame", scene_frame_node)
    graph.add_node("director", make_director_node())
    graph.add_node("narrator", make_narrator_node())
    graph.add_node("narrative_validator", narrative_validator_node)
    graph.add_node("choice_crafter", make_choice_crafter_node())
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
    graph.add_edge("companion_reaction", "moments")
    graph.add_edge("moments", "arc_planner")
    graph.add_edge("arc_planner", "scene_frame")
    graph.add_edge("scene_frame", "director")
    graph.add_edge("director", "narrator")
    graph.add_edge("narrator", "narrative_validator")
    graph.add_edge("narrative_validator", "choice_crafter")
    graph.add_edge("choice_crafter", "commit")
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


def get_pipeline_steps(intent: str) -> list[tuple[str, Any]]:
    """Return the canonical ordered list of (name, node_fn) for a given intent.

    This is the SINGLE SOURCE OF TRUTH for pipeline topology. Both the
    non-streaming path (`_run_pipeline_with_timings`) and the streaming path
    (`_run_pre_narrator_pipeline` / `_run_post_narrator_pipeline`) MUST use
    this function to ensure they stay in sync when new nodes are added.

    Returns:
        List of (node_name, node_function) tuples in execution order.
    """
    if intent == "META":
        return [
            ("meta", meta_node),
            ("commit", make_commit_node()),
        ]

    steps: list[tuple[str, Any]] = []
    if intent != "TALK":
        steps.append(("mechanic", make_mechanic_node()))
    steps.extend([
        ("encounter", make_encounter_node()),
        ("world_sim", make_world_sim_node()),
        ("companion_reaction", companion_reaction_node),
        ("moments", moments_node),
        ("arc_planner", arc_planner_node),
        ("scene_frame", scene_frame_node),
        ("director", make_director_node()),
        ("narrator", make_narrator_node()),
        ("narrative_validator", narrative_validator_node),
        ("choice_crafter", make_choice_crafter_node()),
        ("commit", make_commit_node()),
    ])
    return steps


def get_pre_narrator_steps(intent: str) -> list[tuple[str, Any]]:
    """Return pipeline steps BEFORE the narrator node (for streaming path)."""
    steps = get_pipeline_steps(intent)
    return [(name, fn) for name, fn in steps if name == "narrator"][0:0] or [
        (name, fn) for name, fn in steps
        if name not in ("narrator", "narrative_validator", "choice_crafter", "commit")
    ]


def get_post_narrator_steps() -> list[tuple[str, Any]]:
    """Return pipeline steps AFTER the narrator node (for streaming path)."""
    return [
        ("narrative_validator", narrative_validator_node),
        ("choice_crafter", make_choice_crafter_node()),
        ("commit", make_commit_node()),
    ]


def _run_pipeline_with_timings(state: dict[str, Any]) -> dict[str, Any]:
    """Execute the turn pipeline step-by-step while collecting per-node timings."""
    timings: dict[str, float] = {}

    def _time_step(name: str, fn, st: dict[str, Any]) -> dict[str, Any]:
        t0 = time.perf_counter()
        out = fn(st)
        timings[name] = round(time.perf_counter() - t0, 3)
        return out

    s = _time_step("router", router_node, state)
    intent = s.get("intent", "ACTION")

    for name, fn in get_pipeline_steps(intent):
        s = _time_step(name, fn, s)

    s["agent_timings"] = timings
    llm_timings = get_llm_timings()
    if llm_timings:
        s["llm_timings"] = llm_timings
    return s


def run_turn(conn: sqlite3.Connection, state: GameState) -> GameState:
    """Run the compiled graph for one turn; return updated GameState with final_text and suggested_actions.

    The DB connection is injected into the state dict as ``__runtime_conn`` so that nodes which
    need it (encounter, world_sim, commit) can read it at invocation time without the graph
    capturing a stale connection in closures. This key is a non-serializable runtime handle and
    MUST NOT be persisted or checkpointed. It is stripped from the result before converting back
    to GameState.

    V5.0: AgentFailureError from authoritative agents is caught here and returned as a
    structured error in the GameState (final_text with error message, empty suggestions).
    """
    import logging
    from backend.app.core.error_handling import AgentFailureError

    _logger = logging.getLogger(__name__)
    initial = state_to_dict(state)
    initial["__runtime_conn"] = conn
    reset_llm_timings()
    t0 = time.monotonic()
    try:
        result = _run_pipeline_with_timings(initial)
    except AgentFailureError as afe:
        elapsed = time.monotonic() - t0
        _logger.error(
            "Turn aborted after %.2fs — agent failure: %s (campaign=%s, turn=%d)",
            elapsed,
            afe,
            state.campaign_id or "unknown",
            state.turn_number or 0,
        )
        # Return a GameState with the error surfaced to the player
        error_dict = state_to_dict(state)
        error_dict.pop("__runtime_conn", None)
        error_dict["final_text"] = (
            f"[SYSTEM] A narrative agent failed: {afe.agent_name}. "
            "The turn could not be completed. Please try again."
        )
        error_dict["suggested_actions"] = []
        error_dict["warnings"] = list(error_dict.get("warnings") or []) + [
            f"[AGENT_FAILURE] {afe.agent_name}: {afe.original_error}"
        ]
        error_dict["agent_timings"] = {}
        error_dict["llm_timings"] = get_llm_timings()
        return dict_to_state(error_dict)
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
