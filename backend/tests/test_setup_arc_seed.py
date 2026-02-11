"""Tests for setup-time arc seed generation (hybrid arc approach)."""

from backend.app.api.v2_campaigns import _deterministic_arc_seed, _generate_arc_seed


def test_deterministic_arc_seed_has_required_fields():
    seed = _deterministic_arc_seed(
        time_period="REBELLION",
        genre="political_thriller",
        themes=["duty", "trust"],
        player_concept="A former officer seeking redemption",
        starting_location="loc-mos-eisley",
    )
    assert seed["source"] == "deterministic_fallback"
    assert len(seed["active_themes"]) >= 1
    assert len(seed["opening_threads"]) >= 2
    assert isinstance(seed["climax_question"], str) and seed["climax_question"]
    assert isinstance(seed["arc_intent"], str) and seed["arc_intent"]


def test_generate_arc_seed_falls_back_when_llm_unavailable(monkeypatch):
    class BrokenLLM:
        def __init__(self, role: str):
            raise RuntimeError("offline")

    monkeypatch.setattr("backend.app.core.agents.base.AgentLLM", BrokenLLM)

    seed = _generate_arc_seed(
        time_period="REBELLION",
        genre="heist",
        themes=["survival"],
        player_concept="Scoundrel pilot in debt",
        starting_location="loc-docking-bay",
    )

    assert seed["source"] == "deterministic_fallback"
    assert len(seed["opening_threads"]) >= 2
