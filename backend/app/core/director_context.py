"""Director context builders: style queries, era/faction context, lore hooks."""
from __future__ import annotations

import re

from backend.app.models.state import (
    GameState,
    ACTION_CATEGORY_SOCIAL,
    ACTION_CATEGORY_EXPLORE,
    ACTION_CATEGORY_COMMIT,
    TONE_TAG_NEUTRAL,
    TONE_TAG_BY_CATEGORY,
)

# Style chunk dict: text, source_title, tags (list), score
StyleChunk = dict

# Lore chunk dict: text, source_title, chunk_id, metadata, score
LoreChunk = dict

VALID_TONE_TAGS = frozenset({"PARAGON", "RENEGADE", "INVESTIGATE", "NEUTRAL"})


def build_style_query(state: GameState) -> str:
    """Build a style query from location, user_input, intent, and mechanic action_type."""
    parts = []
    loc = state.current_location
    if loc:
        parts.append(f"location: {loc}")
    user = (state.user_input or "").strip()
    if user:
        parts.append(f"user: {user}")
    intent = state.intent
    if intent:
        parts.append(f"intent: {intent}")
    if state.mechanic_result:
        parts.append(f"action_type: {state.mechanic_result.action_type}")
    return " ".join(parts) if parts else "pacing tone style"


def build_era_factions_companions_context(state: GameState) -> tuple[str, set[str]]:
    """Build era, factions, companions context and set of allowed entity names."""
    campaign = getattr(state, "campaign", None) or {}
    era = str(campaign.get("time_period") or campaign.get("era") or "REBELLION").strip() or "REBELLION"

    ws = campaign.get("world_state_json") or {}
    active_factions = ws.get("active_factions") or campaign.get("active_factions") or []
    faction_names = []
    if isinstance(active_factions, list):
        for f in active_factions[:3]:
            if isinstance(f, dict) and f.get("name"):
                faction_names.append(str(f["name"]).strip())
            elif isinstance(f, str):
                faction_names.append(str(f).strip())

    party = campaign.get("party") or []
    party_affinity = campaign.get("party_affinity") or {}
    party_traits = campaign.get("party_traits") or {}
    companion_lines = []
    for cid in party[:5]:
        aff = int(party_affinity.get(cid, 0))
        mood = "Warm" if aff >= 50 else "Hostile" if aff <= -50 else "Wary" if aff < 0 else "Neutral"
        traits = (party_traits.get(cid) or {})
        traits.get("archetype", "") or traits.get("name", cid)
        companion_lines.append(f"  - {cid}: {mood} (affinity {aff})")
    companions_block = "\n".join(companion_lines) if companion_lines else "  (none)"

    allowed: set[str] = set()
    for n in faction_names:
        allowed.add(n.lower())
    npcs = getattr(state, "present_npcs", None) or []
    for n in npcs:
        name = n.get("name") if isinstance(n, dict) else None
        if name:
            allowed.add(str(name).lower())
    for cid in party:
        allowed.add(str(cid).lower())

    # Include player POV identity + current location/planet so the Director can safely reference them.
    player = getattr(state, "player", None)
    if player and getattr(player, "name", None):
        allowed.add(str(player.name).strip().lower())
    loc = getattr(state, "current_location", None)
    if loc:
        allowed.add(str(loc).strip().lower())
    planet = getattr(state, "current_planet", None)
    if planet:
        allowed.add(str(planet).strip().lower())

    lines = [f"Campaign era: {era}"]
    if faction_names:
        lines.append(f"Active factions (use only these): {', '.join(faction_names)}")
    lines.append("Companions present:")
    lines.append(companions_block)
    return "\n".join(lines), allowed


def adventure_hooks_from_lore(chunks: list[LoreChunk], max_chars: int = 800) -> str:
    """Build adventure/hook context from lore chunks (Director bundle)."""
    if not chunks:
        return ""
    lines = []
    total = 0
    for c in chunks:
        text = (c.get("text") or "").strip()
        if not text:
            continue
        if total + len(text) + 1 > max_chars:
            remainder = max_chars - total - 4
            if remainder > 20:
                lines.append(text[:remainder].rstrip() + "...")
            break
        lines.append(text)
        total += len(text) + 1
    return "\n".join(lines) if lines else ""


def style_context_from_chunks(chunks: list[StyleChunk], max_chars: int = 1200) -> str:
    """Build a short style_context string from retrieved chunks (<= max_chars)."""
    if not chunks:
        return ""
    lines = []
    total = 0
    for c in chunks:
        text = (c.get("text") or "").strip()
        if not text:
            continue
        if total + len(text) + 1 > max_chars:
            remainder = max_chars - total - 4
            if remainder > 20:
                lines.append(text[:remainder].rstrip() + "...")
            break
        lines.append(text)
        total += len(text) + 1
    return "\n".join(lines)


def directives_from_style_context(style_context: str, min_count: int = 2) -> list[str]:
    """Extract at least min_count concrete directive sentences from style_context."""
    if not style_context or min_count <= 0:
        return []
    segments = re.split(r"[.\n]+", style_context)
    directives = [s.strip() for s in segments if len(s.strip()) > 10]
    if not directives:
        lines = [ln.strip() for ln in style_context.split("\n") if ln.strip()]
        directives = lines
    if len(directives) >= min_count:
        return directives[: min_count + 2]
    fallbacks = ["Keep the tone consistent.", "End with a clear choice for the player."]
    while len(directives) < min_count:
        directives.append(fallbacks[len(directives) % len(fallbacks)])
    return directives


def _tokenize_for_similarity(text: str) -> set[str]:
    """Lowercase word tokens for Jaccard similarity."""
    if not text:
        return set()
    return set(re.findall(r"\w+", (text or "").lower()))


def _jaccard_similarity(a: str, b: str) -> float:
    """Token Jaccard similarity between two strings (0 = disjoint, 1 = identical)."""
    ta, tb = _tokenize_for_similarity(a), _tokenize_for_similarity(b)
    if not ta and not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def sanitize_instructions_for_narrator(instructions: str) -> str:
    """Strip Director-internal suggestion guidance before passing to the Narrator.

    The Narrator should only receive scene/pacing guidance, not action-generation
    instructions like 'Suggested actions should be INTRODUCTORY'.
    """
    if not instructions:
        return instructions
    result = instructions
    # Strip sentences about suggested actions (Director-internal guidance)
    result = re.sub(
        r"[^\n]*[Ss]uggested\s+actions?\s+(?:should|must|are|can)[^\n]*\n?",
        "",
        result,
    )
    # Strip "Suggested Actions:" sections with content (LLM-generated)
    result = re.sub(
        r"\*{0,2}Suggested\s+[Aa]ctions?:?\*{0,2}\s*\n(?:(?!\n\n).)*",
        "",
        result,
        flags=re.DOTALL,
    )
    # Strip "Scene Description:" labels (keep the content after the label)
    result = re.sub(
        r"Scene\s+Description:\s*",
        "",
        result,
        flags=re.IGNORECASE,
    )
    # Collapse excess blank lines
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def normalize_tone(item: dict) -> None:
    """Inject default tone_tag from category if missing or invalid."""
    cat = item.get("category") or ACTION_CATEGORY_EXPLORE
    tone = item.get("tone_tag") or ""
    if tone not in VALID_TONE_TAGS:
        item["tone_tag"] = TONE_TAG_BY_CATEGORY.get(cat, TONE_TAG_NEUTRAL)
    if not item.get("intent_style"):
        item["intent_style"] = "neutral"
    if not item.get("consequence_hint"):
        default_hints = {
            ACTION_CATEGORY_SOCIAL: "may gain trust",
            ACTION_CATEGORY_EXPLORE: "learn more",
            ACTION_CATEGORY_COMMIT: "may escalate",
        }
        item["consequence_hint"] = default_hints.get(cat, "")


def validate_suggestions(actions: list | list[dict]) -> tuple[bool, str]:
    """
    Validate: sane count, includes core categories, no near-duplicate intent_text,
    and at least one ALTERNATIVE. Returns (valid, reason).
    """
    from backend.app.constants import (
        INTENT_JACCARD_THRESHOLD,
        SUGGESTED_ACTIONS_MAX,
        SUGGESTED_ACTIONS_MIN,
    )
    from backend.app.models.state import (
        STRATEGY_TAG_ALTERNATIVE,
        STRATEGY_TAG_OPTIMAL,
    )

    if len(actions) < SUGGESTED_ACTIONS_MIN:
        return False, f"expected at least {SUGGESTED_ACTIONS_MIN} actions, got {len(actions)}"
    if len(actions) > SUGGESTED_ACTIONS_MAX:
        return False, f"expected at most {SUGGESTED_ACTIONS_MAX} actions, got {len(actions)}"
    items = [
        a if isinstance(a, dict) else (a.model_dump(mode="json") if hasattr(a, "model_dump") else dict(a))
        for a in actions
    ]
    for it in items:
        normalize_tone(it)
    categories = [it.get("category") or ACTION_CATEGORY_EXPLORE for it in items]
    required = {ACTION_CATEGORY_SOCIAL, ACTION_CATEGORY_EXPLORE, ACTION_CATEGORY_COMMIT}
    if not required.issubset(set(categories)):
        return False, f"must include categories {sorted(required)}; got {sorted(set(categories))}"
    intent_texts = [it.get("intent_text") or "" for it in items]
    for i in range(len(intent_texts)):
        for j in range(i + 1, len(intent_texts)):
            sim = _jaccard_similarity(intent_texts[i], intent_texts[j])
            if sim >= INTENT_JACCARD_THRESHOLD:
                return False, f"near-duplicate intents (Jaccard {sim:.2f}): '{intent_texts[i][:40]}' vs '{intent_texts[j][:40]}'"
    strategy_tags = [it.get("strategy_tag") or STRATEGY_TAG_OPTIMAL for it in items]
    if STRATEGY_TAG_ALTERNATIVE not in strategy_tags:
        return False, "at least one action must be strategy_tag ALTERNATIVE (not obviously optimal)"
    return True, ""
