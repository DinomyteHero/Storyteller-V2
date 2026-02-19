from __future__ import annotations

from backend.app.core.agents.mechanic import MechanicAgent
from backend.app.models.state import ActionSuggestion, CharacterSheet, GameState, MechanicCheck, MechanicOutput


class _StubResolver:
    def __init__(self, result: MechanicOutput) -> None:
        self._result = result
        self.called = 0

    def resolve(self, _state: GameState) -> MechanicOutput:
        self.called += 1
        return self._result.model_copy(deep=True)


def _state(
    *,
    mode: str,
    arc_stage: str,
    user_input: str,
    suggested_actions: list[ActionSuggestion] | None = None,
) -> GameState:
    return GameState(
        campaign_id="c1",
        player_id="p1",
        turn_number=4,
        user_input=user_input,
        intent="ACTION",
        player=CharacterSheet(character_id="p1", name="PC"),
        campaign={
            "world_state_json": {
                "campaign_mode": mode,
                "arc_state": {"current_stage": arc_stage},
            }
        },
        suggested_actions=suggested_actions or [],
    )


def test_sandbox_tsunami_blocked_before_climax() -> None:
    agent = MechanicAgent()
    resolver = _StubResolver(
        MechanicOutput(action_type="INTERACT", time_cost_minutes=5, outcome_summary="ok", difficulty="Moderate")
    )
    agent._resolver = resolver
    gs = _state(
        mode="sandbox",
        arc_stage="RISING",
        user_input="Trigger a sabotage chain across all depots.",
        suggested_actions=[
            ActionSuggestion(
                label="Escalate everything",
                intent_text="Trigger a sabotage chain across all depots.",
                impact_tier="tsunami",
            )
        ],
    )

    out = agent.resolve(gs)
    assert out.invalid_action is True
    assert "unlocks at CLIMAX" in (out.rephrase_message or "")
    assert resolver.called == 0


def test_sandbox_wave_applies_dc_modifier_when_allowed() -> None:
    agent = MechanicAgent()
    resolver = _StubResolver(
        MechanicOutput(
            action_type="INTERACT",
            time_cost_minutes=5,
            outcome_summary="ok",
            difficulty="Hard",
            dc=12,
            checks=[MechanicCheck(dc=14, skill="PERSUADE")],
        )
    )
    agent._resolver = resolver
    gs = _state(
        mode="sandbox",
        arc_stage="RISING",
        user_input="Rally allies and lock down the district.",
        suggested_actions=[
            ActionSuggestion(
                label="Rally allies",
                intent_text="Rally allies and lock down the district.",
                impact_tier="wave",
            )
        ],
    )

    out = agent.resolve(gs)
    assert out.invalid_action is False
    assert out.dc == 17
    assert out.checks and out.checks[0].dc == 19
    assert any((m.get("source") == "sandbox_impact:wave" and m.get("value") == 5) for m in (out.modifiers or []))
    assert any("Sandbox impact tier: wave" in f for f in (out.narrative_facts or []))


def test_historical_mode_ignores_sandbox_impact_tier() -> None:
    agent = MechanicAgent()
    resolver = _StubResolver(
        MechanicOutput(
            action_type="INTERACT",
            time_cost_minutes=5,
            outcome_summary="ok",
            difficulty="Hard",
            dc=12,
        )
    )
    agent._resolver = resolver
    gs = _state(
        mode="historical",
        arc_stage="SETUP",
        user_input="Trigger a sabotage chain across all depots.",
        suggested_actions=[
            ActionSuggestion(
                label="Escalate everything",
                intent_text="Trigger a sabotage chain across all depots.",
                impact_tier="tsunami",
            )
        ],
    )

    out = agent.resolve(gs)
    assert out.invalid_action is False
    assert out.dc == 12
    assert not any((m.get("source") or "").startswith("sandbox_impact:") for m in (out.modifiers or []))
    assert resolver.called == 1
