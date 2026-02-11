"""Router and META nodes for the LangGraph pipeline."""
from __future__ import annotations

from typing import Any

from backend.app.models.state import (
    ActionSuggestion,
    MechanicOutput,
    ROUTER_ROUTE_TALK,
    ROUTER_ROUTE_META,
    ROUTER_ACTION_CLASS_DIALOGUE_ONLY,
    ACTION_CATEGORY_SOCIAL,
    ACTION_CATEGORY_EXPLORE,
    ACTION_CATEGORY_COMMIT,
    TONE_TAG_PARAGON,
    TONE_TAG_INVESTIGATE,
    TONE_TAG_RENEGADE,
)
from backend.app.time_economy import DIALOGUE_ONLY_MINUTES
from backend.app.core.router import route as router_route


def router_node(state: dict[str, Any]) -> dict[str, Any]:
    """Router: classify input into route + action_class. Three branches: META, TALK, ACTION."""
    user_input = (state.get("user_input") or "").strip()
    # Strip the [OPENING_SCENE] tag if present (used by UI to signal first turn)
    # but keep the actual action text for routing
    if "[OPENING_SCENE]" in user_input:
        user_input = user_input.replace("[OPENING_SCENE]", "").strip()
    router_out = router_route(user_input)
    route = router_out.route
    action_class = router_out.action_class
    intent_text = router_out.intent_text or user_input
    # Three-way intent: skip Mechanic only when TALK + DIALOGUE_ONLY + requires_resolution is false
    requires_resolution = getattr(router_out, "requires_resolution", True)
    if route == ROUTER_ROUTE_META and action_class == "META":
        intent = "META"
    elif route == ROUTER_ROUTE_TALK and action_class == ROUTER_ACTION_CLASS_DIALOGUE_ONLY and not requires_resolution:
        intent = "TALK"
    else:
        intent = "ACTION"
    out = {
        **state,
        "intent": intent,
        "route": route,
        "action_class": action_class,
        "intent_text": intent_text,
        "router_output": router_out.model_dump(mode="json"),
    }
    if intent == "TALK":
        # Minimal mechanic_result only for true dialogue-only; no dice, no state changes
        out["mechanic_result"] = MechanicOutput(
            action_type="TALK",
            events=[],
            narrative_facts=[],
            time_cost_minutes=DIALOGUE_ONLY_MINUTES,
            tone_tag=TONE_TAG_PARAGON,
            alignment_delta={},
            faction_reputation_delta={},
            companion_affinity_delta={},
            companion_reaction_reason={},
        ).model_dump(mode="json")
    # META: no mechanic_result here; MetaNode sets final_text/suggested_actions; Commit handles absent mechanic_result
    return out


def meta_node(state: dict[str, Any]) -> dict[str, Any]:
    """Deterministic META handler: no LLMs, no world time, no events."""
    intent_text = (state.get("intent_text") or state.get("user_input") or "").strip().lower()
    if intent_text == "help":
        narrated = (
            "**Help** - You can describe actions (e.g. 'I search the room', 'I ask the guard for directions') "
            "or dialogue ('I tell her I'm leaving'). Save/load are handled by autosave each turn; use the menu for load. "
            "Choose a suggestion below or type your own."
        )
    elif intent_text == "save":
        narrated = (
            "Progress is autosaved at the end of each turn. Use the game menu or load screen to resume later."
        )
    elif intent_text == "load":
        narrated = (
            "Use the game menu or load screen to open a saved campaign. This turn was not counted as in-world time."
        )
    elif intent_text == "quit":
        narrated = (
            "Use the game menu to quit. Your progress is autosaved each turn."
        )
    else:
        narrated = (
            "Meta: Use the menu for save/load/quit. Type an action or dialogue to continue the story."
        )
    suggestions = [
        ActionSuggestion(
            label="Continue story",
            intent_text="Look around",
            category=ACTION_CATEGORY_EXPLORE,
            risk_level="SAFE",
            strategy_tag="OPTIMAL",
            tone_tag=TONE_TAG_INVESTIGATE,
            intent_style="probing",
            consequence_hint="learn more",
        ),
        ActionSuggestion(
            label="Talk to someone",
            intent_text="Say: Hello",
            category=ACTION_CATEGORY_SOCIAL,
            risk_level="SAFE",
            strategy_tag="ALTERNATIVE",
            tone_tag=TONE_TAG_PARAGON,
            intent_style="calm",
            consequence_hint="may gain trust",
        ),
        ActionSuggestion(
            label="Do something",
            intent_text="I check my gear",
            category=ACTION_CATEGORY_COMMIT,
            risk_level="SAFE",
            strategy_tag="ALTERNATIVE",
            tone_tag=TONE_TAG_RENEGADE,
            intent_style="firm",
            consequence_hint="may escalate",
        ),
    ]

    # Keep UI contract consistent (pad/trim to target count) even on META turns.
    from backend.app.core.action_lint import lint_actions

    linted, _notes = lint_actions(suggestions)
    return {
        **state,
        "final_text": narrated,
        "suggested_actions": [a.model_dump(mode="json") for a in linted],
        "lore_citations": [],
    }
