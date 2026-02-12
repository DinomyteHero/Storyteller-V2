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
    ARC_MAX_TURNS,
    ARC_MIN_TURNS,
    ARC_RISING_TO_CLIMAX_MIN_THREADS,
    ARC_SETUP_TO_RISING_MIN_FACTS,
    ARC_SETUP_TO_RISING_MIN_THREADS,
    BEAT_ARCHETYPE_HINTS,
    CONCLUSION_ENDING_STYLES,
    CONCLUSION_MIN_RESOLUTION_TURNS,
    CONCLUSION_RESOLVED_RATIO,
    HERO_JOURNEY_BEATS,
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
) -> tuple[str, bool]:
    """Determine arc stage using content-aware transitions with min/max guards.

    Returns (stage, transition_occurred).
    """
    if current_stage is None:
        return "SETUP", False

    turns_in_stage = max(0, turn_number - stage_start_turn)
    min_turns = ARC_MIN_TURNS.get(current_stage, 3)
    max_turns = ARC_MAX_TURNS.get(current_stage, 999)

    # Don't transition before minimum turns
    if turns_in_stage < min_turns:
        return current_stage, False

    threads = ledger.get("open_threads") or []
    facts = ledger.get("established_facts") or []
    flags = [f for f in facts if f.startswith("Flag set:")]

    # 2.4: Use weighted thread count — a W3 plot thread counts as 3 toward thresholds
    thread_score = weighted_thread_count(threads)

    ready_to_advance = False

    if current_stage == "SETUP":
        # Need enough thread weight and facts to move to RISING
        if thread_score >= ARC_SETUP_TO_RISING_MIN_THREADS and len(facts) >= ARC_SETUP_TO_RISING_MIN_FACTS:
            ready_to_advance = True
    elif current_stage == "RISING":
        # Need enough thread weight and narrative density to move to CLIMAX
        if thread_score >= ARC_RISING_TO_CLIMAX_MIN_THREADS:
            ready_to_advance = True
    elif current_stage == "CLIMAX":
        # Move to RESOLUTION when a "resolved" flag appears
        resolved_flags = [f for f in flags if ARC_CLIMAX_RESOLUTION_FLAG_PREFIX in f.lower()]
        if resolved_flags:
            ready_to_advance = True
    elif current_stage == "RESOLUTION":
        return "RESOLUTION", False  # Terminal stage

    # Force transition if max turns exceeded
    if turns_in_stage >= max_turns:
        ready_to_advance = True

    if ready_to_advance:
        idx = _STAGE_ORDER.index(current_stage) if current_stage in _STAGE_ORDER else 0
        if idx < len(_STAGE_ORDER) - 1:
            return _STAGE_ORDER[idx + 1], True

    return current_stage, False


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


def arc_planner_node(state: dict[str, Any]) -> dict[str, Any]:
    """Deterministic arc planner: reads ledger + turn_number, writes arc_guidance.

    V2.5: Content-aware transitions + thematic guidance.
    """
    turn_number = int(state.get("turn_number") or 0)
    campaign = state.get("campaign") or {}
    ws = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
    ws = ws if isinstance(ws, dict) else {}
    ledger = ws.get("ledger") if isinstance(ws, dict) else {}
    if not isinstance(ledger, dict):
        ledger = {}

    # Load persisted arc state (if any)
    arc_state = ws.get("arc_state") or {}
    current_stage = arc_state.get("current_stage") if isinstance(arc_state, dict) else None
    stage_start_turn = int(arc_state.get("stage_start_turn", 0)) if isinstance(arc_state, dict) else 0

    # First-ever turn: initialize to SETUP
    if current_stage is None:
        current_stage = "SETUP"
        stage_start_turn = turn_number

    arc_stage, transition_occurred = _determine_arc_stage_dynamic(
        turn_number, ledger, current_stage, stage_start_turn,
    )

    if transition_occurred:
        stage_start_turn = turn_number
        logger.info("Arc transition: %s -> %s at turn %d", current_stage, arc_stage, turn_number)

    tension_level = _determine_tension(arc_stage, ledger)

    # Priority threads: top 2 from open_threads
    open_threads = ledger.get("open_threads") or []
    priority_threads = open_threads[:2]

    pacing_hint = _PACING_HINTS.get(arc_stage, "")
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
        # Arc state for persistence (Commit node picks this up)
        "arc_state": {
            "current_stage": arc_stage,
            "stage_start_turn": stage_start_turn,
        },
    }

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
