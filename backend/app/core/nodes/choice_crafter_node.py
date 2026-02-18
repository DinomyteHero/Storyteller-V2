"""Choice Crafter node: LLM-driven player choice generation.

Replaces the suggestion_refiner node. Reads the Narrator's final_text and full scene
context, then calls ChoiceCrafterAgent to generate 4 contextually-aware player choices.

No deterministic fallbacks. On LLM failure, raises AgentFailureError which the
graph-level handler converts to a user-facing error.

V5.0: Authoritative LLM node — setting-agnostic, no hardcoded scenario trees.
"""
from __future__ import annotations

import json as _json
import logging
from typing import Any

from backend.app.constants import SUGGESTED_ACTIONS_TARGET
from backend.app.core.agents.choice_crafter_agent import generate_choices
from backend.app.core.suggestion_engine import (
    classify_suggestion,
    ensure_tone_diversity,
    action_suggestions_to_player_responses,
)
from backend.app.core.action_lint import lint_actions
from backend.app.core.warnings import add_warning
from backend.app.models.state import ActionSuggestion, GameState

logger = logging.getLogger(__name__)

_VALID_TONES = {"PARAGON", "INVESTIGATE", "RENEGADE", "NEUTRAL"}


def _stat_value(stats: dict[str, Any], *keys: str) -> int:
    """Lookup a stat from mixed-case keys with safe int conversion."""
    for key in keys:
        value = stats.get(key)
        if value is None:
            value = stats.get(key.lower())
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def _build_stat_summary(gs: GameState) -> str:
    """Build a stat summary string for the LLM (only notable stats)."""
    player = gs.player
    stats = (player.stats if player and player.stats else {}) or {}
    if not stats:
        return ""
    notable = []
    for stat_name, stat_val in stats.items():
        try:
            val = int(stat_val)
        except (TypeError, ValueError):
            continue
        if val >= 6:
            notable.append(f"{stat_name}={val} (high)")
        elif val <= 1:
            notable.append(f"{stat_name}={val} (untrained)")
    if not notable:
        return ""
    return ", ".join(notable)


def _build_companion_hint(gs: GameState) -> str:
    """Build companion presence hint from party state (no DB calls)."""
    campaign = gs.campaign or {}
    if not isinstance(campaign, dict):
        return ""
    party_ids = campaign.get("party") or []
    if not party_ids:
        return ""
    world_state = campaign.get("world_state_json") or {}
    if isinstance(world_state, str):
        try:
            world_state = _json.loads(world_state)
        except Exception:
            world_state = {}
    party_state_data = world_state.get("party_state") or {} if isinstance(world_state, dict) else {}
    companion_states = party_state_data.get("companion_states") or {} if isinstance(party_state_data, dict) else {}
    hints = []
    for cid in party_ids[:3]:
        try:
            from backend.app.core.companions import get_companion_by_id
            comp_data = get_companion_by_id(cid)
            cstate = companion_states.get(cid) or {}
            influence = int(cstate.get("influence", 0) or 0)
            trust_label = "high trust" if influence > 50 else "wary" if influence < 0 else "neutral"
            if comp_data:
                archetype = comp_data.get("archetype", "companion")
                name = comp_data.get("name", cid)
                hints.append(f"{name} ({trust_label}, {archetype})")
        except Exception:
            continue
    return ", ".join(hints) if hints else ""


def _build_player_history_hint(gs: GameState) -> str:
    """Detect tone streaks in recent player input."""
    last_inputs = gs.last_user_inputs or []
    if len(last_inputs) < 3:
        return ""
    try:
        from backend.app.core.suggestion_engine import _detect_tone_streak
        streak = _detect_tone_streak(gs.history or [], last_inputs)
        if streak:
            return f"Player chose {streak} 3+ turns in a row"
    except Exception:
        pass
    return ""


def _get_consequence_hints(gs: GameState) -> list[str]:
    """Extract active consequence hints from the ledger."""
    campaign = gs.campaign or {}
    if not isinstance(campaign, dict):
        return []
    world_state = campaign.get("world_state_json") or {}
    if isinstance(world_state, str):
        try:
            world_state = _json.loads(world_state)
        except Exception:
            return []
    if not isinstance(world_state, dict):
        return []
    ledger = world_state.get("ledger") or {}
    if not isinstance(ledger, dict):
        return []
    hints = ledger.get("consequence_hints") or []
    if isinstance(hints, list):
        return [str(h) for h in hints[:5] if h]
    return []


def _get_arc_context(gs: GameState) -> tuple[str, str]:
    """Extract arc_stage and tension_level from arc_guidance."""
    ag = gs.arc_guidance if isinstance(gs.arc_guidance, dict) else {}
    arc_state = ag.get("arc_state") or {}
    stage = arc_state.get("current_stage", "") if isinstance(arc_state, dict) else ""
    tension = str(ag.get("tension_level", ""))
    return stage, tension


def _make_fallback_choices(
    final_text: str,
    loc: str,
    immediate_situation: str = "",
) -> list[dict[str, str]]:
    """Deterministic 2-choice fallback when LLM fails.

    Returns minimal but contextually grounded PARAGON + INVESTIGATE choices so the
    turn can complete instead of hard-failing. Caller adds a warning to state.
    """
    situation = immediate_situation or (final_text[-120:].strip() if final_text else "the current situation")
    return [
        {
            "text": f"Act decisively in response to {situation[:60]}",
            "tone": "PARAGON",
            "meaning": "pragmatic",
            "risk": "RISKY",
            "consequence_hint": "Your bold action shapes what happens next.",
        },
        {
            "text": f"Hold back and carefully assess {loc}",
            "tone": "INVESTIGATE",
            "meaning": "seek_history",
            "risk": "SAFE",
            "consequence_hint": "Taking stock reveals something important.",
        },
    ]


def _to_action_suggestions(items: list[dict[str, str]]) -> list[ActionSuggestion]:
    """Convert raw LLM choice dicts to ActionSuggestion objects."""
    suggestions = []
    for item in items:
        text = item.get("text", "").strip()
        tone = item.get("tone", "NEUTRAL").upper()
        meaning = item.get("meaning", "")
        risk = item.get("risk", "SAFE").upper()
        hint = item.get("consequence_hint", "")

        suggestion = classify_suggestion(text, meaning_tag=meaning)
        # Override with LLM's explicit assignments
        if tone in _VALID_TONES:
            suggestion.tone_tag = tone
        if risk in ("SAFE", "RISKY", "DANGEROUS"):
            suggestion.risk_level = risk
        if hint:
            suggestion.consequence_hint = hint
        suggestions.append(suggestion)
    return suggestions


def make_choice_crafter_node():
    """Factory: returns a LangGraph node function for LLM-driven choice generation."""

    def choice_crafter_node(state: dict[str, Any]) -> dict[str, Any]:
        """Generate player choices using LLM. Falls back to 2-choice degraded output on LLM failure."""
        final_text = state.get("final_text") or ""
        if not final_text.strip():
            raise ValueError("ChoiceCrafter: no final_text available for choice generation")

        gs = GameState.model_validate(state) if not isinstance(state, GameState) else state

        # Build location string
        loc = gs.current_location or "here"

        # NPC descriptions
        npcs = gs.present_npcs or []
        npc_descriptions = []
        for n in npcs:
            name = n.get("name", "")
            role = n.get("role", "stranger")
            if name:
                npc_descriptions.append(f"{name} ({role})")

        # Mechanic summary
        mechanic_summary = None
        mr = state.get("mechanic_result") or {}
        action_type = (mr.get("action_type") or "").upper()
        if action_type:
            success = mr.get("success")
            outcome = "succeeded" if success else ("failed" if success is False else "attempted")
            mechanic_summary = f"{action_type.lower()} {outcome}"
            outcome_summary = mr.get("outcome_summary")
            if outcome_summary:
                mechanic_summary += f" — {str(outcome_summary)[:100]}"

        # NPC utterance and scene context
        npc_utt = state.get("npc_utterance") or {}
        npc_utterance_text = npc_utt.get("text", "") if isinstance(npc_utt, dict) else ""
        scene_frame = state.get("scene_frame") or {}
        topic_primary = scene_frame.get("topic_primary", "") if isinstance(scene_frame, dict) else ""
        subtext = scene_frame.get("subtext", "") if isinstance(scene_frame, dict) else ""
        npc_agenda = scene_frame.get("npc_agenda", "") if isinstance(scene_frame, dict) else ""

        # Companion, history, consequence, arc, and stat context
        companion_hint = _build_companion_hint(gs)
        player_history_hint = _build_player_history_hint(gs)
        consequence_hints = _get_consequence_hints(gs)
        arc_stage, tension_level = _get_arc_context(gs)
        stat_summary = _build_stat_summary(gs)

        # Setting style
        from backend.app.core.setting_context import get_setting_rules
        sr = get_setting_rules(state)
        setting_style = sr.suggestion_style

        # Director intent
        director_intent = str((state.get("director_instructions") or ""))[:300]

        # GM Context Object (from scene_frame_node)
        gm_context = state.get("gm_context") or ""

        # Generate choices via LLM (with degraded 2-choice fallback on failure)
        _use_fallback = False
        try:
            items = generate_choices(
                final_text=final_text,
                location=loc,
                npc_descriptions=npc_descriptions,
                mechanic_summary=mechanic_summary,
                npc_utterance_text=npc_utterance_text,
                topic_primary=topic_primary,
                subtext=subtext,
                npc_agenda=npc_agenda,
                companion_hint=companion_hint,
                player_history_hint=player_history_hint,
                director_intent=director_intent,
                arc_stage=arc_stage,
                tension_level=tension_level,
                consequence_hints=consequence_hints,
                stat_summary=stat_summary,
                setting_style=setting_style,
                gm_context=gm_context,
            )
        except Exception as e:
            logger.warning("ChoiceCrafter LLM failed (%s); using 2-choice degraded fallback", e)
            immediate_situation = scene_frame.get("immediate_situation", "") if isinstance(scene_frame, dict) else ""
            items = _make_fallback_choices(final_text, loc, immediate_situation)
            _use_fallback = True

        if _use_fallback:
            add_warning(gs, "ChoiceCrafter: LLM failed; showing 2-choice degraded options.")

        # Convert to ActionSuggestions
        suggestions = _to_action_suggestions(items)
        suggestions = ensure_tone_diversity(suggestions)

        # Lint through the standard pipeline
        actions_list = [
            a.model_dump(mode="json") if hasattr(a, "model_dump") else a
            for a in suggestions
        ]
        linted, lint_notes = lint_actions(
            actions_list,
            game_state=gs,
            router_output=gs.router_output,
            mechanic_output=gs.mechanic_result,
            encounter_context={"present_npcs": gs.present_npcs},
        )
        if lint_notes:
            add_warning(gs, f"ChoiceCrafter ActionLint: {'; '.join(lint_notes)}")

        actions_list = [a.model_dump(mode="json") for a in linted]

        # Convert to PlayerResponse dicts for DialogueTurn
        player_responses = action_suggestions_to_player_responses(linted, scene_frame)

        logger.info("ChoiceCrafter: generated %d choices from prose", len(actions_list))
        return {
            **state,
            "suggested_actions": actions_list,
            "player_responses": player_responses,
            "warnings": gs.warnings,
        }

    return choice_crafter_node
