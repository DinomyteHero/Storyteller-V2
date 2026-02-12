from backend.app.core.passages.engine import load_episode, build_choices, apply_choice


def test_passage_requirements_and_flags():
    ep = load_episode("rebellion")
    passage = ep["passages"][ep["start_passage_id"]]
    state = {"flags": {}, "player_name": "Test"}
    choices = build_choices(passage, state)
    assert len(choices) >= 2
    next_pid, out, delta = apply_choice(ep, ep["start_passage_id"], choices[0].id, state)
    assert next_pid
    assert out.category
    assert delta.time_minutes >= 0


def test_passage_end_fallback_has_two_choices():
    ep = load_episode("rebellion")
    end_p = ep["passages"]["p_end"]
    choices = build_choices(end_p, {"flags": {}})
    assert len(choices) >= 2
