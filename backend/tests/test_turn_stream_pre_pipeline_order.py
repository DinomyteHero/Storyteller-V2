"""Regression test: streaming pre-narrator pipeline matches graph order."""
from __future__ import annotations

from backend.app.api.v2_turn import _run_pre_narrator_pipeline


def _append_step(step_name: str):
    def _fn(state: dict) -> dict:
        steps = list(state.get("_steps") or [])
        steps.append(step_name)
        state["_steps"] = steps
        return state

    return _fn


def test_stream_pre_pipeline_includes_moments_in_graph_order(monkeypatch):
    """Streaming helper must include moments between companion and arc_planner."""
    # state_to_dict — patched in nodes module (local import in _run_pre_narrator_pipeline)
    monkeypatch.setattr(
        "backend.app.core.nodes.state_to_dict",
        lambda _state: {},
    )

    # Router and intent — patched in nodes.router (local import in _run_pre_narrator_pipeline)
    def _router(state: dict) -> dict:
        state = _append_step("router")(state)
        state["intent"] = "ACTION"
        return state

    monkeypatch.setattr("backend.app.core.nodes.router.router_node", _router)

    # Node factories — must patch in graph module where they are imported at top level,
    # not in the source modules (graph.py binds its own references at import time).
    monkeypatch.setattr(
        "backend.app.core.graph.make_mechanic_node",
        lambda: _append_step("mechanic"),
    )
    monkeypatch.setattr(
        "backend.app.core.graph.make_encounter_node",
        lambda: _append_step("encounter"),
    )
    monkeypatch.setattr(
        "backend.app.core.graph.make_world_sim_node",
        lambda: _append_step("world_sim"),
    )
    monkeypatch.setattr(
        "backend.app.core.graph.moments_node",
        _append_step("moments"),
    )
    monkeypatch.setattr(
        "backend.app.core.graph.arc_planner_node",
        _append_step("arc_planner"),
    )
    monkeypatch.setattr(
        "backend.app.core.graph.interlude_node",
        _append_step("interlude"),
    )
    monkeypatch.setattr(
        "backend.app.core.graph.scene_frame_node",
        _append_step("scene_frame"),
    )
    monkeypatch.setattr(
        "backend.app.core.graph.make_director_node",
        lambda: _append_step("director"),
    )
    monkeypatch.setattr(
        "backend.app.core.graph.companion_reaction_node",
        _append_step("companion_reaction"),
    )

    result = _run_pre_narrator_pipeline(conn=object(), state=object())  # state is stubbed via state_to_dict

    assert result["_steps"] == [
        "router",
        "mechanic",
        "encounter",
        "world_sim",
        "moments",
        "arc_planner",
        "interlude",
        "scene_frame",
        "director",
        "companion_reaction",
    ]
