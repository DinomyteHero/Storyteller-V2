from backend.app.core.passages.engine import apply_choice


def test_hybrid_sim_scene_sets_pending_flag():
    ep = {
        "passages": {
            "p1": {"choices": [{"id": "c1", "label": "Sim", "next": "SIM_SCENE:breach", "cost": {"time_minutes": 3}}]}
        }
    }
    state = {"flags": {}}
    nxt, _out, delta = apply_choice(ep, "p1", "c1", state)
    assert nxt == "p1"
    assert delta.flags_set.get("pending_sim_scene") == "breach"
