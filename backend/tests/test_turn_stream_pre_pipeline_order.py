"""Regression test: streaming pre-narrator pipeline matches graph order."""
from __future__ import annotations

from backend.app.api.v2_campaigns import _run_pre_narrator_pipeline


def _append_step(step_name: str):
    def _fn(state: dict) -> dict:
        steps = list(state.get("_steps") or [])
        steps.append(step_name)
        state["_steps"] = steps
        return state

    return _fn


def test_stream_pre_pipeline_includes_moments_in_graph_order(monkeypatch):
    """Streaming helper must include moments between companion and arc_planner."""
    # state_to_dict
    monkeypatch.setattr(
        "backend.app.core.nodes.state_to_dict",
        lambda _state: {},
    )

    # Router and intent
    def _router(state: dict) -> dict:
        state = _append_step("router")(state)
        state["intent"] = "ACTION"
        return state

    monkeypatch.setattr("backend.app.core.nodes.router.router_node", _router)

    # Node factories
    monkeypatch.setattr(
        "backend.app.core.nodes.mechanic.make_mechanic_node",
        lambda: _append_step("mechanic"),
    )
    monkeypatch.setattr(
        "backend.app.core.nodes.encounter.make_encounter_node",
        lambda: _append_step("encounter"),
    )
    monkeypatch.setattr(
        "backend.app.core.nodes.world_sim.make_world_sim_node",
        lambda: _append_step("world_sim"),
    )
    monkeypatch.setattr(
        "backend.app.core.nodes.companion.companion_reaction_node",
        _append_step("companion_reaction"),
    )
    monkeypatch.setattr(
        "backend.app.core.nodes.moments.moments_node",
        _append_step("moments"),
    )
    monkeypatch.setattr(
        "backend.app.core.nodes.arc_planner.arc_planner_node",
        _append_step("arc_planner"),
    )
    monkeypatch.setattr(
        "backend.app.core.nodes.scene_frame.scene_frame_node",
        _append_step("scene_frame"),
    )
    monkeypatch.setattr(
        "backend.app.core.nodes.director.make_director_node",
        lambda: _append_step("director"),
    )

    result = _run_pre_narrator_pipeline(conn=object(), state=object())  # state is stubbed via state_to_dict

    assert result["_steps"] == [
        "router",
        "mechanic",
        "encounter",
        "world_sim",
        "companion_reaction",
        "moments",
        "arc_planner",
        "scene_frame",
        "director",
    ]
