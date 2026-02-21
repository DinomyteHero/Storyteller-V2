"""Arc planner node: deterministic arc stage + pacing guidance for Director (no LLM, no DB).

V2.5: Content-aware arc transitions — stages advance based on narrative
readiness (thread/fact counts) with min/max turn guards.  Also injects
active_themes and theme_guidance from the ledger.
"""
from __future__ import annotations

import logging
from typing import Any

from backend.app.constants import (
    ARC_CLIMAX_RESOLUTION_FLAG_PREFIX,
    ARC_COUNT_BY_SCALE,
    ARC_MAX_TURNS,
    ARC_MIN_TURNS,
    ARC_MOOD_PROFILES,
    ARC_RISING_TO_CLIMAX_MIN_THREADS,
    ARC_SETUP_TO_RISING_MIN_FACTS,
    ARC_SETUP_TO_RISING_MIN_THREADS,
    BEAT_ARCHETYPE_HINTS,
    CONCLUSION_ENDING_STYLES,
    CONCLUSION_MIN_RESOLUTION_TURNS,
    CONCLUSION_RESOLVED_RATIO,
    DEFAULT_ARC_MOOD_PROFILE,
    EPILOGUE_PACING_HINT,
    EPILOGUE_TURNS,
    FORESHADOW_MAX_HINTS,
    HERO_JOURNEY_BEATS,
    INTERLUDE_MAX_TURNS,
    INTERLUDE_PACING_HINT,
    NPC_ARCHETYPES,
    SCALE_DOWN_SCORE_THRESHOLD,
    SCALE_ORDER,
    SCALE_SHIFT_COOLDOWN_TURNS,
    SCALE_UP_SCORE_THRESHOLD,
)
from backend.app.core.ledger import weighted_thread_count

logger = logging.getLogger(__name__)

# Tension level by arc stage
_TENSION_BY_STAGE: dict[str, str] = {
    "SETUP": "CALM",
    "RISING": "ESCALATING",
    "CLIMAX": "PEAK",
    "RESOLUTION": "RESOLVING",
}

# Pacing hints by arc stage
_PACING_HINTS: dict[str, str] = {
    "SETUP": "Establish setting and relationships. Introduce threads gradually.",
    "RISING": "Increase stakes. Reference open threads. Build toward confrontation.",
    "CLIMAX": "Stakes are high. At least one suggestion should advance the primary conflict.",
    "RESOLUTION": "Consider aftermath and reflection. Tie up loose threads.",
}

# Suggested category weights by stage
_WEIGHTS_BY_STAGE: dict[str, dict[str, float]] = {
    "SETUP": {"SOCIAL": 0.4, "EXPLORE": 0.4, "COMMIT": 0.2},
    "RISING": {"SOCIAL": 0.3, "EXPLORE": 0.3, "COMMIT": 0.4},
    "CLIMAX": {"SOCIAL": 0.1, "EXPLORE": 0.2, "COMMIT": 0.7},
    "RESOLUTION": {"SOCIAL": 0.5, "EXPLORE": 0.3, "COMMIT": 0.2},
}

# Theme-specific pacing guidance by arc stage
_THEME_GUIDANCE_BY_STAGE: dict[str, str] = {
    "SETUP": "Introduce themes through setting and character interactions.",
    "RISING": "Deepen themes through escalating moral dilemmas.",
    "CLIMAX": "Bring themes to crisis point. Force hard choices that test the theme.",
    "RESOLUTION": "Reflect on how themes were resolved or transformed.",
}

# Stage transition order
_STAGE_ORDER = ["SETUP", "RISING", "CLIMAX", "RESOLUTION"]


def _determine_arc_stage_dynamic(
    turn_number: int,
    ledger: dict,
    current_stage: str | None,
    stage_start_turn: int,
    recent_narrative: str = "",
) -> tuple[str, bool, dict]:
    """Determine arc stage using LLM semantic analysis with min/max safety guards.

    V5.0: Hybrid approach — deterministic guards (hard constraints) + LLM narrative
    analysis (within the transition window). Returns (stage, transition_occurred, arc_weaver_result).
    """
    if current_stage is None:
        return "SETUP", False, {}

    # RESOLUTION is handled by multi-arc transition logic in arc_planner_node.
    # Stay in RESOLUTION here; the node itself checks conclusion_ready for chaining.
    if current_stage == "RESOLUTION":
        return "RESOLUTION", False, {}

    turns_in_stage = max(0, turn_number - stage_start_turn)
    min_turns = ARC_MIN_TURNS.get(current_stage, 3)
    max_turns = ARC_MAX_TURNS.get(current_stage, 999)

    # Hard guard: don't transition before minimum turns
    if turns_in_stage < min_turns:
        return current_stage, False, {}

    threads = ledger.get("open_threads") or []
    facts = ledger.get("established_facts") or []
    consequence_hints = ledger.get("consequence_hints") or []

    # Hard guard: force transition if max turns exceeded
    if turns_in_stage >= max_turns:
        idx = _STAGE_ORDER.index(current_stage) if current_stage in _STAGE_ORDER else 0
        if idx < len(_STAGE_ORDER) - 1:
            return _STAGE_ORDER[idx + 1], True, {"justification": "max turns exceeded"}
        return current_stage, False, {}

    # Within transition window: use LLM semantic analysis
    try:
        from backend.app.core.agents.arc_weaver_agent import evaluate_arc_transition
        result = evaluate_arc_transition(
            current_stage=current_stage,
            turns_in_stage=turns_in_stage,
            ledger_facts=facts[-10:],
            open_threads=threads[-8:],
            consequence_hints=consequence_hints[:5],
            recent_narrative=recent_narrative,
        )
        if result.get("should_advance"):
            idx = _STAGE_ORDER.index(current_stage) if current_stage in _STAGE_ORDER else 0
            if idx < len(_STAGE_ORDER) - 1:
                logger.info(
                    "ArcWeaver: advancing %s -> %s — %s",
                    current_stage, _STAGE_ORDER[idx + 1],
                    result.get("justification", ""),
                )
                return _STAGE_ORDER[idx + 1], True, result
        return current_stage, False, result
    except Exception as e:
        # If LLM fails, fall back to the deterministic thresholds
        logger.warning("ArcWeaver LLM failed, using deterministic fallback: %s", e)
        thread_score = weighted_thread_count(threads)
        ready = False
        if current_stage == "SETUP":
            if thread_score >= ARC_SETUP_TO_RISING_MIN_THREADS and len(facts) >= ARC_SETUP_TO_RISING_MIN_FACTS:
                ready = True
        elif current_stage == "RISING":
            if thread_score >= ARC_RISING_TO_CLIMAX_MIN_THREADS:
                ready = True
        elif current_stage == "CLIMAX":
            flags = [f for f in facts if f.startswith("Flag set:")]
            resolved_flags = [f for f in flags if ARC_CLIMAX_RESOLUTION_FLAG_PREFIX in f.lower()]
            if resolved_flags:
                ready = True
        if ready:
            idx = _STAGE_ORDER.index(current_stage) if current_stage in _STAGE_ORDER else 0
            if idx < len(_STAGE_ORDER) - 1:
                return _STAGE_ORDER[idx + 1], True, {}
        return current_stage, False, {}


def _determine_hero_beat(arc_stage: str, turns_in_stage: int, min_turns: int, max_turns: int) -> dict:
    """Determine the current Hero's Journey sub-beat within the arc stage.

    Uses turn-count-based deterministic transitions: each stage has 3 beats,
    distributed evenly across the stage's turn range.
    Returns dict with 'beat' and 'pacing' keys.
    """
    beats = HERO_JOURNEY_BEATS.get(arc_stage, [])
    if not beats:
        return {"beat": "UNKNOWN", "pacing": ""}

    # Divide the stage turn range into thirds for 3 beats
    # Use max_turns as the expected range (min_turns is the earliest we can transition)
    range_per_beat = max(1, max_turns // len(beats))

    beat_idx = min(turns_in_stage // range_per_beat, len(beats) - 1)
    return beats[beat_idx]


def _get_archetype_hints(hero_beat: str) -> list[dict[str, str]]:
    """Get NPC archetype hints relevant to the current Hero's Journey beat."""
    archetype_ids = BEAT_ARCHETYPE_HINTS.get(hero_beat, [])
    return [
        {"archetype": aid, "description": NPC_ARCHETYPES.get(aid, "")}
        for aid in archetype_ids
        if aid in NPC_ARCHETYPES
    ]


def _determine_tension(arc_stage: str, ledger: dict) -> str:
    """Determine tension level from arc stage and ledger state."""
    base = _TENSION_BY_STAGE.get(arc_stage, "CALM")
    # Override: if few open threads in RISING, tension is BUILDING not ESCALATING
    threads = ledger.get("open_threads") or []
    if arc_stage == "RISING" and len(threads) < 2:
        return "BUILDING"
    return base


def _evaluate_scale_recommendation(
    current_scale: str,
    arc_stage: str,
    tension_level: str,
    ledger: dict,
    turn_number: int,
    last_scale_change_turn: int,
    pivotal_event_count: int,
) -> dict[str, Any] | None:
    """Evaluate whether campaign scale should shift based on narrative density.

    Returns a recommendation dict or None if no change is warranted.
    Pure function — caller gates on ENABLE_SCALE_ADVISOR feature flag.
    """
    # Enforce cooldown
    if turn_number - last_scale_change_turn < SCALE_SHIFT_COOLDOWN_TURNS:
        return None

    # Don't advise during SETUP — not enough data yet
    eligible_stages = ("RISING", "CLIMAX", "RESOLUTION")
    if arc_stage not in eligible_stages:
        return None

    # Compute narrative density score
    threads = ledger.get("open_threads") or []
    goals = ledger.get("active_goals") or []
    thread_score = weighted_thread_count(threads)
    density_score = thread_score + len(goals) + (pivotal_event_count * 2)

    scale_idx = SCALE_ORDER.index(current_scale) if current_scale in SCALE_ORDER else 1

    # Scale UP: high density during RISING/CLIMAX
    if arc_stage in ("RISING", "CLIMAX") and density_score >= SCALE_UP_SCORE_THRESHOLD:
        if scale_idx < len(SCALE_ORDER) - 1:
            new_scale = SCALE_ORDER[scale_idx + 1]
            return {
                "recommended_scale": new_scale,
                "direction": "up",
                "reason": f"Narrative density ({density_score}) exceeds threshold during {arc_stage}",
                "density_score": density_score,
            }

    # Scale DOWN: low density during RESOLUTION
    if arc_stage == "RESOLUTION" and density_score <= SCALE_DOWN_SCORE_THRESHOLD:
        if scale_idx > 0:
            new_scale = SCALE_ORDER[scale_idx - 1]
            return {
                "recommended_scale": new_scale,
                "direction": "down",
                "reason": f"Low narrative density ({density_score}) during RESOLUTION",
                "density_score": density_score,
            }

    return None


def _build_conclusion_plan(
    arc_stage: str,
    turns_in_stage: int,
    campaign_scale: str,
    ledger: dict,
) -> dict[str, Any] | None:
    """Build a deterministic conclusion plan during RESOLUTION stage.

    Returns a conclusion_plan dict or None if not in RESOLUTION.
    """
    if arc_stage != "RESOLUTION":
        return None

    scale = campaign_scale if campaign_scale in CONCLUSION_RESOLVED_RATIO else "medium"
    ending_style = CONCLUSION_ENDING_STYLES.get(scale, "soft_cliffhanger")
    required_ratio = CONCLUSION_RESOLVED_RATIO.get(scale, 0.7)

    threads = ledger.get("open_threads") or []
    total_threads = len(threads)

    if total_threads == 0:
        # No threads tracked — campaign is trivially ready to conclude
        return {
            "ending_style": ending_style,
            "conclusion_ready": turns_in_stage >= CONCLUSION_MIN_RESOLUTION_TURNS,
            "resolved_ratio": 1.0,
            "dangling_hooks": [],
            "payoff_threads": [],
        }

    # Classify threads by weight: W3 = must resolve, W1 = can become hooks
    resolved_facts = ledger.get("established_facts") or []
    resolved_flags = [f for f in resolved_facts if f.lower().startswith("resolved")]

    # Heuristic: count threads whose text appears in a resolved flag
    resolved_count = 0
    dangling_hooks: list[str] = []
    payoff_threads: list[str] = []

    import re as _re
    for t in threads:
        thread_text = t if isinstance(t, str) else (t.get("text", "") if isinstance(t, dict) else str(t))
        # Check if any resolved flag references this thread
        # Strip [W<n>] prefix for matching
        clean_text = _re.sub(r"^\[W\d\]\s*", "", thread_text) if isinstance(thread_text, str) else thread_text
        is_resolved = any(
            clean_text.lower()[:20] in flag.lower()
            for flag in resolved_flags
        ) if clean_text else False

        if is_resolved:
            resolved_count += 1
            payoff_threads.append(thread_text)
        else:
            # Weight-based classification: W3 payoffs, W1 hooks
            weight = 1
            if isinstance(t, str):
                wm = _re.match(r"^\[W(\d)\]", t)
                if wm:
                    weight = int(wm.group(1))
            elif isinstance(t, dict):
                weight = int(t.get("weight", 1))
            if weight >= 3:
                payoff_threads.append(thread_text)
            else:
                dangling_hooks.append(thread_text)

    resolved_ratio = resolved_count / total_threads if total_threads > 0 else 1.0
    conclusion_ready = (
        resolved_ratio >= required_ratio
        and turns_in_stage >= CONCLUSION_MIN_RESOLUTION_TURNS
    )

    return {
        "ending_style": ending_style,
        "conclusion_ready": conclusion_ready,
        "resolved_ratio": round(resolved_ratio, 2),
        "dangling_hooks": dangling_hooks[:10],
        "payoff_threads": payoff_threads[:10],
    }


def _build_arc_summary(
    arc_number: int,
    arc_id: str,
    ending_style: str,
    conclusion_plan: dict,
    alignment: dict | None,
    companion_states: dict | None,
) -> str:
    """Build a one-paragraph deterministic arc summary for cross-arc memory bridging."""
    payoffs = conclusion_plan.get("payoff_threads") or []
    hooks = conclusion_plan.get("dangling_hooks") or []
    payoff_text = "; ".join(payoffs[:3]) if payoffs else "none tracked"
    hook_text = "; ".join(hooks[:3]) if hooks else "none"

    alignment_text = ""
    if isinstance(alignment, dict):
        top_tone = max(alignment, key=alignment.get, default=None)  # type: ignore[arg-type]
        if top_tone:
            alignment_text = f" Player leaned {top_tone}."

    companion_text = ""
    if isinstance(companion_states, dict):
        milestones = []
        for cid, cstate in list(companion_states.items())[:3]:
            influence = cstate.get("influence", 0) if isinstance(cstate, dict) else 0
            if abs(influence) >= 30:
                label = "allied" if influence > 0 else "strained"
                milestones.append(f"{cid} ({label})")
        if milestones:
            companion_text = f" Companions: {', '.join(milestones)}."

    return (
        f"Arc {arc_number} ({arc_id}): {ending_style}. "
        f"Resolved: {payoff_text}. Unresolved: {hook_text}.{alignment_text}{companion_text}"
    )


def _trigger_arc_transition(
    conclusion_plan: dict,
    arc_state: dict,
    world_state: dict,
    campaign_scale: str,
    turn_number: int,
) -> tuple[dict, dict | None]:
    """Check if the current arc should transition to a new one or trigger epilogue.

    Returns (updated_arc_state, new_arc_seed_or_None).
    If no transition is warranted, returns the arc_state unchanged and None.
    """
    if not conclusion_plan.get("conclusion_ready"):
        return arc_state, None

    current_arc_number = arc_state.get("current_arc_number", 1)
    max_arcs = ARC_COUNT_BY_SCALE.get(campaign_scale, 3)
    next_arc_number = current_arc_number + 1

    # Build summary of the completing arc
    alignment = world_state.get("alignment")
    companion_states = world_state.get("party_affinity")
    current_arc_id = arc_state.get("current_arc_id", f"arc_{current_arc_number}")
    ending_style = conclusion_plan.get("ending_style", "soft_cliffhanger")
    summary = _build_arc_summary(
        current_arc_number, current_arc_id, ending_style,
        conclusion_plan, alignment, companion_states,
    )

    # Archive the completing arc
    arc_history = list(arc_state.get("arc_history") or [])
    arc_history.append({
        "arc_id": current_arc_id,
        "arc_number": current_arc_number,
        "arc_seed_summary": summary,
        "dangling_hooks": list(conclusion_plan.get("dangling_hooks") or [])[:5],
        "turns": turn_number - arc_state.get("stage_start_turn", 0),
        "ending_style": ending_style,
    })

    if next_arc_number > max_arcs:
        # Final arc completed — trigger epilogue
        logger.info(
            "Campaign concluding after %d arcs (scale=%s). Entering epilogue.",
            current_arc_number, campaign_scale,
        )
        return {
            **arc_state,
            "arc_history": arc_history,
            "campaign_concluding": True,
            "epilogue_active": True,
            "epilogue_remaining": EPILOGUE_TURNS,
        }, None

    # Build seed for next arc from dangling hooks + world context
    dangling_hooks = conclusion_plan.get("dangling_hooks") or []
    active_factions = world_state.get("active_factions") or []
    faction_goals = [
        f.get("current_goal", "") for f in active_factions[:3]
        if isinstance(f, dict) and f.get("current_goal")
    ]

    new_arc_seed = {
        "opening_threads": dangling_hooks[:3],
        "active_themes": (world_state.get("ledger") or {}).get("active_themes") or [],
        "arc_intent": f"Continue from arc {current_arc_number}: {', '.join(dangling_hooks[:2]) or 'new developments'}",
        "climax_question": None,  # Will be populated by BibleAgent if available
        "faction_context": faction_goals[:2],
    }
    new_arc_id = f"arc_{next_arc_number}"

    logger.info(
        "Arc transition: arc %d -> arc %d (%s). Dangling hooks: %d carried forward.",
        current_arc_number, next_arc_number, new_arc_id, len(dangling_hooks),
    )

    updated_state = {
        "current_stage": "SETUP",
        "stage_start_turn": turn_number,
        "interlude_remaining": INTERLUDE_MAX_TURNS,
        "current_arc_number": next_arc_number,
        "current_arc_id": new_arc_id,
        "arc_history": arc_history,
        "campaign_concluding": False,
        "epilogue_active": False,
        "epilogue_remaining": 0,
    }

    return updated_state, new_arc_seed


def arc_planner_node(state: dict[str, Any]) -> dict[str, Any]:
    """Deterministic arc planner: reads ledger + turn_number, writes arc_guidance.

    V2.5: Content-aware transitions + thematic guidance.
    V8.0: Multi-arc chaining — RESOLUTION triggers new arcs or epilogue.
    Phase 0.5: Prologue branch — when prologue_mode is active in world_state_json,
    use the constrained PROLOGUE_STAGES loop instead of SETUP→RESOLUTION.
    """
    turn_number = int(state.get("turn_number") or 0)
    campaign = state.get("campaign") or {}
    ws = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
    ws = ws if isinstance(ws, dict) else {}

    # ── Origin branch (runs before prologue) ─────────────────────────
    if ws.get("origin_mode"):
        try:
            from backend.app.core.origin_engine import build_origin_arc_guidance
            arc_guidance = build_origin_arc_guidance(ws, turn_number)
            return {**state, "arc_guidance": arc_guidance}
        except Exception as _origin_err:
            logger.warning(
                "Origin arc_guidance failed (non-fatal), falling back to prologue/normal: %s",
                _origin_err,
            )
            # Fall through to prologue or normal arc planner

    # ── Prologue branch ────────────────────────────────────────────────
    if ws.get("prologue_mode"):
        try:
            from backend.app.core.prologue_engine import build_prologue_arc_guidance
            arc_guidance = build_prologue_arc_guidance(ws, turn_number)
            return {**state, "arc_guidance": arc_guidance}
        except Exception as _prologue_err:
            logger.warning(
                "Prologue arc_guidance failed (non-fatal), falling back to normal arc: %s",
                _prologue_err,
            )
            # Fall through to normal arc planner

    ledger = ws.get("ledger") if isinstance(ws, dict) else {}
    if not isinstance(ledger, dict):
        ledger = {}

    # Load persisted arc state (if any)
    arc_state = ws.get("arc_state") or {}
    if not isinstance(arc_state, dict):
        arc_state = {}
    current_stage = arc_state.get("current_stage")
    stage_start_turn = int(arc_state.get("stage_start_turn", 0))

    # Multi-arc fields (V8.0) — initialize defaults for existing campaigns
    current_arc_number = int(arc_state.get("current_arc_number", 1))
    current_arc_id = arc_state.get("current_arc_id", f"arc_{current_arc_number}")
    arc_history = list(arc_state.get("arc_history") or [])
    campaign_concluding = bool(arc_state.get("campaign_concluding", False))
    epilogue_active = bool(arc_state.get("epilogue_active", False))
    epilogue_remaining = int(arc_state.get("epilogue_remaining", 0))
    campaign_complete = bool(arc_state.get("campaign_complete", False))
    new_arc_seed_for_ws: dict | None = None

    # First-ever turn: initialize to SETUP
    if current_stage is None:
        current_stage = "SETUP"
        stage_start_turn = turn_number

    # ── Epilogue handling ─────────────────────────────────────────────
    # If campaign is already complete, return minimal guidance.
    if campaign_complete:
        arc_guidance = {
            "arc_stage": "RESOLUTION",
            "priority_threads": [],
            "tension_level": "CALM",
            "pacing_hint": "Campaign is complete.",
            "suggested_weight": _WEIGHTS_BY_STAGE["RESOLUTION"],
            "transition_occurred": False,
            "turns_in_stage": 0,
            "active_themes": [],
            "theme_guidance": "",
            "hero_beat": "RETURN_WITH_ELIXIR",
            "hero_pacing": "",
            "archetype_hints": [],
            "era_transition_pending": False,
            "interlude_active": False,
            "arc_state": arc_state,
            "campaign_complete": True,
        }
        return {**state, "arc_guidance": arc_guidance}

    # If epilogue is active, count down and generate epilogue guidance.
    if epilogue_active:
        epilogue_remaining = max(0, epilogue_remaining - 1)
        if epilogue_remaining <= 0:
            campaign_complete = True
            logger.info("Campaign complete! Epilogue finished at turn %d.", turn_number)

        arc_guidance = {
            "arc_stage": "RESOLUTION",
            "priority_threads": [],
            "tension_level": "BITTERSWEET",
            "pacing_hint": EPILOGUE_PACING_HINT,
            "suggested_weight": {"SOCIAL": 0.6, "EXPLORE": 0.3, "COMMIT": 0.1},
            "transition_occurred": False,
            "turns_in_stage": 0,
            "active_themes": (ledger.get("active_themes") or [])[:3],
            "theme_guidance": "Reflect on how themes were resolved or transformed across the saga.",
            "hero_beat": "RETURN_WITH_ELIXIR",
            "hero_pacing": "The hero returns transformed. Show the new status quo.",
            "archetype_hints": [],
            "era_transition_pending": False,
            "interlude_active": False,
            "campaign_concluding": True,
            "epilogue_active": True,
            "campaign_complete": campaign_complete,
            "arc_history": arc_history,
            "current_arc_number": current_arc_number,
            "arc_state": {
                "current_stage": "RESOLUTION",
                "stage_start_turn": stage_start_turn,
                "interlude_remaining": 0,
                "current_arc_number": current_arc_number,
                "current_arc_id": current_arc_id,
                "arc_history": arc_history,
                "campaign_concluding": True,
                "epilogue_active": True,
                "epilogue_remaining": epilogue_remaining,
                "campaign_complete": campaign_complete,
            },
        }
        return {**state, "arc_guidance": arc_guidance}

    # ── Normal arc stage progression ──────────────────────────────────
    recent_narrative = "\n".join((state.get("recent_narrative") or [])[-2:])[:500]
    arc_stage, transition_occurred, arc_weaver_result = _determine_arc_stage_dynamic(
        turn_number, ledger, current_stage, stage_start_turn,
        recent_narrative=recent_narrative,
    )

    if transition_occurred:
        stage_start_turn = turn_number
        logger.info("Arc transition: %s -> %s at turn %d", current_stage, arc_stage, turn_number)

    # ── Multi-arc chaining (V8.0) ─────────────────────────────────────
    # When RESOLUTION is reached and conclusion is ready, trigger next arc or epilogue.
    interlude_active = False
    interlude_turns_remaining = 0
    _interlude_state = arc_state.get("interlude_remaining", 0)

    if arc_stage == "RESOLUTION" and not campaign_concluding:
        turns_in_res = max(0, turn_number - stage_start_turn)
        campaign_scale = ws.get("campaign_scale") or "medium"
        conclusion_plan = _build_conclusion_plan(
            arc_stage=arc_stage,
            turns_in_stage=turns_in_res,
            campaign_scale=campaign_scale,
            ledger=ledger,
        )
        if conclusion_plan and conclusion_plan.get("conclusion_ready"):
            updated_arc_state, new_seed = _trigger_arc_transition(
                conclusion_plan=conclusion_plan,
                arc_state={
                    **arc_state,
                    "current_arc_number": current_arc_number,
                    "current_arc_id": current_arc_id,
                    "arc_history": arc_history,
                    "stage_start_turn": stage_start_turn,
                },
                world_state=ws,
                campaign_scale=campaign_scale,
                turn_number=turn_number,
            )

            if updated_arc_state.get("epilogue_active"):
                # Epilogue triggered — will be handled on next turn
                epilogue_active = True
                epilogue_remaining = updated_arc_state.get("epilogue_remaining", EPILOGUE_TURNS)
                campaign_concluding = True
                arc_history = updated_arc_state.get("arc_history", arc_history)
            elif new_seed is not None:
                # New arc — transition to SETUP with interlude
                arc_stage = "SETUP"
                stage_start_turn = turn_number
                transition_occurred = True
                current_arc_number = updated_arc_state.get("current_arc_number", current_arc_number + 1)
                current_arc_id = updated_arc_state.get("current_arc_id", f"arc_{current_arc_number}")
                arc_history = updated_arc_state.get("arc_history", arc_history)
                _interlude_state = INTERLUDE_MAX_TURNS
                new_arc_seed_for_ws = new_seed
                logger.info("New arc %d (%s) begins at turn %d", current_arc_number, current_arc_id, turn_number)

    # Phase 3.3: Between-Arc Interlude — decompression turns on new arc start.
    if _interlude_state > 0:
        interlude_active = True
        interlude_turns_remaining = _interlude_state - 1  # Will be persisted for next turn

    tension_level = _determine_tension(arc_stage, ledger)
    if interlude_active:
        tension_level = "CALM"

    # Priority threads: top 2 from open_threads
    open_threads = ledger.get("open_threads") or []
    priority_threads = open_threads[:2]

    pacing_hint = _PACING_HINTS.get(arc_stage, "")
    if interlude_active:
        pacing_hint = INTERLUDE_PACING_HINT
    suggested_weight = _WEIGHTS_BY_STAGE.get(
        arc_stage, {"SOCIAL": 0.33, "EXPLORE": 0.34, "COMMIT": 0.33}
    )

    # Theme guidance (Phase 3)
    active_themes = ledger.get("active_themes") or []

    # Hybrid setup seed (if present): use setup-time arc seed as initial scaffold,
    # then continue deterministic progression from ledger + turn state.
    arc_seed = ws.get("arc_seed") if isinstance(ws, dict) else {}
    if not isinstance(arc_seed, dict):
        arc_seed = {}
    seed_themes = [str(t).strip() for t in (arc_seed.get("active_themes") or []) if str(t).strip()]
    if not active_themes and seed_themes:
        active_themes = seed_themes[:3]

    seed_threads = [str(t).strip() for t in (arc_seed.get("opening_threads") or []) if str(t).strip()]
    if turn_number <= 3 and seed_threads:
        seed_priority_threads = seed_threads[:2]
        if not priority_threads:
            priority_threads = seed_priority_threads

    theme_guidance = _THEME_GUIDANCE_BY_STAGE.get(arc_stage, "") if active_themes else ""

    # Hero's Journey sub-beat (deterministic, based on turns in stage)
    turns_in_stage = max(0, turn_number - stage_start_turn)
    min_t = ARC_MIN_TURNS.get(arc_stage, 3)
    max_t = ARC_MAX_TURNS.get(arc_stage, 999)
    hero_beat_info = _determine_hero_beat(arc_stage, turns_in_stage, min_t, max_t)
    hero_beat = hero_beat_info.get("beat", "UNKNOWN")
    hero_pacing = hero_beat_info.get("pacing", "")
    archetype_hints = _get_archetype_hints(hero_beat)

    if transition_occurred:
        logger.info("Hero beat: %s (stage %s, turn %d in stage)", hero_beat, arc_stage, turns_in_stage)

    # Combine stage pacing with hero beat pacing
    if hero_pacing:
        pacing_hint = f"{pacing_hint} {hero_pacing}"

    # Era transition check: when RESOLUTION is sufficiently complete
    era_transition_pending = False
    current_era = campaign.get("time_period") or campaign.get("era") or ""
    if arc_stage == "RESOLUTION" and turns_in_stage >= 2 and current_era:
        from backend.app.core.era_transition import can_transition
        era_transition_pending = can_transition(
            current_era, arc_stage,
            arc_guidance={"turns_in_stage": turns_in_stage},
        )
        if era_transition_pending:
            logger.info("Era transition available: %s (turn %d in RESOLUTION)", current_era, turns_in_stage)

    # ── V10.0 Feature 10: Arc mood profile ─────────────────────────────
    _mood_profile_key = ws.get("arc_mood_profile") or DEFAULT_ARC_MOOD_PROFILE
    _mood_profiles = ARC_MOOD_PROFILES.get(_mood_profile_key) or ARC_MOOD_PROFILES[DEFAULT_ARC_MOOD_PROFILE]
    _mood_for_stage = _mood_profiles.get(arc_stage, "")

    # ── V10.0 Feature 5: Foreshadowing hooks ─────────────────────────────
    foreshadow_hints: list[dict] = []
    if arc_stage in ("SETUP", "RISING"):
        # Seed from dangling hooks of previous arcs
        for prev_arc in arc_history:
            if isinstance(prev_arc, dict):
                for hook in (prev_arc.get("dangling_hooks") or [])[:2]:
                    if len(foreshadow_hints) >= FORESHADOW_MAX_HINTS:
                        break
                    foreshadow_hints.append({
                        "type": "dangling_hook",
                        "hint": f"Subtly reference: {hook}",
                        "payoff_arc": "future",
                    })
        # Seed from NPC agendas with hidden motivations
        _npc_states_fh = ws.get("npc_states") or {}
        if isinstance(_npc_states_fh, dict) and len(foreshadow_hints) < FORESHADOW_MAX_HINTS:
            for npc_id, npc_data in list(_npc_states_fh.items())[:10]:
                if len(foreshadow_hints) >= FORESHADOW_MAX_HINTS:
                    break
                if isinstance(npc_data, dict):
                    agenda = (npc_data.get("agenda") or "").strip()
                    if agenda and any(kw in agenda.lower() for kw in ("secret", "hidden", "betray", "plan", "deceive")):
                        foreshadow_hints.append({
                            "type": "npc_secret",
                            "hint": f"Environmental hint toward: {npc_id} — {agenda}",
                            "payoff_arc": "this_arc",
                        })

    # ── V10.0 Feature 9: Thematic resonance (CLIMAX echoes early themes) ──
    _thematic_echoes = None
    if arc_stage == "CLIMAX":
        _arc_consequences = ws.get("arc_consequences") or {}
        _arc_cons_history = _arc_consequences.get("arc_history") or [] if isinstance(_arc_consequences, dict) else []
        if _arc_cons_history and isinstance(_arc_cons_history, list):
            _first_arc = _arc_cons_history[0] if _arc_cons_history else {}
            _first_sig = _first_arc.get("thematic_signature") or {} if isinstance(_first_arc, dict) else {}
            _early_themes = _first_sig.get("dominant_themes") or [] if isinstance(_first_sig, dict) else []
            if _early_themes:
                _thematic_echoes = {
                    "early_themes": _early_themes,
                    "resonance_note": (
                        f"This campaign began with themes of {', '.join(str(t).replace('_', ' ') for t in _early_themes[:3])}. "
                        f"Consider how this climax confronts or subverts those themes."
                    ),
                }

    arc_guidance = {
        "arc_stage": arc_stage,
        "priority_threads": priority_threads,
        "seed_climax_question": str(arc_seed.get("climax_question") or "").strip() or None,
        "arc_intent": str(arc_seed.get("arc_intent") or "").strip() or None,
        "tension_level": tension_level,
        "pacing_hint": pacing_hint,
        "suggested_weight": suggested_weight,
        "transition_occurred": transition_occurred,
        "turns_in_stage": turns_in_stage,
        "active_themes": active_themes,
        "theme_guidance": theme_guidance,
        # Hero's Journey beat tracking
        "hero_beat": hero_beat,
        "hero_pacing": hero_pacing,
        "archetype_hints": archetype_hints,
        # Era transition flag
        "era_transition_pending": era_transition_pending,
        # Phase 3.3: Interlude state
        "interlude_active": interlude_active,
        # Multi-arc tracking (V8.0)
        "current_arc_number": current_arc_number,
        "current_arc_id": current_arc_id,
        "arc_history": arc_history,
        "campaign_concluding": campaign_concluding,
        "epilogue_active": epilogue_active,
        "campaign_complete": campaign_complete,
        # Saga context for narrator (first 3 turns of new arc)
        "saga_context": (
            arc_history[-1]["arc_seed_summary"]
            if arc_history and current_arc_number > 1 and turns_in_stage <= 3
            else None
        ),
        # V10.0 Feature 10: Mood profile for tonal guidance
        "mood_directive": _mood_for_stage,
        "mood_profile": _mood_profile_key,
        # V10.0 Feature 5: Foreshadowing hooks
        "foreshadow_hints": foreshadow_hints,
        # V10.0 Feature 9: Thematic resonance across arcs
        "thematic_echoes": _thematic_echoes,
        # New arc seed to persist (commit node writes to world_state["arc_seed"])
        "new_arc_seed": new_arc_seed_for_ws,
        # Arc state for persistence (Commit node picks this up)
        "arc_state": {
            "current_stage": arc_stage,
            "stage_start_turn": stage_start_turn,
            "interlude_remaining": interlude_turns_remaining,
            "current_arc_number": current_arc_number,
            "current_arc_id": current_arc_id,
            "arc_history": arc_history,
            "campaign_concluding": campaign_concluding,
            "epilogue_active": epilogue_active,
            "epilogue_remaining": epilogue_remaining,
            "campaign_complete": campaign_complete,
        },
    }

    # ── V8.0 Gate 4: Tiered scene loop escalation ───────────────────
    # Track consecutive loop turns and escalate disruption progressively.
    _prev_loop_count = int(arc_state.get("scene_loop_consecutive", 0))
    if state.get("scene_loop_detected"):
        _loop_count = _prev_loop_count + 1
        arc_guidance["scene_loop_detected"] = True
        arc_guidance["scene_loop_consecutive"] = _loop_count
        # Persist in arc_state for next turn
        arc_guidance["arc_state"]["scene_loop_consecutive"] = _loop_count

        if _loop_count >= 3:
            # Tier 3: Force a world event — WorldSim should escalate
            loop_escalation = (
                "SCENE STAGNATION CRITICAL (3+ turns): The narrative is stuck. "
                "FORCE a disruption: a faction makes a sudden move, an NPC arrives with "
                "urgent news that changes the situation entirely, or an environmental "
                "event (alarm, explosion, storm) forces the player to react. "
                "This MUST fundamentally change the scene."
            )
            arc_guidance["force_world_event"] = True
        elif _loop_count >= 2:
            # Tier 2: Director-level disruption
            loop_escalation = (
                "SCENE STAGNATION DETECTED (2+ turns): Introduce a disruption — "
                "an NPC arrives with urgent news, a faction makes a move that changes "
                "the situation, or a companion breaks the tension with a question or "
                "challenge. Choose ONE. Make it feel organic, not forced."
            )
        else:
            # Tier 1: Gentle escalation hint
            loop_escalation = (
                "SCENE LOOP DETECTED: The player has been in a similar scene recently. "
                "ESCALATE: introduce a new complication, reveal new information, "
                "or shift the environment. Do NOT repeat the same scene beats."
            )

        arc_guidance["pacing_hint"] = f"{arc_guidance.get('pacing_hint', '')} {loop_escalation}".strip()
        # Bump tension if calm
        if arc_guidance.get("tension_level") in ("CALM", "BUILDING"):
            arc_guidance["tension_level"] = "ESCALATING"
        logger.info("Arc planner scene loop escalation tier=%d", _loop_count)
    else:
        # Reset consecutive counter when scene changes
        if _prev_loop_count > 0:
            logger.info("Scene loop broken — resetting consecutive counter from %d", _prev_loop_count)
        arc_guidance["scene_loop_consecutive"] = 0
        arc_guidance["arc_state"]["scene_loop_consecutive"] = 0

    # ── Scale advisor (gated by ENABLE_SCALE_ADVISOR) ────────────────
    try:
        from backend.app.config import ENABLE_SCALE_ADVISOR
        if ENABLE_SCALE_ADVISOR:
            current_scale = ws.get("campaign_scale") or "medium"
            last_scale_change_turn = int(ws.get("last_scale_change_turn") or 0)
            pivotal_event_count = int(ws.get("pivotal_event_count") or 0)
            scale_rec = _evaluate_scale_recommendation(
                current_scale=current_scale,
                arc_stage=arc_stage,
                tension_level=tension_level,
                ledger=ledger,
                turn_number=turn_number,
                last_scale_change_turn=last_scale_change_turn,
                pivotal_event_count=pivotal_event_count,
            )
            if scale_rec:
                arc_guidance["scale_recommendation"] = scale_rec
                logger.info(
                    "Scale advisor recommends %s (%s): %s",
                    scale_rec["recommended_scale"],
                    scale_rec["direction"],
                    scale_rec["reason"],
                )
    except Exception as _scale_err:
        logger.warning("Scale advisor failed (non-fatal): %s", _scale_err)

    # ── Conclusion planner (active during RESOLUTION) ────────────────
    try:
        campaign_scale = ws.get("campaign_scale") or "medium"
        conclusion_plan = _build_conclusion_plan(
            arc_stage=arc_stage,
            turns_in_stage=turns_in_stage,
            campaign_scale=campaign_scale,
            ledger=ledger,
        )
        if conclusion_plan:
            arc_guidance["conclusion_plan"] = conclusion_plan
            if conclusion_plan.get("conclusion_ready"):
                logger.info(
                    "Conclusion ready: style=%s ratio=%.2f",
                    conclusion_plan["ending_style"],
                    conclusion_plan["resolved_ratio"],
                )
    except Exception as _concl_err:
        logger.warning("Conclusion planner failed (non-fatal): %s", _concl_err)

    return {
        **state,
        "arc_guidance": arc_guidance,
    }
