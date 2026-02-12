"""Deterministic companion approval and banter from MechanicResult (trait weights, no LLM)."""
from __future__ import annotations

from typing import Any

import random

from backend.app.constants import (
    BANTER_MEMORY_POOL,
    BANTER_POOL,
    COMPANION_ARC_LOYAL_MIN,
    COMPANION_ARC_STRANGER_MAX,
    COMPANION_ARC_TRUSTED_MIN,
    COMPANION_CONFLICT_SHARP_DROP,
    COMPANION_CONFLICT_THRESHOLD_CROSS,
    COMPANION_MAX_MEMORIES,
    COMPANION_EMOTION_DECAY_PER_TURN,
    COMPANION_EMOTION_MAX_INTENSITY,
    COMPANION_EMOTION_MULTIPLIERS,
)
from backend.app.models.state import (
    TONE_TAG_PARAGON,
    TONE_TAG_RENEGADE,
    TONE_TAG_INVESTIGATE,
    TONE_TAG_NEUTRAL,
)

# Affinity delta bounds per turn (deterministic)
AFFINITY_DELTA_MIN = -5
AFFINITY_DELTA_MAX = 5
# Loyalty nudge: small progress when affinity moves positive
LOYALTY_NUDGE_ON_APPROVAL = 1
# Banter: at most one enqueue every BANTER_COOLDOWN_TURNS
BANTER_COOLDOWN_TURNS = 3
# Mood thresholds for party_status.mood_tag
MOOD_WARM_THRESHOLD = 50
MOOD_WARY_THRESHOLD = -50  # below this = Hostile; between WARY and WARM = Wary/Neutral


def _trait(party_traits: dict[str, dict[str, int]], companion_id: str, key: str) -> int:
    """Get trait value for companion; 0 if missing."""
    traits = (party_traits or {}).get(companion_id) or {}
    return int(traits.get(key, 0))


def _score_paragon(traits: dict[str, int]) -> int:
    """Positive = likes PARAGON (idealist, merciful). idealist_pragmatic > 0, merciful_ruthless < 0."""
    idealist = traits.get("idealist_pragmatic", 0)
    merciful = traits.get("merciful_ruthless", 0)
    # Idealists (positive) and merciful (negative) like PARAGON
    return idealist - merciful  # high when idealist and merciful


def _score_renegade(traits: dict[str, int]) -> int:
    """Positive = likes RENEGADE (pragmatic, ruthless). idealist_pragmatic < 0, merciful_ruthless > 0."""
    idealist = traits.get("idealist_pragmatic", 0)
    merciful = traits.get("merciful_ruthless", 0)
    return -idealist + merciful


def _score_investigate(traits: dict[str, int]) -> int:
    """Positive = likes INVESTIGATE (cautious, pragmatic). lawful_rebellious < 0 = cautious; idealist_pragmatic < 30."""
    lawful = traits.get("lawful_rebellious", 0)
    idealist = traits.get("idealist_pragmatic", 0)
    # Cautious (negative lawful) and slightly pragmatic (low idealist) like gathering intel
    return -lawful + max(0, 30 - idealist)


def _tone_match_score(tone_tag: str, traits: dict[str, int]) -> int:
    """Return a score indicating how much this companion likes the tone. Positive = likes."""
    tone = (tone_tag or TONE_TAG_NEUTRAL).upper()
    if tone == TONE_TAG_PARAGON:
        return _score_paragon(traits)
    if tone == TONE_TAG_RENEGADE:
        return _score_renegade(traits)
    if tone == TONE_TAG_INVESTIGATE:
        return _score_investigate(traits)
    return 0


def _score_to_affinity_delta(score: int) -> int:
    """Map trait-vs-tone score to a bounded affinity delta. Score in roughly -200..200 -> delta -5..5. 0 -> 0."""
    if score >= 50:
        return min(AFFINITY_DELTA_MAX, 3)
    if score >= 20:
        return 2
    if score > 0:
        return 1
    if score == 0:
        return 0
    if score >= -20:
        return -1
    if score >= -50:
        return -2
    return max(AFFINITY_DELTA_MIN, -3)


def compute_companion_reactions(
    party: list[str],
    party_traits: dict[str, dict[str, int]],
    mechanic_result: dict[str, Any] | Any,
) -> tuple[dict[str, int], dict[str, str]]:
    """Compute affinity deltas and short reasons from mechanic result (deterministic).

    - Uses mechanic_result.tone_tag and alignment_delta as primary signals.
    - If mechanic_result has companion_affinity_delta explicitly, that overrides computed for that companion.
    Returns (affinity_delta_map, reasons_map).
    """
    affinity_delta_map: dict[str, int] = {}
    reasons_map: dict[str, str] = {}

    # Normalize to dict for consistent access
    if hasattr(mechanic_result, "model_dump"):
        mr = mechanic_result.model_dump(mode="json")
    elif isinstance(mechanic_result, dict):
        mr = mechanic_result
    else:
        return affinity_delta_map, reasons_map

    tone_tag = (mr.get("tone_tag") or TONE_TAG_NEUTRAL).strip().upper()
    alignment_delta = mr.get("alignment_delta") or {}
    explicit_affinity = mr.get("companion_affinity_delta") or {}
    explicit_reasons = mr.get("companion_reaction_reason") or {}

    # V2.21: Companion emotional state from world_state (if available)
    emotional_states: dict[str, str] = {}
    ws = mr.get("__world_state") or {}
    companion_emotions = ws.get("companion_emotions") or {}
    if isinstance(companion_emotions, dict):
        for cid_key, emo_data in companion_emotions.items():
            if isinstance(emo_data, dict):
                emotional_states[cid_key] = emo_data.get("state", "calm")

    for cid in party or []:
        traits = (party_traits or {}).get(cid) or {}
        if cid in explicit_affinity:
            affinity_delta_map[cid] = max(AFFINITY_DELTA_MIN, min(AFFINITY_DELTA_MAX, int(explicit_affinity[cid])))
            reasons_map[cid] = (explicit_reasons.get(cid) or "mechanic override")[:64]
            continue
        score = _tone_match_score(tone_tag, traits)
        delta = _score_to_affinity_delta(score)

        # V2.21: Apply emotional volatility multiplier
        emotion = emotional_states.get(cid, "calm")
        multiplier = COMPANION_EMOTION_MULTIPLIERS.get((tone_tag, emotion), 1.0)
        if multiplier != 1.0 and delta != 0:
            delta = max(AFFINITY_DELTA_MIN, min(AFFINITY_DELTA_MAX, round(delta * multiplier)))

        if delta != 0:
            affinity_delta_map[cid] = delta
            emotion_suffix = f" ({emotion})" if emotion != "calm" else ""
            if tone_tag == TONE_TAG_PARAGON:
                reasons_map[cid] = f"paragon choice{emotion_suffix}" if score > 0 else f"disapproved paragon{emotion_suffix}"
            elif tone_tag == TONE_TAG_RENEGADE:
                reasons_map[cid] = f"renegade choice{emotion_suffix}" if score > 0 else f"disapproved renegade{emotion_suffix}"
            elif tone_tag == TONE_TAG_INVESTIGATE:
                reasons_map[cid] = f"investigate choice{emotion_suffix}" if score > 0 else f"neutral to investigate{emotion_suffix}"
            else:
                reasons_map[cid] = "neutral"
    return affinity_delta_map, reasons_map


def decay_companion_emotions(world_state: dict[str, Any]) -> None:
    """Decay companion emotional intensity by 1 per turn toward calm.

    Called from the companion_reaction node each turn.
    Modifies world_state["companion_emotions"] in place.
    """
    emotions = world_state.get("companion_emotions")
    if not isinstance(emotions, dict):
        return
    for cid, emo_data in list(emotions.items()):
        if not isinstance(emo_data, dict):
            continue
        intensity = int(emo_data.get("intensity", 0))
        if intensity > 0:
            intensity = max(0, intensity - COMPANION_EMOTION_DECAY_PER_TURN)
            emo_data["intensity"] = intensity
            if intensity == 0:
                emo_data["state"] = "calm"
            emotions[cid] = emo_data
    world_state["companion_emotions"] = emotions


def trigger_companion_emotion(
    world_state: dict[str, Any],
    companion_id: str,
    emotion: str,
    intensity: int = 5,
) -> None:
    """Set a companion's emotional state (e.g., after a betrayal or rescue).

    Called from commit node or event processing when significant events occur.
    """
    emotions = world_state.get("companion_emotions")
    if not isinstance(emotions, dict):
        emotions = {}
    emotions[companion_id] = {
        "state": emotion,
        "intensity": min(COMPANION_EMOTION_MAX_INTENSITY, max(0, intensity)),
    }
    world_state["companion_emotions"] = emotions


def update_party_state(
    state: dict[str, Any],
    affinity_deltas: dict[str, int],
    reasons: dict[str, str] | None = None,
    mechanic_result: dict[str, Any] | None = None,
    turn_number: int = 0,
) -> dict[str, Any]:
    """Apply affinity deltas to campaign party_affinity, nudge loyalty_progress,
    detect conflicts, and extract companion moments. Returns updated state (copy)."""
    campaign = dict(state.get("campaign") or {})
    party_affinity = dict(campaign.get("party_affinity") or {})
    old_affinity = dict(party_affinity)  # snapshot before changes
    loyalty_progress = dict(campaign.get("loyalty_progress") or {})
    reasons = reasons or {}

    for cid, delta in affinity_deltas.items():
        party_affinity[cid] = max(-100, min(100, party_affinity.get(cid, 0) + delta))
        if delta > 0:
            loyalty_progress[cid] = min(100, loyalty_progress.get(cid, 0) + LOYALTY_NUDGE_ON_APPROVAL)

    campaign["party_affinity"] = party_affinity
    campaign["loyalty_progress"] = loyalty_progress

    # Phase 5: Detect conflicts
    party = campaign.get("party") or []
    conflicts = detect_companion_conflicts(party, old_affinity, party_affinity, affinity_deltas)
    if conflicts:
        campaign["companion_conflicts"] = conflicts

    # Phase 5: Extract companion moments for significant deltas
    pending_moments: list[dict] = []
    for cid, delta in affinity_deltas.items():
        moment = extract_companion_moments(
            cid, delta, reasons.get(cid, ""), mechanic_result, turn_number,
        )
        if moment:
            pending_moments.append({"companion_id": cid, "text": moment})
    if pending_moments:
        campaign["pending_companion_moments"] = list(campaign.get("pending_companion_moments") or []) + pending_moments

    return {**state, "campaign": campaign}


def apply_alignment_and_faction(
    state: dict[str, Any],
    mechanic_result: dict[str, Any] | Any,
) -> dict[str, Any]:
    """Apply mechanic alignment_delta and faction_reputation_delta to campaign (in-memory). Returns updated state."""
    mr = mechanic_result.model_dump(mode="json") if hasattr(mechanic_result, "model_dump") else (mechanic_result or {})
    if not isinstance(mr, dict):
        return state
    campaign = dict(state.get("campaign") or {})
    alignment = dict(campaign.get("alignment") or {"light_dark": 0, "paragon_renegade": 0})
    faction_reputation = dict(campaign.get("faction_reputation") or {})
    for key, delta in (mr.get("alignment_delta") or {}).items():
        if isinstance(delta, (int, float)):
            alignment[key] = max(-100, min(100, alignment.get(key, 0) + int(delta)))
    for fid, delta in (mr.get("faction_reputation_delta") or {}).items():
        if isinstance(delta, (int, float)):
            faction_reputation[str(fid)] = max(-100, min(100, faction_reputation.get(str(fid), 0) + int(delta)))
    campaign["alignment"] = alignment
    campaign["faction_reputation"] = faction_reputation
    return {**state, "campaign": campaign}


def maybe_enqueue_banter(
    state: dict[str, Any],
    mechanic_result: dict[str, Any] | Any,
) -> tuple[dict[str, Any], str | None]:
    """Rate-limited banter: optionally add one line to banter_queue. Returns (updated_state, line_added_or_None)."""
    mr = mechanic_result.model_dump(mode="json") if hasattr(mechanic_result, "model_dump") else (mechanic_result or {})
    if isinstance(mr, dict) and mr.get("invalid_action"):
        return state, None
    campaign = dict(state.get("campaign") or {})
    party = campaign.get("party") or []
    banter_queue = list(campaign.get("banter_queue") or [])
    turn_number = int(state.get("turn_number") or 0)

    # Rate limit: at most one enqueue every BANTER_COOLDOWN_TURNS
    if party and (turn_number % BANTER_COOLDOWN_TURNS) == (BANTER_COOLDOWN_TURNS - 1):
        companion_id = party[turn_number % len(party)]
        from backend.app.core.companions import get_companion_by_id
        comp = get_companion_by_id(companion_id)
        name = comp.get("name", "Companion") if comp else "Companion"
        style = (comp or {}).get("banter_style", "stoic")

        # Phase 5: Reference companion memories in banter when available
        ws = campaign.get("world_state_json") if isinstance(campaign.get("world_state_json"), dict) else {}
        memories = (ws.get("companion_memories") or {}).get(companion_id) or [] if isinstance(ws, dict) else []
        aff = campaign.get("party_affinity", {}).get(companion_id, 0)
        arc = companion_arc_stage(aff)

        # Determine tone from last mechanic result
        tone_tag = "NEUTRAL"
        if isinstance(mr, dict):
            tone_tag = (mr.get("tone_tag") or "NEUTRAL").strip().upper()

        # Seeded RNG for deterministic but varied banter selection
        from backend.app.world.npc_generator import derive_seed
        banter_seed = derive_seed(campaign.get("id", ""), turn_number, counter=77)
        banter_rng = random.Random(banter_seed)

        if memories and arc in ("TRUSTED", "LOYAL"):
            recent_memory = memories[-1][:60] if memories else ""
            pool = BANTER_MEMORY_POOL.get(style, BANTER_MEMORY_POOL.get("stoic", []))
            if pool:
                template = banter_rng.choice(pool)
                line = template.format(name=name, memory=recent_memory)
            else:
                line = f'"{name} pauses, recalling {recent_memory}."'
        else:
            style_pool = BANTER_POOL.get(style, BANTER_POOL.get("stoic", {}))
            tone_lines = style_pool.get(tone_tag, style_pool.get("NEUTRAL", []))
            if tone_lines:
                template = banter_rng.choice(tone_lines)
                line = template.format(name=name)
            else:
                # Ultimate fallback
                line = f'"{name} watches quietly."'
        banter_queue.append({"speaker": name, "text": line})
        campaign["banter_queue"] = banter_queue
        return {**state, "campaign": campaign}, line
    return state, None


def maybe_enqueue_news_banter(state: dict[str, Any]) -> dict[str, Any]:
    """If a NewsItem touches a faction a companion cares about, optionally enqueue one banter/comment line.
    Only runs when world_sim just added news (world_sim_ran and news_feed has items). At most one per turn."""
    if not state.get("world_sim_ran"):
        return state
    campaign = dict(state.get("campaign") or {})
    news_feed = campaign.get("news_feed") or []
    if not news_feed or not isinstance(news_feed, list):
        return state
    party = campaign.get("party") or []
    if not party:
        return state
    from backend.app.core.companions import get_companion_by_id
    # Latest 1–2 items (newest first)
    for item in news_feed[:2]:
        if not isinstance(item, dict):
            continue
        related = list(item.get("related_factions") or [])
        headline = (item.get("headline") or "").strip()
        for cid in party:
            comp = get_companion_by_id(cid)
            if not comp:
                continue
            faction_interest = comp.get("faction_interest")
            if not isinstance(faction_interest, list):
                continue
            overlap = [f for f in related if f and any(fi for fi in faction_interest if fi and (f.lower() == fi.lower() or fi.lower() in f.lower() or f.lower() in fi.lower()))]
            if not overlap:
                continue
            name = comp.get("name", "Companion")
            style = comp.get("banter_style", "stoic")
            if style == "warm":
                line = f'"{name} leans in. \"We should look into that.\""'
            elif style == "snarky":
                line = f'"{name} snorts. \"There it is. Knew it was only a matter of time.\""'
            else:
                line = f'"{name}: \"That intel changes things.\""'
            banter_queue = list(campaign.get("banter_queue") or [])
            banter_queue.append({"speaker": name, "text": line})
            campaign["banter_queue"] = banter_queue
            return {**state, "campaign": campaign}
    return state


def affinity_to_mood_tag(affinity: int) -> str:
    """Derive mood_tag from affinity for party_status. Hostile <= -50, Wary < 0, Neutral 0..49, Warm >= 50."""
    if affinity >= MOOD_WARM_THRESHOLD:
        return "Warm"
    if affinity <= MOOD_WARY_THRESHOLD:
        return "Hostile"
    if affinity < 0:
        return "Wary"
    return "Neutral"


# ---------------------------------------------------------------------------
# Phase 5: Deep Companion System
# ---------------------------------------------------------------------------


def companion_arc_stage(affinity: int) -> str:
    """Derive relationship arc stage from affinity value.

    STRANGER (affinity <= -10), ALLY (-9..29), TRUSTED (30..69), LOYAL (70+).
    """
    if affinity <= COMPANION_ARC_STRANGER_MAX:
        return "STRANGER"
    if affinity >= COMPANION_ARC_LOYAL_MIN:
        return "LOYAL"
    if affinity >= COMPANION_ARC_TRUSTED_MIN:
        return "TRUSTED"
    return "ALLY"


def detect_companion_conflicts(
    party: list[str],
    old_affinity: dict[str, int],
    new_affinity: dict[str, int],
    deltas: dict[str, int],
) -> list[dict[str, Any]]:
    """Detect sharp drops, threshold crosses, and stage downgrades.

    Returns list of conflict dicts: {companion_id, conflict_type, details}.
    """
    conflicts: list[dict[str, Any]] = []
    for cid in party:
        delta = deltas.get(cid, 0)
        old_aff = old_affinity.get(cid, 0)
        new_aff = new_affinity.get(cid, 0)

        # Sharp drop
        if delta <= COMPANION_CONFLICT_SHARP_DROP:
            conflicts.append({
                "companion_id": cid,
                "conflict_type": "sharp_drop",
                "details": f"Affinity dropped by {delta} (from {old_aff} to {new_aff})",
            })

        # Threshold cross into negative territory
        if old_aff >= 0 > new_aff and new_aff <= COMPANION_CONFLICT_THRESHOLD_CROSS:
            conflicts.append({
                "companion_id": cid,
                "conflict_type": "threshold_cross",
                "details": f"Crossed into hostile territory (from {old_aff} to {new_aff})",
            })

        # Stage downgrade
        old_stage = companion_arc_stage(old_aff)
        new_stage = companion_arc_stage(new_aff)
        stage_order = ["STRANGER", "ALLY", "TRUSTED", "LOYAL"]
        if stage_order.index(new_stage) < stage_order.index(old_stage):
            conflicts.append({
                "companion_id": cid,
                "conflict_type": "stage_downgrade",
                "details": f"Downgraded from {old_stage} to {new_stage}",
            })

    return conflicts


def record_companion_moment(
    world_state: dict,
    companion_id: str,
    moment_text: str,
) -> dict:
    """Append a moment to world_state['companion_memories'][cid], capped at COMPANION_MAX_MEMORIES.

    Returns the (mutated) world_state.
    """
    memories = dict(world_state.get("companion_memories") or {})
    cid_memories = list(memories.get(companion_id) or [])
    cid_memories.append(moment_text[:200])
    if len(cid_memories) > COMPANION_MAX_MEMORIES:
        cid_memories = cid_memories[-COMPANION_MAX_MEMORIES:]
    memories[companion_id] = cid_memories
    world_state["companion_memories"] = memories
    return world_state


def format_companion_reactions_for_narrator(
    state: dict[str, Any],
    affinity_deltas: dict[str, int],
    reasons: dict[str, str],
) -> str:
    """Format companion reactions as a narrator-injectable context block.

    Returns a short block like:
        - Kessa (Warm, affinity +3): approved your paragon choice. [Quirk: She lists names under her breath before hard choices.]
        - Vekk (Hostile, affinity -2): disapproved your choice. [Quirk: Uses Imperial jargon out of habit.]
    """
    campaign = state.get("campaign") or {}
    party_affinity = campaign.get("party_affinity") or {}

    from backend.app.core.companions import get_companion_by_id
    lines: list[str] = []
    for cid, delta in affinity_deltas.items():
        if delta == 0:
            continue
        comp = get_companion_by_id(cid)
        name = comp.get("name", cid) if comp else cid
        aff = party_affinity.get(cid, 0)
        mood = affinity_to_mood_tag(aff)
        reason = reasons.get(cid, "")
        direction = "approved" if delta > 0 else "disapproved"
        sign = "+" if delta > 0 else ""
        quirk = (comp.get("speech_quirk") or "") if comp else ""
        line = f"- {name} ({mood}, affinity {sign}{delta}): {direction} ({reason})"
        if quirk:
            line += f" [Quirk: {quirk}]"
        lines.append(line)
    return "\n".join(lines) if lines else ""


def extract_companion_moments(
    companion_id: str,
    delta: int,
    reason: str,
    mechanic_result: dict[str, Any] | None,
    turn_number: int,
) -> str | None:
    """Generate a moment string for significant deltas (abs >= 2). Returns None if not significant."""
    if abs(delta) < 2:
        return None
    direction = "approved" if delta > 0 else "disapproved"
    reason_short = (reason or "unknown")[:40]
    return f"Turn {turn_number}: {companion_id} {direction} ({reason_short})"


def compute_inter_party_tensions(
    party: list[str],
    party_traits: dict[str, dict[str, int]],
    affinity_deltas: dict[str, int],
) -> list[dict[str, Any]]:
    """Detect inter-companion tensions from opposing trait reactions.

    When one companion approves (delta >= 2) and another disapproves (delta <= -2)
    on the same turn, flag a tension between them.

    Returns list of tension dicts: {companion_a, companion_b, description}.
    """
    from backend.app.core.companions import get_companion_by_id

    approvers: list[tuple[str, int]] = []
    disapprovers: list[tuple[str, int]] = []
    for cid, delta in affinity_deltas.items():
        if delta >= 2:
            approvers.append((cid, delta))
        elif delta <= -2:
            disapprovers.append((cid, delta))

    tensions: list[dict[str, Any]] = []
    for a_id, a_delta in approvers:
        for d_id, d_delta in disapprovers:
            if a_id == d_id:
                continue
            a_comp = get_companion_by_id(a_id)
            d_comp = get_companion_by_id(d_id)
            a_name = a_comp.get("name", a_id) if a_comp else a_id
            d_name = d_comp.get("name", d_id) if d_comp else d_id
            tensions.append({
                "companion_a": a_id,
                "companion_b": d_id,
                "description": f"{a_name} and {d_name} are at odds over your last decision.",
                "a_name": a_name,
                "b_name": d_name,
            })
    return tensions


def format_inter_party_tensions_for_narrator(tensions: list[dict[str, Any]]) -> str:
    """Format inter-party tensions as a narrator-injectable context block."""
    if not tensions:
        return ""
    lines = []
    for t in tensions[:2]:  # cap at 2 tension lines
        lines.append(f"- {t['a_name']} and {t['b_name']} exchange a tense glance — they disagree about what just happened.")
    return "\n".join(lines)


def format_inter_party_tensions_for_director(tensions: list[dict[str, Any]]) -> str:
    """Format inter-party tensions as Director context."""
    if not tensions:
        return ""
    lines = []
    for t in tensions[:2]:
        lines.append(
            f"- {t['a_name']} and {t['b_name']} are at odds. "
            f"Consider offering a suggestion that addresses their disagreement."
        )
    return "\n".join(lines)


def check_companion_triggers(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Check for companion-initiated events based on affinity milestones.

    Returns pending companion events:
      - COMPANION_REQUEST: TRUSTED companion wants to speak (20% per turn)
      - COMPANION_QUEST: LOYAL companion reveals personal quest hook
      - COMPANION_CONFRONTATION: sharp conflict detected, companion confronts player

    Events are seeded by turn_number for determinism.
    """
    from backend.app.world.npc_generator import derive_seed
    campaign = state.get("campaign") or {}
    party = campaign.get("party") or []
    party_affinity = campaign.get("party_affinity") or {}
    turn_number = int(state.get("turn_number") or 0)
    campaign_id = state.get("campaign_id", "")

    # Track which triggers have already fired to avoid repeats
    ws = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
    ws = ws if isinstance(ws, dict) else {}
    fired_triggers = set(ws.get("companion_triggers_fired") or [])

    events: list[dict[str, Any]] = []
    for cid in party:
        aff = int(party_affinity.get(cid, 0))
        arc = companion_arc_stage(aff)
        trigger_seed = derive_seed(campaign_id, turn_number, counter=hash(cid) % 1000)
        trigger_rng = random.Random(trigger_seed)

        # TRUSTED companions: 20% chance per turn to request conversation
        if arc == "TRUSTED" and f"{cid}_request" not in fired_triggers:
            if trigger_rng.random() < 0.20:
                events.append({
                    "event_type": "COMPANION_REQUEST",
                    "companion_id": cid,
                    "description": f"{cid} wants to speak with you privately.",
                })
                fired_triggers.add(f"{cid}_request")

        # LOYAL companions: reveal personal quest (one-time)
        if arc == "LOYAL" and f"{cid}_quest" not in fired_triggers:
            events.append({
                "event_type": "COMPANION_QUEST",
                "companion_id": cid,
                "description": f"{cid} has something important to share — a personal matter.",
            })
            fired_triggers.add(f"{cid}_quest")

    # Check for confrontation events from recent conflicts
    companion_conflicts = campaign.get("companion_conflicts") or []
    for conflict in companion_conflicts:
        cid = conflict.get("companion_id", "")
        ctype = conflict.get("conflict_type", "")
        if ctype == "sharp_drop" and f"{cid}_confrontation_{turn_number}" not in fired_triggers:
            events.append({
                "event_type": "COMPANION_CONFRONTATION",
                "companion_id": cid,
                "description": f"{cid} confronts you about your recent choices.",
            })
            fired_triggers.add(f"{cid}_confrontation_{turn_number}")

    # Persist fired triggers back into state
    if events:
        ws = dict(campaign.get("world_state_json") or {})
        ws["companion_triggers_fired"] = list(fired_triggers)
        campaign = dict(campaign)
        campaign["world_state_json"] = ws
        state = {**state, "campaign": campaign}

    return events
