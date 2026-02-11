"""Suggestion refiner node: post-Narrator LLM pass that generates scene-aware KOTOR suggestions.

Reads the Narrator's final_text and generates 4 contextual action suggestions that
respond to what actually happened in the prose. On parse failure, retries once with
a correction prompt. On double failure, minimal emergency fallback responses are used.

Uses qwen3:4b (lightweight model) for low latency. Feature-flagged via
ENABLE_SUGGESTION_REFINER env var.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from backend.app.config import ENABLE_SUGGESTION_REFINER
from backend.app.constants import SUGGESTED_ACTIONS_TARGET
from backend.app.core.agents.base import AgentLLM
from backend.app.core.json_repair import extract_json_array
from backend.app.core.director_validation import (
    _humanize_location_for_suggestion,
    action_suggestions_to_player_responses,
    classify_suggestion,
    ensure_tone_diversity,
)
from backend.app.core.action_lint import lint_actions
from backend.app.core.warnings import add_warning
from backend.app.models.state import ActionSuggestion, GameState

logger = logging.getLogger(__name__)

_VALID_TONES = {"PARAGON", "INVESTIGATE", "RENEGADE", "NEUTRAL"}

_SYSTEM_PROMPT = """\
You write SHORT player dialogue options for a Star Wars KOTOR-style game.

TASK: Given scene context, output EXACTLY 4 options the player character can say or do.

OUTPUT FORMAT: A JSON array containing exactly 4 objects. Your response MUST start with [ and end with ].
Do NOT output a single object. Do NOT wrap in {"suggestions": [...]}.
Each object has exactly 3 keys: "text", "tone", "meaning"

TONES (pick one per option, use at least 3 different tones):
- PARAGON: kind, principled, empathetic
- INVESTIGATE: curious, cautious, probing
- RENEGADE: aggressive, ruthless, blunt
- NEUTRAL: practical, tactical, detached

MEANING TAGS (pick one per option):
reveal_values, probe_belief, challenge_premise, seek_history, set_boundary, pragmatic, deflect

RULES:
- Each "text" is 8-16 words, first person, spoken by the PLAYER CHARACTER
- These are player CHOICES, not NPC dialogue or narration
- DO NOT continue the scene or write NPC responses
- DO NOT add fields beyond text/tone/meaning
- Always output ALL 4 options in a single JSON array

EXAMPLE OUTPUT:
[
  {"text": "What happened to you out there?", "tone": "PARAGON", "meaning": "seek_history"},
  {"text": "That's convenient. Who told you that?", "tone": "INVESTIGATE", "meaning": "challenge_premise"},
  {"text": "I don't need your guilt. Where's the ship?", "tone": "RENEGADE", "meaning": "set_boundary"},
  {"text": "Save the philosophy. What's the job?", "tone": "NEUTRAL", "meaning": "pragmatic"}
]"""


def _build_user_prompt(
    final_text: str,
    location: str,
    npc_descriptions: list[str],
    mechanic_summary: str | None,
    npc_utterance_text: str = "",
    topic_primary: str = "",
    subtext: str = "",
    npc_agenda: str = "",
    companion_hint: str = "",
    player_history_hint: str = "",
    director_intent: str = "",
) -> str:
    """Build the user prompt from scene context.

    V3.0: Added companion_hint and player_history_hint for deeper KOTOR-soul
    context without additional LLM calls (data from state).
    """
    parts = [f"PROSE:\n{final_text}"]
    # V2.18: NPC utterance is the primary anchor for player responses
    if npc_utterance_text:
        parts.append(f"\nNPC SAYS: \"{npc_utterance_text}\"")
    parts.append(f"\nSCENE: {location}")
    if npc_descriptions:
        parts.append(f"NPCs: {', '.join(npc_descriptions)}")
    else:
        parts.append("NPCs: No NPCs present")
    if mechanic_summary:
        parts.append(f"AFTER: {mechanic_summary}")
    # V2.18: Topic anchoring context
    if topic_primary:
        parts.append(f"TOPIC: {topic_primary}")
    if subtext:
        parts.append(f"SUBTEXT: {subtext}")
    if npc_agenda:
        parts.append(f"NPC AGENDA: {npc_agenda}")
    # V3.0: Companion and memory context
    if companion_hint:
        parts.append(f"COMPANIONS: {companion_hint}")
    if player_history_hint:
        parts.append(f"PLAYER PATTERN: {player_history_hint}")
    if director_intent:
        parts.append(f"DIRECTOR INTENT: {director_intent}")
    parts.append("\nGenerate 4 responses the player character could say or do:")
    return "\n".join(parts)


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


def _build_stat_gated_options(gs: GameState) -> list[ActionSuggestion]:
    """Deterministic stat-gated dialogue options.

    These options are injected when player stats or alignment cross thresholds so
    the dialogue wheel reflects character build and prior behavior.
    """
    player = gs.player
    stats = (player.stats if player and player.stats else {}) or {}
    campaign = gs.campaign if isinstance(gs.campaign, dict) else {}
    ws = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
    if not isinstance(ws, dict):
        ws = {}
    alignment = ws.get("alignment") if isinstance(ws.get("alignment"), dict) else {}

    charisma = _stat_value(stats, "Charisma", "charisma")
    tech = _stat_value(stats, "Tech", "tech", "Investigation", "investigation")
    combat = _stat_value(stats, "Combat", "combat")
    paragon_renegade = int(alignment.get("paragon_renegade", 0) or 0)

    gated: list[ActionSuggestion] = []
    if charisma >= 6:
        gated.append(ActionSuggestion(
            label="[PERSUADE] I can resolve this without bloodshed—hear me out.",
            intent_text="I can resolve this without bloodshed—hear me out.",
            category="SOCIAL",
            risk_level="SAFE",
            strategy_tag="ALTERNATIVE",
            tone_tag="PARAGON",
            intent_style="confident",
            consequence_hint="uses high charisma to de-escalate",
        ))
    if tech >= 6:
        gated.append(ActionSuggestion(
            label="[TECH] Give me ten seconds. I'll slice the terminal myself.",
            intent_text="Give me ten seconds. I'll slice the terminal myself.",
            category="EXPLORE",
            risk_level="RISKY",
            strategy_tag="ALTERNATIVE",
            tone_tag="INVESTIGATE",
            intent_style="focused",
            consequence_hint="uses technical expertise",
        ))
    if combat >= 7:
        gated.append(ActionSuggestion(
            label="[COMBAT] Stand down now, or I end this the hard way.",
            intent_text="Stand down now, or I end this the hard way.",
            category="COMMIT",
            risk_level="DANGEROUS",
            strategy_tag="ALTERNATIVE",
            tone_tag="RENEGADE",
            intent_style="aggressive",
            consequence_hint="leverages combat reputation",
        ))
    if paragon_renegade >= 8:
        gated.append(ActionSuggestion(
            label="[PARAGON] We do this cleanly. No one gets abandoned.",
            intent_text="We do this cleanly. No one gets abandoned.",
            category="SOCIAL",
            risk_level="SAFE",
            strategy_tag="ALTERNATIVE",
            tone_tag="PARAGON",
            intent_style="steady",
            consequence_hint="reinforces your paragon path",
        ))
    if paragon_renegade <= -8:
        gated.append(ActionSuggestion(
            label="[RENEGADE] Spare me the speech. Give me what I came for.",
            intent_text="Spare me the speech. Give me what I came for.",
            category="COMMIT",
            risk_level="RISKY",
            strategy_tag="ALTERNATIVE",
            tone_tag="RENEGADE",
            intent_style="cold",
            consequence_hint="leans into your renegade reputation",
        ))

    return gated


def _apply_stat_gating(gs: GameState, suggestions: list[ActionSuggestion]) -> list[ActionSuggestion]:
    """Inject at least one stat-gated option when available."""
    gated = _build_stat_gated_options(gs)
    if not gated:
        return suggestions
    out = list(suggestions[: SUGGESTED_ACTIONS_TARGET])
    if not out:
        return gated[:SUGGESTED_ACTIONS_TARGET]

    # Keep one option per tone where possible and reserve slot 0 for gated affordance.
    out[0] = gated[0]
    return out


_VALID_MEANING_TAGS = {
    "reveal_values", "probe_belief", "challenge_premise",
    "seek_history", "set_boundary", "pragmatic", "deflect",
}


def _parse_and_validate(
    raw: str,
    allowed_npc_names: set[str],
) -> list[dict[str, str]] | None:
    """Parse LLM JSON output and validate structure. Returns None on failure.

    V2.18: Accepts both old shape ({"label", "tone"}) and new shape
    ({"text", "tone", "meaning"}). Normalizes to {"label", "tone", "meaning"}.

    V3.0 hardened: Handles raw_json_mode output which may contain <think> blocks,
    markdown fences, single-object responses, or wrapped arrays.
    """
    if not raw or not raw.strip():
        return None

    # Strip markdown fences, leading/trailing noise, and /think blocks
    cleaned = raw.strip()
    # Remove <think>...</think> blocks (qwen3 chain-of-thought)
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
    # Remove markdown code fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    data = None
    # Try 1: Direct parse of the cleaned text
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        pass

    # Try 2: Extract JSON array via bracket matching (handles text before/after)
    if data is None:
        arr_str = extract_json_array(cleaned)
        if arr_str:
            try:
                data = json.loads(arr_str)
            except (json.JSONDecodeError, TypeError):
                pass

    # Try 3: If still nothing, try extracting from original raw (pre-think-strip)
    if data is None:
        arr_str = extract_json_array(raw)
        if arr_str:
            try:
                data = json.loads(arr_str)
            except (json.JSONDecodeError, TypeError):
                pass

    if data is None:
        logger.debug("SuggestionRefiner: all JSON parse attempts failed. Raw (first 500 chars): %s", raw[:500])
        return None

    if not isinstance(data, list):
        # Some models wrap the array in {"suggestions": [...]} — unwrap
        if isinstance(data, dict):
            for key in ("suggestions", "responses", "options", "choices"):
                if key in data and isinstance(data[key], list):
                    data = data[key]
                    break
            else:
                # V3.0: Single suggestion object — wrap it as a partial result
                # Check if it looks like a valid suggestion item
                if data.get("text") or data.get("label"):
                    data = [data]
                    logger.debug("SuggestionRefiner: single object response, wrapped as partial list (1 item)")
                else:
                    logger.debug("SuggestionRefiner: output is dict but no array key found: %s", list(data.keys()))
                    return None

    # V3.0: Accept partial results (1-3 items) — will be validated but not rejected on count alone
    # We still need exactly SUGGESTED_ACTIONS_TARGET, but we'll return None only after checking
    if not data or len(data) > SUGGESTED_ACTIONS_TARGET + 2:
        logger.debug("SuggestionRefiner: expected ~%d items, got %d", SUGGESTED_ACTIONS_TARGET, len(data) if data else 0)
        return None

    # Validate each item
    valid_items = []
    for item in data:
        if not isinstance(item, dict):
            continue
        # V2.18: Accept "text" or "label" key
        label = item.get("text") or item.get("label")
        tone = item.get("tone")
        if not isinstance(label, str) or not label.strip():
            continue
        if not isinstance(tone, str) or tone.upper() not in _VALID_TONES:
            continue
        # Normalize to "label" key for downstream compatibility
        item["label"] = label.strip()
        item["tone"] = tone.upper()
        # V2.18: Validate meaning tag if present, default to empty
        meaning = item.get("meaning", "")
        if meaning and meaning not in _VALID_MEANING_TAGS:
            item["meaning"] = ""  # Invalid tag → clear it (inferred later)
        valid_items.append(item)

    if len(valid_items) < 3:
        logger.debug("SuggestionRefiner: too few valid items (%d, need at least 3)", len(valid_items))
        return None

    # Trim to target if over, pad with generic NEUTRAL if under
    if len(valid_items) > SUGGESTED_ACTIONS_TARGET:
        valid_items = valid_items[:SUGGESTED_ACTIONS_TARGET]
    while len(valid_items) < SUGGESTED_ACTIONS_TARGET:
        valid_items.append({
            "label": "Take a moment to consider your options.",
            "tone": "NEUTRAL",
            "meaning": "pragmatic",
        })

    return valid_items


def _to_action_suggestions(
    items: list[dict[str, str]],
) -> list[ActionSuggestion]:
    """Convert raw LLM items to ActionSuggestion objects via classify_suggestion.

    V2.18: Carries meaning_tag from LLM output through to the suggestion.
    """
    suggestions = []
    for item in items:
        label = item["label"].strip()
        tone = item.get("tone", "NEUTRAL").upper()
        meaning = item.get("meaning", "")
        suggestion = classify_suggestion(label, meaning_tag=meaning)
        # Override tone with LLM's explicit assignment if valid
        if tone in _VALID_TONES:
            suggestion.tone_tag = tone
        suggestions.append(suggestion)
    return suggestions


def make_suggestion_refiner_node():
    """Factory: returns a LangGraph node function for scene-aware suggestion refinement."""
    enabled = ENABLE_SUGGESTION_REFINER
    # Lazy LLM init: retry each turn until Ollama is available, then cache.
    # This avoids a permanent no-op if Ollama isn't running at graph-build time.
    _llm_holder: list[AgentLLM | None] = [None]

    def _get_llm() -> AgentLLM | None:
        if _llm_holder[0] is None:
            try:
                _llm_holder[0] = AgentLLM("suggestion_refiner")
            except Exception as e:
                logger.warning("SuggestionRefiner: failed to init LLM (%s); will use emergency fallback", e)
        return _llm_holder[0]

    def _emergency_fallback(state: dict[str, Any]) -> dict[str, Any]:
        """Generate minimal emergency player responses when LLM refinement is unavailable.

        These are simple, generic one-liners — just enough to keep the game playable.
        """
        if state.get("player_responses"):
            return state

        emergency_suggestions = [
            ActionSuggestion(
                label="Tell me more about what's going on.",
                intent_text="Tell me more about what's going on.",
                category="SOCIAL", risk_level="SAFE",
                strategy_tag="ALTERNATIVE", tone_tag="PARAGON",
                intent_style="calm", consequence_hint="learn more",
            ),
            ActionSuggestion(
                label="What aren't you telling me?",
                intent_text="What aren't you telling me?",
                category="SOCIAL", risk_level="SAFE",
                strategy_tag="ALTERNATIVE", tone_tag="INVESTIGATE",
                intent_style="probing", consequence_hint="press for truth",
            ),
            ActionSuggestion(
                label="Enough talk. Let's get this done.",
                intent_text="Enough talk. Let's get this done.",
                category="COMMIT", risk_level="SAFE",
                strategy_tag="ALTERNATIVE", tone_tag="RENEGADE",
                intent_style="firm", consequence_hint="move things along",
            ),
            ActionSuggestion(
                label="I'll look around first.",
                intent_text="I'll look around first.",
                category="EXPLORE", risk_level="SAFE",
                strategy_tag="ALTERNATIVE", tone_tag="NEUTRAL",
                intent_style="patient", consequence_hint="observe the situation",
            ),
        ]
        actions_list = [a.model_dump(mode="json") for a in emergency_suggestions]
        scene_frame = state.get("scene_frame")
        player_responses = action_suggestions_to_player_responses(emergency_suggestions, scene_frame)
        return {**state, "suggested_actions": actions_list, "player_responses": player_responses}

    def suggestion_refiner_node(state: dict[str, Any]) -> dict[str, Any]:
        """Refine suggestions using Narrator prose as context. Falls back to emergency responses."""
        if not enabled:
            return _emergency_fallback(state)
        llm = _get_llm()
        if llm is None:
            return _emergency_fallback(state)

        final_text = state.get("final_text") or ""
        if not final_text.strip():
            return _emergency_fallback(state)

        # Build context from state
        gs = GameState.model_validate(state) if not isinstance(state, GameState) else state

        loc = gs.current_location or "here"
        loc_readable = _humanize_location_for_suggestion(loc)

        npcs = gs.present_npcs or []
        npc_descriptions = []
        npc_names: set[str] = set()
        for n in npcs:
            name = n.get("name", "")
            role = n.get("role", "stranger")
            if name:
                npc_descriptions.append(f"{name} ({role})")
                npc_names.add(name)

        # Mechanic summary
        mechanic_summary = None
        mr = state.get("mechanic_result") or {}
        action_type = (mr.get("action_type") or "").upper()
        if action_type:
            success = mr.get("success")
            outcome = "succeeded" if success else ("failed" if success is False else "attempted")
            mechanic_summary = f"{action_type.lower()} {outcome}"

        # V2.18: Extract NPC utterance and scene context for KOTOR-recipe prompt
        npc_utterance_text = ""
        npc_utt = state.get("npc_utterance") or {}
        if isinstance(npc_utt, dict):
            npc_utterance_text = npc_utt.get("text", "")
        scene_frame = state.get("scene_frame") or {}
        topic_primary = scene_frame.get("topic_primary", "") if isinstance(scene_frame, dict) else ""
        subtext = scene_frame.get("subtext", "") if isinstance(scene_frame, dict) else ""
        npc_agenda = scene_frame.get("npc_agenda", "") if isinstance(scene_frame, dict) else ""

        # V3.0: Build companion presence hint from party state (no DB calls)
        companion_hint = ""
        try:
            campaign = gs.campaign or {}
            party_ids = campaign.get("party") or [] if isinstance(campaign, dict) else []
            world_state = campaign.get("world_state_json") or {} if isinstance(campaign, dict) else {}
            if isinstance(world_state, str):
                import json as _json2
                world_state = _json2.loads(world_state)
            party_state_data = world_state.get("party_state") or {} if isinstance(world_state, dict) else {}
            companion_states = party_state_data.get("companion_states") or {} if isinstance(party_state_data, dict) else {}
            comp_hints = []
            for cid in (party_ids or [])[:3]:
                from backend.app.core.companions import get_companion_by_id
                comp_data = get_companion_by_id(cid)
                cstate = companion_states.get(cid) or {}
                influence = int(cstate.get("influence", 0) or 0)
                trust_label = "high trust" if influence > 50 else "wary" if influence < 0 else "neutral"
                if comp_data:
                    archetype = comp_data.get("archetype", "companion")
                    comp_name_hint = comp_data.get("name", cid)
                    comp_hints.append(f"{comp_name_hint} ({trust_label}, {archetype})")
            if comp_hints:
                companion_hint = ", ".join(comp_hints)
        except Exception:
            pass  # Non-fatal; companion hint is optional

        # V3.0: Build player history hint from recent inputs (no DB calls)
        player_history_hint = ""
        try:
            last_inputs = gs.last_user_inputs or []
            if len(last_inputs) >= 3:
                from backend.app.core.director_validation import _detect_tone_streak
                streak = _detect_tone_streak(gs.history or [], last_inputs)
                if streak:
                    player_history_hint = f"Player chose {streak} 3+ turns in a row"
        except Exception:
            pass  # Non-fatal

        user_prompt = _build_user_prompt(
            final_text, loc_readable, npc_descriptions, mechanic_summary,
            npc_utterance_text=npc_utterance_text,
            topic_primary=topic_primary,
            subtext=subtext,
            npc_agenda=npc_agenda,
            companion_hint=companion_hint,
            player_history_hint=player_history_hint,
            director_intent=str((state.get("director_instructions") or ""))[:300],
        )

        try:
            raw = llm.complete(_SYSTEM_PROMPT, user_prompt, json_mode=True, raw_json_mode=True)
            logger.debug("SuggestionRefiner raw LLM output (first 600 chars): %s", (raw or "")[:600])
            items = _parse_and_validate(raw, npc_names)

            # Retry once with explicit correction prompt on parse failure
            if items is None:
                logger.info("SuggestionRefiner: first attempt failed, retrying with correction prompt")
                correction_prompt = (
                    "Your previous output was not a valid JSON array of 4 player dialogue options. "
                    "Output ONLY a JSON array with exactly 4 objects. Each object must have "
                    '"text" (8-16 words, player speech), "tone" (PARAGON/INVESTIGATE/RENEGADE/NEUTRAL), '
                    'and "meaning" (one tag). Start with [ and end with ]. No other text.\n\n'
                    + user_prompt
                )
                raw2 = llm.complete(_SYSTEM_PROMPT, correction_prompt, json_mode=True, raw_json_mode=True)
                logger.debug("SuggestionRefiner retry output (first 600 chars): %s", (raw2 or "")[:600])
                items = _parse_and_validate(raw2, npc_names)
                if items is not None:
                    logger.info("SuggestionRefiner: retry succeeded after initial failure")

            if items is None:
                logger.warning("SuggestionRefiner: both LLM attempts failed. Raw (first 300 chars): %s", (raw or "")[:300])
                add_warning(gs, "SuggestionRefiner: LLM output validation failed on both attempts; used emergency fallback")
                return _emergency_fallback({**state, "warnings": gs.warnings})

            suggestions = _to_action_suggestions(items)
            suggestions = ensure_tone_diversity(suggestions)
            suggestions = _apply_stat_gating(gs, suggestions)

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
                add_warning(gs, f"SuggestionRefiner ActionLint: {'; '.join(lint_notes)}")

            actions_list = [a.model_dump(mode="json") for a in linted]

            # V2.17: Convert to PlayerResponse dicts for DialogueTurn
            scene_frame = state.get("scene_frame")
            player_responses = action_suggestions_to_player_responses(linted, scene_frame)

            logger.info("SuggestionRefiner: successfully refined %d suggestions from prose", len(actions_list))
            return {
                **state,
                "suggested_actions": actions_list,
                "player_responses": player_responses,
                "warnings": gs.warnings,
            }

        except Exception as e:
            logger.warning("SuggestionRefiner: LLM call failed (%s); using emergency fallback", str(e))
            add_warning(gs, "SuggestionRefiner: LLM error; used emergency fallback")
            return _emergency_fallback({**state, "warnings": gs.warnings})

    return suggestion_refiner_node
