from __future__ import annotations

from backend.app.core.nodes.encounter import apply_canon_proximity_rules
from backend.app.world.era_pack_models import CanonCharacterRule


def _state(mode: str, beat: str = "", user_input: str = "") -> dict:
    return {
        "campaign": {
            "world_state_json": {
                "campaign_mode": mode,
                "current_beat": beat,
            }
        },
        "user_input": user_input,
    }


def test_canon_proximity_noop_in_sandbox() -> None:
    present, bg, warnings = apply_canon_proximity_rules(
        state=_state("sandbox"),
        effective_loc="loc-cantina",
        present_npcs=[{"id": "npc-1", "name": "Luke Skywalker"}],
        background_figures=[],
        canon_rules=[
            CanonCharacterRule(
                name="Luke Skywalker",
                proximity="cameo",
                locations=["loc-cantina"],
                exclusion_events=[],
            )
        ],
    )
    assert len(present) == 1
    assert not bg
    assert not warnings


def test_canon_proximity_cameo_removes_interaction_adds_background_figure() -> None:
    present, bg, warnings = apply_canon_proximity_rules(
        state=_state("historical"),
        effective_loc="loc-cantina",
        present_npcs=[{"id": "npc-luke", "name": "Luke Skywalker"}],
        background_figures=[],
        canon_rules=[
            CanonCharacterRule(
                name="Luke Skywalker",
                proximity="cameo",
                locations=["loc-cantina"],
                exclusion_events=[],
            )
        ],
    )
    assert not any(n.get("name") == "Luke Skywalker" for n in present)
    assert any("Luke Skywalker" in line for line in bg)
    assert not warnings


def test_canon_proximity_interaction_adds_protected_npc() -> None:
    present, bg, warnings = apply_canon_proximity_rules(
        state=_state("historical"),
        effective_loc="loc-rebel-base",
        present_npcs=[],
        background_figures=[],
        canon_rules=[
            CanonCharacterRule(
                name="Princess Leia",
                proximity="interaction",
                locations=["loc-rebel-base"],
                exclusion_events=[],
            )
        ],
    )
    assert any(n.get("name") == "Princess Leia" for n in present)
    leia = next(n for n in present if n.get("name") == "Princess Leia")
    assert leia.get("canon_protected") is True
    assert leia.get("canon_proximity") == "interaction"
    assert any("cannot be altered" in w for w in warnings)
    assert not bg


def test_canon_proximity_exclusion_warns_and_redirects_flavor() -> None:
    present, bg, warnings = apply_canon_proximity_rules(
        state=_state("historical", beat="Battle of Yavin trench run"),
        effective_loc="loc-rebel-base",
        present_npcs=[{"id": "npc-luke", "name": "Luke Skywalker"}],
        background_figures=[],
        canon_rules=[
            CanonCharacterRule(
                name="Luke Skywalker",
                proximity="exclusion",
                locations=["loc-rebel-base"],
                exclusion_events=["Battle of Yavin trench run"],
            )
        ],
    )
    assert not any(n.get("name") == "Luke Skywalker" for n in present)
    assert any("redirected away" in w for w in warnings)
    assert any("pull you away" in line for line in bg)
