from backend.app.prompts.registry import load_prompt, prompt_registry_snapshot, prompt_version_id


def test_prompt_loader_returns_suggestion_refiner_prompt():
    body = load_prompt("suggestion_refiner_system")
    assert "TONES" in body
    assert "MEANING TAGS" in body


def test_prompt_version_id_is_stable_format():
    vid = prompt_version_id("suggestion_refiner_system")
    assert vid.startswith("v1:")
    assert len(vid) > 6


def test_prompt_registry_snapshot_contains_expected_keys():
    snap = prompt_registry_snapshot()
    assert "suggestion_refiner_system" in snap
    assert snap["suggestion_refiner_system"].startswith("v1:")
