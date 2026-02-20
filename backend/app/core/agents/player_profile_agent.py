"""PlayerProfileAgent: deterministic player behavioral profiling (V10.0 Feature 4).

Runs every ~10 turns. Analyzes player choice patterns (not narrative content)
to build a behavioral profile the Director uses for engagement-aware pacing.

No LLM calls — pure Python analysis of choice_history data.
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------


def _compute_distribution(history: list[dict], key: str) -> dict[str, float]:
    """Compute percentage distribution of a categorical field across history."""
    values = [h.get(key, "UNKNOWN") for h in history if h.get(key)]
    if not values:
        return {}
    counts = Counter(values)
    total = len(values)
    return {k: round(v / total, 2) for k, v in counts.most_common()}


def _compute_risk_profile(history: list[dict]) -> str:
    """Derive risk tolerance label from choice risk distribution."""
    dist = _compute_distribution(history, "risk")
    risky_pct = dist.get("RISKY", 0.0) + dist.get("DANGEROUS", 0.0)
    if risky_pct >= 0.4:
        return "bold"
    elif risky_pct >= 0.15:
        return "moderate"
    return "cautious"


def _compute_creativity_ratio(history: list[dict]) -> float:
    """Ratio of free-text inputs to structured choice clicks."""
    if not history:
        return 0.0
    free_count = sum(1 for h in history if h.get("is_free_text"))
    return round(free_count / len(history), 2)


def _compute_engagement_trend(history: list[dict], window: int = 10) -> str:
    """Detect engagement trend from input length over recent window."""
    if len(history) < window * 2:
        return "stable"
    recent = history[-window:]
    earlier = history[-window * 2:-window]
    avg_recent = sum(h.get("input_length", 0) for h in recent) / max(len(recent), 1)
    avg_earlier = sum(h.get("input_length", 0) for h in earlier) / max(len(earlier), 1)
    if avg_earlier == 0:
        return "stable"
    change = (avg_recent - avg_earlier) / avg_earlier
    if change < -0.3:
        return "declining"
    elif change > 0.3:
        return "rising"
    return "stable"


def _detect_boredom_signals(history: list[dict], window: int = 10) -> bool:
    """Detect possible player disengagement from repetitive patterns."""
    from backend.app.constants import (
        PLAYER_BOREDOM_REPETITION_THRESHOLD,
        PLAYER_BOREDOM_INPUT_LENGTH_DECLINE,
    )
    if len(history) < window:
        return False
    recent = history[-window:]
    # Signal 1: Same tone > threshold of last N choices
    tones = [h.get("tone", "NEUTRAL") for h in recent]
    tone_counts = Counter(tones)
    if tone_counts and tone_counts.most_common(1)[0][1] / len(tones) > PLAYER_BOREDOM_REPETITION_THRESHOLD:
        return True
    # Signal 2: Average input length declining sharply
    if len(history) >= window * 2:
        avg_recent = sum(h.get("input_length", 0) for h in recent) / window
        avg_earlier = sum(h.get("input_length", 0) for h in history[-window * 2:-window]) / window
        if avg_earlier > 0 and (avg_recent / avg_earlier) < PLAYER_BOREDOM_INPUT_LENGTH_DECLINE:
            return True
    return False


def _derive_play_style(tone_dist: dict[str, float], action_dist: dict[str, float]) -> str:
    """Derive a human-readable play style label from distributions."""
    top_tone = max(tone_dist, key=tone_dist.get, default="NEUTRAL") if tone_dist else "NEUTRAL"
    top_action = max(action_dist, key=action_dist.get, default="TALK") if action_dist else "TALK"

    if top_action in ("DO", "USE_ABILITY") and top_tone == "RENEGADE":
        return "fighter"
    if top_action == "INVESTIGATE" or top_tone == "INVESTIGATE":
        return "explorer"
    if top_action == "TALK" and top_tone == "PARAGON":
        return "diplomat"
    if top_action == "TALK" and top_tone in ("RENEGADE", "NEUTRAL"):
        return "provocateur"
    if top_action == "TRAVEL":
        return "wanderer"
    return "balanced"


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class PlayerProfileAgent:
    """Deterministic player behavioral profiling.

    Analyzes choice_history to build a profile of player tendencies:
    preferred tone, action type, risk tolerance, engagement signals.
    Writes result to world_state["player_behavior_profile"].
    """

    def analyze(
        self,
        world_state: dict[str, Any],
        state_snapshot: dict[str, Any],
        turn_number: int,
    ) -> None:
        """Build player_behavior_profile from accumulated choice_history."""
        history = world_state.get("choice_history") or []
        if not history:
            logger.debug("PlayerProfileAgent: no choice_history yet, skipping")
            return

        tone_dist = _compute_distribution(history, "tone")
        action_dist = _compute_distribution(history, "action_type")

        profile = {
            "preferred_tone": tone_dist,
            "preferred_action": action_dist,
            "risk_tolerance": _compute_risk_profile(history),
            "creativity_ratio": _compute_creativity_ratio(history),
            "engagement_trend": _compute_engagement_trend(history),
            "play_style": _derive_play_style(tone_dist, action_dist),
            "possible_boredom": _detect_boredom_signals(history),
            "turn_analyzed": turn_number,
            "sample_size": len(history),
        }

        world_state["player_behavior_profile"] = profile
        logger.info(
            "PlayerProfileAgent: profiled player at turn %d "
            "(style=%s, risk=%s, boredom=%s, samples=%d)",
            turn_number,
            profile["play_style"],
            profile["risk_tolerance"],
            profile["possible_boredom"],
            len(history),
        )
