"""Director validation, fallbacks, and context builders."""
from __future__ import annotations

import re

from backend.app.constants import (
    DIRECTOR_ENTITY_STOP_WORDS,
    INTENT_JACCARD_THRESHOLD,
    SUGGESTED_ACTIONS_MAX,
    SUGGESTED_ACTIONS_MIN,
    SUGGESTED_ACTIONS_TARGET,
)
from backend.app.models.state import (
    ActionSuggestion,
    GameState,
    ACTION_CATEGORY_SOCIAL,
    ACTION_CATEGORY_EXPLORE,
    ACTION_CATEGORY_COMMIT,
    ACTION_RISK_SAFE,
    ACTION_RISK_RISKY,
    ACTION_RISK_DANGEROUS,
    STRATEGY_TAG_OPTIMAL,
    STRATEGY_TAG_ALTERNATIVE,
    TONE_TAG_PARAGON,
    TONE_TAG_RENEGADE,
    TONE_TAG_INVESTIGATE,
    TONE_TAG_NEUTRAL,
    TONE_TAG_BY_CATEGORY,
)


# Style chunk dict: text, source_title, tags (list), score
StyleChunk = dict

# Lore chunk dict: text, source_title, chunk_id, metadata, score
LoreChunk = dict

VALID_TONE_TAGS = frozenset({TONE_TAG_PARAGON, TONE_TAG_RENEGADE, TONE_TAG_INVESTIGATE, TONE_TAG_NEUTRAL})


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
        archetype = traits.get("archetype", "") or traits.get("name", cid)
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


def check_entities(actions: list[dict], allowed_entities: set[str]) -> tuple[bool, str]:
    """Disabled (V3.0): too many false positives in Star Wars context.

    Previously rejected suggestions referencing proper nouns not in allowed_entities.
    In a Star Wars game, every proper noun sounds hallucinated — this guard produced
    constant false positives. Kept as no-op for API compatibility.
    """
    return True, ""


def fix_social_npc_targets(actions: list[dict], present_npcs: list[dict]) -> None:
    """Disabled (V3.0): too aggressive for Star Wars context.

    Previously replaced NPC names in SOCIAL actions when not in present_npcs.
    This overwrote legitimate LLM-generated dialogue options with generic fallbacks.
    Kept as no-op for API compatibility.
    """
    return


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


def validate_suggestions(actions: list[ActionSuggestion] | list[dict]) -> tuple[bool, str]:
    """
    Validate: sane count, includes core categories, no near-duplicate intent_text,
    and at least one ALTERNATIVE. Returns (valid, reason).
    """
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


def _humanize_location_for_suggestion(loc_id: str) -> str:
    """Convert a raw location ID into a readable name for suggestions.

    Handles both loc- prefixed IDs and plain names (planets, proper nouns).
    """
    if not loc_id or loc_id == "\u2014":
        return "the area"
    raw = loc_id.strip()
    _display_names = {
        "loc-cantina": "the cantina",
        "loc-tavern": "the cantina",
        "loc-marketplace": "the marketplace",
        "loc-market": "the marketplace",
        "loc-docking-bay": "the docking bay",
        "loc-docks": "the docking bay",
        "loc-lower-streets": "the lower streets",
        "loc-street": "the lower streets",
        "loc-hangar": "the hangar bay",
        "loc-spaceport": "the spaceport",
        "loc-command-center": "the command center",
        "loc-med-bay": "the med bay",
        "loc-jedi-temple": "the Jedi Temple",
    }
    display = _display_names.get(raw.lower())
    if display:
        return display
    # Check if it has a loc- prefix (generic location) vs a proper name
    has_prefix = False
    cleaned = raw
    for prefix in ("loc-", "loc_", "location-", "location_"):
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix):]
            has_prefix = True
            break
    cleaned = cleaned.replace("-", " ").replace("_", " ").strip()
    if not cleaned:
        return "the area"
    # If no prefix was stripped and the name starts with a capital letter,
    # it's likely a proper noun (planet name, city name) — no article needed
    if not has_prefix and cleaned[0].isupper():
        return cleaned
    # For generic location words, add "the"
    return f"the {cleaned}"


# ── Narrator-first suggestion classification (V2.12) ──────────────────

# Keyword sets for deterministic tone classification
_PARAGON_VERBS = frozenset({
    "help", "offer", "introduce", "comfort", "share", "heal", "protect",
    "reassure", "encourage", "support", "befriend", "trust", "apologize",
    "calm", "thank", "welcome", "show", "give",
})
_INVESTIGATE_VERBS = frozenset({
    "ask", "question", "search", "scan", "observe", "examine", "check",
    "listen", "watch", "investigate", "study", "inspect", "analyze",
    "survey", "wait", "eavesdrop", "look", "peer", "scout", "explore",
})
_RENEGADE_VERBS = frozenset({
    "demand", "threaten", "confront", "intimidate", "steal", "force",
    "challenge", "provoke", "deceive", "bluff", "bribe", "blackmail",
    "pressure", "insult", "mock", "taunt", "grab", "shove",
})
_RISKY_VERBS = frozenset({
    "confront", "demand", "sneak", "bluff", "deceive", "threaten",
    "pickpocket", "hack", "bribe", "pick", "break", "sabotage",
    "provoke", "challenge", "pressure", "intimidate",
})
_DANGEROUS_VERBS = frozenset({
    "attack", "steal", "betray", "sabotage", "ambush", "assassinate",
    "destroy", "fight", "kill", "shoot",
})
_SOCIAL_VERBS = frozenset({
    "talk", "say", "ask", "tell", "greet", "introduce", "negotiate",
    "persuade", "convince", "approach", "speak", "chat", "flatter",
    "compliment", "question", "offer", "comfort", "reassure",
    "demand", "threaten", "confront", "intimidate", "bluff", "bribe",
    "show", "thank",
})
_COMMIT_VERBS = frozenset({
    "fight", "attack", "steal", "leave", "escape", "flee", "commit",
    "sabotage", "destroy", "break", "shoot", "ambush", "betray",
    "kill",
})

_CONSEQUENCE_HINTS = {
    (ACTION_CATEGORY_SOCIAL, ACTION_RISK_SAFE): "may gain trust or new information",
    (ACTION_CATEGORY_SOCIAL, ACTION_RISK_RISKY): "may escalate the situation",
    (ACTION_CATEGORY_SOCIAL, ACTION_RISK_DANGEROUS): "may provoke a hostile response",
    (ACTION_CATEGORY_EXPLORE, ACTION_RISK_SAFE): "learn more about the area",
    (ACTION_CATEGORY_EXPLORE, ACTION_RISK_RISKY): "may reveal hidden dangers",
    (ACTION_CATEGORY_EXPLORE, ACTION_RISK_DANGEROUS): "high risk of discovery",
    (ACTION_CATEGORY_COMMIT, ACTION_RISK_SAFE): "spot something others missed",
    (ACTION_CATEGORY_COMMIT, ACTION_RISK_RISKY): "may trigger a new encounter",
    (ACTION_CATEGORY_COMMIT, ACTION_RISK_DANGEROUS): "point of no return",
}

_INTENT_STYLES = {
    TONE_TAG_PARAGON: "empathetic",
    TONE_TAG_INVESTIGATE: "probing",
    TONE_TAG_RENEGADE: "firm",
    TONE_TAG_NEUTRAL: "neutral",
}


def classify_suggestion(
    raw_text: str,
    *,
    index: int = 0,
    meaning_tag: str = "",
) -> ActionSuggestion:
    """Classify raw suggestion text into a full ActionSuggestion with tone/risk/category.

    Uses deterministic keyword analysis rather than LLM output. The raw_text
    is expected to be a verb-first action description from the Narrator.

    V2.18: Accepts optional meaning_tag from LLM. If not provided, infers
    deterministically via infer_meaning_tag().
    """
    from backend.app.models.dialogue_turn import infer_meaning_tag

    text = raw_text.strip()
    if not text:
        text = "Wait and observe"

    # V2.13: Detect dialogue-quote suggestions (character speech as option)
    # e.g., '"I\'ll take the job"' or '"No deal. Find someone else."'
    is_dialogue = text.startswith('"') or text.startswith("'") or text.startswith("\u201c")
    intent_text = text
    if is_dialogue:
        # Wrap as Say: for the router (TALK intent)
        clean_quote = text.strip("\"'\u201c\u201d").strip()
        intent_text = f"Say: '{clean_quote}'"

    # Extract the leading verb (first word, lowercased)
    # For dialogue quotes, analyze the content inside the quotes
    analysis_text = text.strip("\"'\u201c\u201d").strip() if is_dialogue else text
    words = re.findall(r"[a-zA-Z]+", analysis_text.lower())
    lead_verb = words[0] if words else ""
    all_words_set = set(words)

    # ── Tone classification ──
    if lead_verb in _PARAGON_VERBS or all_words_set & _PARAGON_VERBS:
        tone = TONE_TAG_PARAGON
    elif lead_verb in _RENEGADE_VERBS or all_words_set & _RENEGADE_VERBS:
        tone = TONE_TAG_RENEGADE
    elif lead_verb in _INVESTIGATE_VERBS or all_words_set & _INVESTIGATE_VERBS:
        tone = TONE_TAG_INVESTIGATE
    else:
        tone = TONE_TAG_NEUTRAL

    # Prioritize lead verb for tone (it's the primary action)
    if lead_verb in _PARAGON_VERBS:
        tone = TONE_TAG_PARAGON
    elif lead_verb in _RENEGADE_VERBS:
        tone = TONE_TAG_RENEGADE
    elif lead_verb in _INVESTIGATE_VERBS:
        tone = TONE_TAG_INVESTIGATE

    # ── Risk classification ──
    if lead_verb in _DANGEROUS_VERBS or all_words_set & _DANGEROUS_VERBS:
        risk = ACTION_RISK_DANGEROUS
    elif lead_verb in _RISKY_VERBS or all_words_set & _RISKY_VERBS:
        risk = ACTION_RISK_RISKY
    else:
        risk = ACTION_RISK_SAFE

    # ── Category classification ──
    if is_dialogue:
        category = ACTION_CATEGORY_SOCIAL
    elif lead_verb in _SOCIAL_VERBS:
        category = ACTION_CATEGORY_SOCIAL
    elif lead_verb in _COMMIT_VERBS:
        category = ACTION_CATEGORY_COMMIT
    else:
        category = ACTION_CATEGORY_EXPLORE

    # ── Strategy tag ── First suggestion is OPTIMAL, last is ALTERNATIVE
    strategy = STRATEGY_TAG_OPTIMAL

    # ── Consequence hint ──
    hint = _CONSEQUENCE_HINTS.get((category, risk), "")

    # ── Intent style ──
    style = _INTENT_STYLES.get(tone, "neutral")

    # ── V2.18: Meaning tag ──
    resolved_meaning = meaning_tag or infer_meaning_tag(text)

    return ActionSuggestion(
        label=text,
        intent_text=intent_text,
        category=category,
        risk_level=risk,
        strategy_tag=strategy,
        tone_tag=tone,
        intent_style=style,
        consequence_hint=hint,
        meaning_tag=resolved_meaning,
    )


def ensure_tone_diversity(suggestions: list[ActionSuggestion]) -> list[ActionSuggestion]:
    """Guarantee KOTOR tone spread: at least one each of PARAGON, INVESTIGATE, RENEGADE if possible.

    Also ensures at least one ALTERNATIVE strategy tag. Mutates and returns the list.
    """
    if len(suggestions) < 3:
        return suggestions

    present_tones = {s.tone_tag for s in suggestions}
    needed = []
    if TONE_TAG_PARAGON not in present_tones:
        needed.append(TONE_TAG_PARAGON)
    if TONE_TAG_INVESTIGATE not in present_tones:
        needed.append(TONE_TAG_INVESTIGATE)
    if TONE_TAG_RENEGADE not in present_tones:
        needed.append(TONE_TAG_RENEGADE)

    # Re-tag NEUTRAL suggestions to fill gaps
    neutral_indices = [i for i, s in enumerate(suggestions) if s.tone_tag == TONE_TAG_NEUTRAL]
    for tone_needed in needed:
        if not neutral_indices:
            break
        idx = neutral_indices.pop(0)
        suggestions[idx].tone_tag = tone_needed
        suggestions[idx].intent_style = _INTENT_STYLES.get(tone_needed, "neutral")
        # Update category to match tone convention
        category_for_tone = {
            TONE_TAG_PARAGON: ACTION_CATEGORY_SOCIAL,
            TONE_TAG_INVESTIGATE: ACTION_CATEGORY_EXPLORE,
            TONE_TAG_RENEGADE: ACTION_CATEGORY_COMMIT,
        }
        if tone_needed in category_for_tone:
            suggestions[idx].category = category_for_tone[tone_needed]

    # Ensure at least one ALTERNATIVE strategy tag (last suggestion is a good candidate)
    has_alt = any(s.strategy_tag == STRATEGY_TAG_ALTERNATIVE for s in suggestions)
    if not has_alt and suggestions:
        suggestions[-1].strategy_tag = STRATEGY_TAG_ALTERNATIVE

    return suggestions


def _detect_tone_streak(history: list[str], last_inputs: list[str]) -> str | None:
    """Detect if the player has chosen the same tone 3+ times in a row.

    Analyzes last_user_inputs for tone patterns. Returns the tone tag if
    a streak of 3+ is detected, else None. Purely deterministic.
    """
    if len(last_inputs) < 3:
        return None
    recent = last_inputs[-3:]
    tones = []
    for inp in recent:
        inp_lower = (inp or "").lower()
        words = set(re.findall(r"[a-z]+", inp_lower))
        if words & _PARAGON_VERBS:
            tones.append(TONE_TAG_PARAGON)
        elif words & _RENEGADE_VERBS:
            tones.append(TONE_TAG_RENEGADE)
        elif words & _INVESTIGATE_VERBS:
            tones.append(TONE_TAG_INVESTIGATE)
        else:
            tones.append(TONE_TAG_NEUTRAL)
    if len(set(tones)) == 1:
        return tones[0]
    return None


def _has_visited_location(history: list[str], location: str) -> bool:
    """Check if the player has visited this location before based on history."""
    if not location or not history:
        return False
    loc_lower = location.lower().replace("-", " ").replace("_", " ")
    # Check history for location mentions
    for entry in history[:-1]:  # Exclude current turn
        if loc_lower in (entry or "").lower():
            return True
    return False


def _get_companion_context(
    world_state: dict,
    party_ids: list[str],
) -> tuple[str | None, str | None, int]:
    """Extract best companion for suggestion generation.

    Returns (companion_name, companion_archetype, influence_score).
    Picks the companion with highest influence who is in the active party.
    """
    party_state_data = world_state.get("party_state") if isinstance(world_state, dict) else None
    if not party_state_data or not isinstance(party_state_data, dict):
        return None, None, 0
    companion_states = party_state_data.get("companion_states") or {}
    if not companion_states:
        return None, None, 0

    best_name = None
    best_archetype = None
    best_influence = -101

    for cid in party_ids:
        cstate = companion_states.get(cid) or {}
        influence = int(cstate.get("influence", 0) or 0)
        if influence > best_influence:
            best_influence = influence
            # Get companion definition for name/archetype
            from backend.app.core.companions import get_companion_by_id
            comp_data = get_companion_by_id(cid)
            if comp_data:
                best_name = comp_data.get("name", cid)
                best_archetype = comp_data.get("archetype", "")
            else:
                best_name = cid
                best_archetype = ""

    if best_influence < -50:
        return None, None, 0  # Don't suggest hostile companions
    return best_name, best_archetype, best_influence


def _get_location_affordances(
    era: str,
    location_id: str,
) -> tuple[list[str], list[dict], list[dict]]:
    """Get location services, access_points, and travel_links from era pack.

    Returns (services, access_points, travel_links) — all as lists.
    """
    try:
        from backend.app.world.era_pack_loader import get_era_pack
        pack = get_era_pack(era)
        if not pack:
            return [], [], []
        loc = pack.location_by_id(location_id or "")
        if not loc:
            return [], [], []
        services = list(loc.services or [])
        access_points = [ap.model_dump(mode="json") for ap in (loc.access_points or [])]
        travel_links = [tl.model_dump(mode="json") for tl in (loc.travel_links or [])]
        return services, access_points, travel_links
    except Exception:
        return [], [], []


def generate_suggestions(
    state: GameState,
    mechanic_result: dict | None = None,
) -> list[ActionSuggestion]:
    """Generate KOTOR-style CYOA suggestions deterministically from game state.

    V2.15: Primary suggestion path (replaces Narrator-embedded suggestions).
    V3.0: Enhanced with memory-aware, companion-aware, and location-specific
    suggestion generation for deeper KOTOR-soul integration.

    Uses scene context (location, NPCs, mechanic result, player background,
    faction memory, stress level, episodic memory, companion state, and
    location affordances) to produce 4 contextual action choices.
    """
    loc = state.current_location or "here"
    loc_readable = _humanize_location_for_suggestion(loc)
    npcs = state.present_npcs or []
    npc_names = [n.get("name") for n in npcs if n.get("name")]
    npc_roles = [n.get("role", "stranger") for n in npcs if n.get("name")]

    known_npcs = set(getattr(state, "known_npcs", None) or [])

    def _npc_label(name: str, role: str) -> str:
        """Return NPC name if known, else descriptive role."""
        if name in known_npcs:
            return name
        return f"the {role.lower()}" if role else "the nearby figure"

    # Pick a primary NPC for suggestions
    if npc_names:
        first_name = npc_names[0]
        first_role = npc_roles[0] if npc_roles else "stranger"
        first_npc = _npc_label(first_name, first_role)
    else:
        first_npc = "someone nearby"

    # Extract context
    campaign = getattr(state, "campaign", None) or {}
    world_state = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
    if isinstance(world_state, str):
        import json as _json
        try:
            world_state = _json.loads(world_state)
        except (ValueError, TypeError):
            world_state = {}

    player_background = ""
    if state.player:
        player_background = getattr(state.player, "background", None) or ""

    faction_context = ""
    faction_memory = world_state.get("faction_memory") if isinstance(world_state, dict) else None
    if faction_memory and isinstance(faction_memory, dict):
        for faction_id, memory in list(faction_memory.items())[:1]:
            plan = memory.get("current_plan") if isinstance(memory, dict) else None
            if plan:
                faction_context = plan
                break

    # Determine stress level for high-stress option
    psych = {}
    if state.player and getattr(state.player, "psych_profile", None):
        psych = state.player.psych_profile or {}
    stress_level = int(psych.get("stress_level", 0) or 0)

    # V3.0: Extract memory context for suggestion enrichment
    last_inputs = getattr(state, "last_user_inputs", None) or []
    history = getattr(state, "history", None) or []
    tone_streak = _detect_tone_streak(history, last_inputs)
    is_return_visit = _has_visited_location(history, loc)

    # V3.0: Extract companion context
    era = str((campaign.get("time_period") or campaign.get("era") or "REBELLION")).strip().upper() or "REBELLION"
    party_ids = (campaign.get("party") or []) if isinstance(campaign, dict) else []
    comp_name, comp_archetype, comp_influence = _get_companion_context(world_state, party_ids)

    # V3.0: Extract location affordances from era pack
    services, access_points, travel_links = _get_location_affordances(era, loc)

    # ── Situation-aware branches based on mechanic result ──
    mr = mechanic_result or {}
    action_type = (mr.get("action_type") or "").upper()
    # MechanicOutput has `success: bool | None` and `outcome_summary: str`
    mr_success = mr.get("success")
    if mr_success is None:
        # Fallback: infer from outcome_summary text
        outcome_text = (mr.get("outcome_summary") or "").lower()
        if any(kw in outcome_text for kw in ("fail", "lost", "barely escaped", "barely survived")):
            mr_success = False
        elif any(kw in outcome_text for kw in ("success", "victory", "won", "defeated")):
            mr_success = True
    events = mr.get("events") or []
    has_damage = any(
        (e.get("event_type") if isinstance(e, dict) else getattr(e, "event_type", "")) == "DAMAGE"
        for e in events
    )

    # POST-COMBAT: player just won or lost a fight
    if action_type in ("ATTACK", "COMBAT") or has_damage:
        if mr_success is False:
            return _post_combat_failure_suggestions(first_npc, loc_readable)
        return _post_combat_success_suggestions(first_npc, loc_readable)

    # POST-STEALTH: player just sneaked
    if action_type in ("STEALTH", "SNEAK"):
        if mr_success is False:
            return _post_stealth_failure_suggestions(first_npc, loc_readable)
        return _post_stealth_success_suggestions(first_npc, loc_readable)

    # NO NPCs PRESENT: exploration mode (with location affordance enrichment)
    if not npc_names:
        return _exploration_suggestions(
            loc_readable, stress_level,
            services=services,
            access_points=access_points,
            travel_links=travel_links,
            comp_name=comp_name,
            comp_influence=comp_influence,
            is_return_visit=is_return_visit,
        )

    # ── Default: social scene with NPCs present ──

    # V3.0: Memory-aware — if player is in a tone streak, subtly reference it
    # by adapting the labels to acknowledge or contrast the pattern.
    streak_prefix = ""
    if tone_streak == TONE_TAG_PARAGON:
        streak_prefix = "again, "  # "Show good faith again" — acknowledges pattern
    elif tone_streak == TONE_TAG_RENEGADE:
        streak_prefix = "try a different approach — "

    # PARAGON option — adapt based on player background
    if "Force" in player_background or "Jedi" in player_background:
        paragon_intent = "Say: 'I sense your distress. Let me help — it's what I was trained to do.'"
    elif "smuggler" in player_background.lower() or "criminal" in player_background.lower():
        paragon_intent = "Say: 'Look, I've been where you are. What do you need? I might know someone.'"
    else:
        paragon_intent = "Say: 'I can see you're dealing with something. What do you need? Maybe I can help.'"

    # V3.0: Return visit — adapt paragon to acknowledge familiarity
    if is_return_visit and npc_names:
        paragon_label = f"Reconnect with {first_npc}"
        paragon_intent = f"Say: 'I've been here before. Things are different now — tell me what changed.'"
    else:
        paragon_label = f"Show {first_npc} good faith"

    # INVESTIGATE option — use faction context if available
    if faction_context:
        investigate_label = f"Ask {first_npc} about recent activity"
        investigate_intent = f"Ask: 'I've heard rumors about operations in {loc_readable}. What do you know?'"
    else:
        investigate_label = f"Press {first_npc} for specifics"
        investigate_intent = "Ask: 'Give me names. Who's involved, and what exactly do they want?'"

    # RENEGADE option — adapt based on location
    if "cantina" in loc_readable.lower() or "bar" in loc_readable.lower():
        renegade_intent = "Say: 'Enough games. You're going to tell me what I want to know, or we're stepping outside.'"
    else:
        renegade_intent = "Say: 'Enough games. I want the truth, and I want it now — or we have a problem.'"

    # V3.0: Companion-aware — replace NEUTRAL slot with companion-specific suggestion
    # when a trusted companion (influence > 50) is in the party.
    if comp_name and comp_influence > 50 and npc_names:
        # Pick companion suggestion based on archetype
        archetype_lower = (comp_archetype or "").lower()
        if "negotiator" in archetype_lower or "diplomat" in archetype_lower:
            neutral_suggestion = ActionSuggestion(
                label=f"Let {comp_name} handle the talking",
                intent_text=f"Say: '{comp_name}, you're better at this. Take the lead.'",
                category=ACTION_CATEGORY_SOCIAL,
                risk_level=ACTION_RISK_SAFE,
                strategy_tag=STRATEGY_TAG_OPTIMAL,
                tone_tag=TONE_TAG_NEUTRAL,
                intent_style="tactical",
                consequence_hint=f"{comp_name} may build rapport faster",
            )
        elif "tech" in archetype_lower or "slicer" in archetype_lower or "mechanic" in archetype_lower:
            neutral_suggestion = ActionSuggestion(
                label=f"Ask {comp_name} to scan for intel",
                intent_text=f"Say: '{comp_name}, see what you can pull from nearby systems.'",
                category=ACTION_CATEGORY_EXPLORE,
                risk_level=ACTION_RISK_SAFE,
                strategy_tag=STRATEGY_TAG_OPTIMAL,
                tone_tag=TONE_TAG_NEUTRAL,
                intent_style="tactical",
                consequence_hint=f"{comp_name}'s skills may uncover hidden data",
            )
        elif "warrior" in archetype_lower or "soldier" in archetype_lower or "enforcer" in archetype_lower:
            neutral_suggestion = ActionSuggestion(
                label=f"Have {comp_name} watch your back",
                intent_text=f"Signal {comp_name} to keep watch while you focus on the conversation",
                category=ACTION_CATEGORY_COMMIT,
                risk_level=ACTION_RISK_SAFE,
                strategy_tag=STRATEGY_TAG_OPTIMAL,
                tone_tag=TONE_TAG_NEUTRAL,
                intent_style="tactical",
                consequence_hint="feel safer knowing someone has your back",
            )
        else:
            neutral_suggestion = ActionSuggestion(
                label=f"Ask {comp_name} what they think",
                intent_text=f"Say: '{comp_name}, you know this place. What's your read?'",
                category=ACTION_CATEGORY_SOCIAL,
                risk_level=ACTION_RISK_SAFE,
                strategy_tag=STRATEGY_TAG_OPTIMAL,
                tone_tag=TONE_TAG_NEUTRAL,
                intent_style="tactical",
                consequence_hint=f"{comp_name} may share local knowledge",
            )
    else:
        # V3.0: Location-specific NEUTRAL — use services/access_points when available
        if "bounty_board" in services:
            neutral_suggestion = ActionSuggestion(
                label="Check the bounty board",
                intent_text=f"Walk over to the bounty board in {loc_readable} and see what's posted",
                category=ACTION_CATEGORY_EXPLORE,
                risk_level=ACTION_RISK_SAFE,
                strategy_tag=STRATEGY_TAG_OPTIMAL,
                tone_tag=TONE_TAG_NEUTRAL,
                intent_style="tactical",
                consequence_hint="might find paying work",
            )
        elif "medbay" in services:
            neutral_suggestion = ActionSuggestion(
                label="Visit the medbay",
                intent_text=f"Head to the medical station in {loc_readable}",
                category=ACTION_CATEGORY_EXPLORE,
                risk_level=ACTION_RISK_SAFE,
                strategy_tag=STRATEGY_TAG_OPTIMAL,
                tone_tag=TONE_TAG_NEUTRAL,
                intent_style="tactical",
                consequence_hint="patch up and get information",
            )
        elif any(ap.get("visibility") in ("hidden", "secret") for ap in access_points):
            neutral_suggestion = ActionSuggestion(
                label="Search for hidden passages",
                intent_text=f"Carefully examine {loc_readable} for concealed doors or passages",
                category=ACTION_CATEGORY_EXPLORE,
                risk_level=ACTION_RISK_RISKY,
                strategy_tag=STRATEGY_TAG_ALTERNATIVE,
                tone_tag=TONE_TAG_NEUTRAL,
                intent_style="tactical",
                consequence_hint="may reveal a secret route",
            )
        elif travel_links:
            dest_id = travel_links[0].get("to_location_id", "")
            dest_readable = _humanize_location_for_suggestion(dest_id)
            neutral_suggestion = ActionSuggestion(
                label=f"Head to {dest_readable}",
                intent_text=f"Leave {loc_readable} and travel to {dest_readable}",
                category=ACTION_CATEGORY_COMMIT,
                risk_level=ACTION_RISK_SAFE,
                strategy_tag=STRATEGY_TAG_ALTERNATIVE,
                tone_tag=TONE_TAG_NEUTRAL,
                intent_style="tactical",
                consequence_hint="change scenery and find new leads",
            )
        else:
            # Default NEUTRAL/TACTICAL option — location-specific search
            if "docking" in loc_readable.lower() or "hangar" in loc_readable.lower():
                search_hint = "spot ship vulnerabilities or escape routes"
            elif "cantina" in loc_readable.lower():
                search_hint = "overhear useful conversations"
            else:
                search_hint = "spot something others missed"
            neutral_suggestion = ActionSuggestion(
                label=f"Search {loc_readable} for an advantage",
                intent_text=f"I scan {loc_readable} for security gaps, hidden exits, or anything useful",
                category=ACTION_CATEGORY_COMMIT,
                risk_level=ACTION_RISK_SAFE,
                strategy_tag=STRATEGY_TAG_OPTIMAL,
                tone_tag=TONE_TAG_NEUTRAL,
                intent_style="tactical",
                consequence_hint=search_hint,
            )

    base = [
        ActionSuggestion(
            label=paragon_label,
            intent_text=paragon_intent,
            category=ACTION_CATEGORY_SOCIAL,
            risk_level=ACTION_RISK_SAFE,
            strategy_tag=STRATEGY_TAG_OPTIMAL,
            tone_tag=TONE_TAG_PARAGON,
            intent_style="empathetic",
            consequence_hint="may gain trust or new information",
        ),
        ActionSuggestion(
            label=investigate_label,
            intent_text=investigate_intent,
            category=ACTION_CATEGORY_EXPLORE,
            risk_level=ACTION_RISK_SAFE,
            strategy_tag=STRATEGY_TAG_OPTIMAL,
            tone_tag=TONE_TAG_INVESTIGATE,
            intent_style="direct",
            consequence_hint="get concrete leads to follow",
        ),
        ActionSuggestion(
            label=f"Confront {first_npc} directly",
            intent_text=renegade_intent,
            category=ACTION_CATEGORY_SOCIAL,
            risk_level=ACTION_RISK_RISKY,
            strategy_tag=STRATEGY_TAG_ALTERNATIVE,
            tone_tag=TONE_TAG_RENEGADE,
            intent_style="firm",
            consequence_hint="may escalate the situation",
        ),
        neutral_suggestion,
    ]
    return base[:SUGGESTED_ACTIONS_TARGET]


# Keep the old name as an alias for backward compatibility
fallback_suggestions = generate_suggestions


def _post_combat_success_suggestions(first_npc: str, loc_readable: str) -> list[ActionSuggestion]:
    """Suggestions after winning combat."""
    return [
        ActionSuggestion(
            label="Search the fallen for intel",
            intent_text="Search the defeated enemies for datapads, comlinks, or useful intel",
            category=ACTION_CATEGORY_EXPLORE,
            risk_level=ACTION_RISK_SAFE,
            strategy_tag=STRATEGY_TAG_OPTIMAL,
            tone_tag=TONE_TAG_INVESTIGATE,
            intent_style="probing",
            consequence_hint="may reveal their employer or mission",
        ),
        ActionSuggestion(
            label="Interrogate the survivor",
            intent_text="Say: 'Start talking. Who sent you, and why?'",
            category=ACTION_CATEGORY_SOCIAL,
            risk_level=ACTION_RISK_SAFE,
            strategy_tag=STRATEGY_TAG_OPTIMAL,
            tone_tag=TONE_TAG_RENEGADE,
            intent_style="firm",
            consequence_hint="may extract valuable information",
        ),
        ActionSuggestion(
            label="Tend to wounds and regroup",
            intent_text="Take a moment to catch your breath and check for injuries",
            category=ACTION_CATEGORY_EXPLORE,
            risk_level=ACTION_RISK_SAFE,
            strategy_tag=STRATEGY_TAG_OPTIMAL,
            tone_tag=TONE_TAG_PARAGON,
            intent_style="empathetic",
            consequence_hint="recover composure before moving on",
        ),
        ActionSuggestion(
            label="Press deeper while they're disorganized",
            intent_text=f"Push forward through {loc_readable} before reinforcements arrive",
            category=ACTION_CATEGORY_COMMIT,
            risk_level=ACTION_RISK_RISKY,
            strategy_tag=STRATEGY_TAG_ALTERNATIVE,
            tone_tag=TONE_TAG_NEUTRAL,
            intent_style="tactical",
            consequence_hint="may catch them off guard — or walk into a trap",
        ),
    ][:SUGGESTED_ACTIONS_TARGET]


def _post_combat_failure_suggestions(first_npc: str, loc_readable: str) -> list[ActionSuggestion]:
    """Suggestions after losing or barely surviving combat."""
    return [
        ActionSuggestion(
            label="Fall back and find cover",
            intent_text=f"Retreat to a defensible position in {loc_readable}",
            category=ACTION_CATEGORY_COMMIT,
            risk_level=ACTION_RISK_SAFE,
            strategy_tag=STRATEGY_TAG_OPTIMAL,
            tone_tag=TONE_TAG_NEUTRAL,
            intent_style="tactical",
            consequence_hint="regroup and reassess the situation",
        ),
        ActionSuggestion(
            label="Attempt to negotiate",
            intent_text="Say: 'Wait — there's no need for more bloodshed. Let's talk.'",
            category=ACTION_CATEGORY_SOCIAL,
            risk_level=ACTION_RISK_RISKY,
            strategy_tag=STRATEGY_TAG_OPTIMAL,
            tone_tag=TONE_TAG_PARAGON,
            intent_style="empathetic",
            consequence_hint="they might listen — or might not",
        ),
        ActionSuggestion(
            label="Look for an escape route",
            intent_text=f"Scan {loc_readable} for exits, vents, or alternate paths",
            category=ACTION_CATEGORY_EXPLORE,
            risk_level=ACTION_RISK_SAFE,
            strategy_tag=STRATEGY_TAG_OPTIMAL,
            tone_tag=TONE_TAG_INVESTIGATE,
            intent_style="probing",
            consequence_hint="find a way out before things get worse",
        ),
        ActionSuggestion(
            label="Make a desperate stand",
            intent_text="Draw your weapon and fight with everything you have left",
            category=ACTION_CATEGORY_COMMIT,
            risk_level=ACTION_RISK_DANGEROUS,
            strategy_tag=STRATEGY_TAG_ALTERNATIVE,
            tone_tag=TONE_TAG_RENEGADE,
            intent_style="firm",
            consequence_hint="all or nothing — high risk",
        ),
    ][:SUGGESTED_ACTIONS_TARGET]


def _post_stealth_success_suggestions(first_npc: str, loc_readable: str) -> list[ActionSuggestion]:
    """Suggestions after successful stealth."""
    return [
        ActionSuggestion(
            label="Eavesdrop on the conversation",
            intent_text="Stay hidden and listen to what they're saying",
            category=ACTION_CATEGORY_EXPLORE,
            risk_level=ACTION_RISK_SAFE,
            strategy_tag=STRATEGY_TAG_OPTIMAL,
            tone_tag=TONE_TAG_INVESTIGATE,
            intent_style="probing",
            consequence_hint="learn their plans without being detected",
        ),
        ActionSuggestion(
            label="Slip past to the next area",
            intent_text=f"Move quietly through {loc_readable} while they're distracted",
            category=ACTION_CATEGORY_COMMIT,
            risk_level=ACTION_RISK_SAFE,
            strategy_tag=STRATEGY_TAG_OPTIMAL,
            tone_tag=TONE_TAG_NEUTRAL,
            intent_style="tactical",
            consequence_hint="advance deeper undetected",
        ),
        ActionSuggestion(
            label="Reveal yourself peacefully",
            intent_text="Say: 'Don't be alarmed — I'm here to talk, not fight.'",
            category=ACTION_CATEGORY_SOCIAL,
            risk_level=ACTION_RISK_RISKY,
            strategy_tag=STRATEGY_TAG_OPTIMAL,
            tone_tag=TONE_TAG_PARAGON,
            intent_style="empathetic",
            consequence_hint="surprise them but on friendly terms",
        ),
        ActionSuggestion(
            label="Ambush from the shadows",
            intent_text="Strike while they don't know you're here",
            category=ACTION_CATEGORY_COMMIT,
            risk_level=ACTION_RISK_DANGEROUS,
            strategy_tag=STRATEGY_TAG_ALTERNATIVE,
            tone_tag=TONE_TAG_RENEGADE,
            intent_style="firm",
            consequence_hint="decisive but violent — no going back",
        ),
    ][:SUGGESTED_ACTIONS_TARGET]


def _post_stealth_failure_suggestions(first_npc: str, loc_readable: str) -> list[ActionSuggestion]:
    """Suggestions after failed stealth (caught)."""
    return [
        ActionSuggestion(
            label="Bluff your way out",
            intent_text="Say: 'Easy — I'm supposed to be here. Check with your superior.'",
            category=ACTION_CATEGORY_SOCIAL,
            risk_level=ACTION_RISK_RISKY,
            strategy_tag=STRATEGY_TAG_OPTIMAL,
            tone_tag=TONE_TAG_INVESTIGATE,
            intent_style="probing",
            consequence_hint="might buy time or convince them",
        ),
        ActionSuggestion(
            label="Surrender peacefully",
            intent_text="Say: 'Alright, you caught me. I'm not looking for trouble.'",
            category=ACTION_CATEGORY_SOCIAL,
            risk_level=ACTION_RISK_SAFE,
            strategy_tag=STRATEGY_TAG_OPTIMAL,
            tone_tag=TONE_TAG_PARAGON,
            intent_style="empathetic",
            consequence_hint="avoid violence but lose freedom",
        ),
        ActionSuggestion(
            label="Fight your way free",
            intent_text="Draw your weapon and make a break for it",
            category=ACTION_CATEGORY_COMMIT,
            risk_level=ACTION_RISK_DANGEROUS,
            strategy_tag=STRATEGY_TAG_ALTERNATIVE,
            tone_tag=TONE_TAG_RENEGADE,
            intent_style="firm",
            consequence_hint="dangerous but may be the only way out",
        ),
        ActionSuggestion(
            label="Create a distraction",
            intent_text=f"Look around {loc_readable} for something to cause a diversion",
            category=ACTION_CATEGORY_EXPLORE,
            risk_level=ACTION_RISK_RISKY,
            strategy_tag=STRATEGY_TAG_OPTIMAL,
            tone_tag=TONE_TAG_NEUTRAL,
            intent_style="tactical",
            consequence_hint="may create an opening to escape",
        ),
    ][:SUGGESTED_ACTIONS_TARGET]


def action_suggestion_to_player_response(
    sug: ActionSuggestion,
    index: int,
    scene_frame: dict | None = None,
) -> dict:
    """Convert an ActionSuggestion to a PlayerResponse dict (V2.17).

    Returns a dict matching the PlayerResponse schema in dialogue_turn.py.
    Validates targets against scene_frame.present_npcs if provided.
    V2.18: Includes meaning_tag from ActionSuggestion.
    """
    from backend.app.models.dialogue_turn import infer_intent, infer_action_type, infer_meaning_tag

    label = sug.label or ""
    intent_text = sug.intent_text or label

    # Infer action type and intent
    action_type = infer_action_type(intent_text)
    intent = infer_intent(label)

    # Resolve target: find first NPC name mentioned in the label
    target = None
    if scene_frame:
        present = scene_frame.get("present_npcs") or []
        for npc in present:
            npc_name = npc.get("name", "")
            if npc_name and npc_name.lower() in label.lower():
                target = npc.get("id", npc_name)
                break

    # V2.18: Meaning tag — use from suggestion if available, otherwise infer
    meaning = getattr(sug, "meaning_tag", "") or infer_meaning_tag(label)

    return {
        "id": f"resp_{index + 1}",
        "display_text": label,
        "action": {
            "type": action_type,
            "intent": intent,
            "target": target,
            "tone": sug.tone_tag or TONE_TAG_NEUTRAL,
        },
        "risk_level": sug.risk_level or ACTION_RISK_SAFE,
        "consequence_hint": sug.consequence_hint or "",
        "tone_tag": sug.tone_tag or TONE_TAG_NEUTRAL,
        "meaning_tag": meaning,
    }


def action_suggestions_to_player_responses(
    suggestions: list[ActionSuggestion],
    scene_frame: dict | None = None,
) -> list[dict]:
    """Convert a list of ActionSuggestions to PlayerResponse dicts."""
    return [
        action_suggestion_to_player_response(s, i, scene_frame)
        for i, s in enumerate(suggestions)
    ]


def _exploration_suggestions(
    loc_readable: str,
    stress_level: int = 0,
    *,
    services: list[str] | None = None,
    access_points: list[dict] | None = None,
    travel_links: list[dict] | None = None,
    comp_name: str | None = None,
    comp_influence: int = 0,
    is_return_visit: bool = False,
) -> list[ActionSuggestion]:
    """Suggestions when no NPCs are present (exploration mode).

    V3.0: Enhanced with location-specific services, hidden access points,
    travel links, companion integration, and return-visit awareness.
    """
    services = services or []
    access_points = access_points or []
    travel_links = travel_links or []

    # ── Slot 1: INVESTIGATE — location-specific or default search ──
    if "bounty_board" in services:
        investigate_sug = ActionSuggestion(
            label="Check the bounty board",
            intent_text=f"Walk over to the bounty board in {loc_readable} and see what work is posted",
            category=ACTION_CATEGORY_EXPLORE,
            risk_level=ACTION_RISK_SAFE,
            strategy_tag=STRATEGY_TAG_OPTIMAL,
            tone_tag=TONE_TAG_INVESTIGATE,
            intent_style="probing",
            consequence_hint="might find paying work or leads",
        )
    elif "briefing_room" in services:
        investigate_sug = ActionSuggestion(
            label="Check the briefing room",
            intent_text=f"Head to the briefing room in {loc_readable} for intelligence updates",
            category=ACTION_CATEGORY_EXPLORE,
            risk_level=ACTION_RISK_SAFE,
            strategy_tag=STRATEGY_TAG_OPTIMAL,
            tone_tag=TONE_TAG_INVESTIGATE,
            intent_style="probing",
            consequence_hint="may reveal mission intel or objectives",
        )
    elif is_return_visit:
        investigate_sug = ActionSuggestion(
            label=f"Notice what's changed in {loc_readable}",
            intent_text=f"Look around {loc_readable} for anything different since your last visit",
            category=ACTION_CATEGORY_EXPLORE,
            risk_level=ACTION_RISK_SAFE,
            strategy_tag=STRATEGY_TAG_OPTIMAL,
            tone_tag=TONE_TAG_INVESTIGATE,
            intent_style="probing",
            consequence_hint="familiarity helps you spot changes",
        )
    else:
        investigate_sug = ActionSuggestion(
            label=f"Search {loc_readable} for clues",
            intent_text=f"Carefully examine {loc_readable} for anything out of the ordinary",
            category=ACTION_CATEGORY_EXPLORE,
            risk_level=ACTION_RISK_SAFE,
            strategy_tag=STRATEGY_TAG_OPTIMAL,
            tone_tag=TONE_TAG_INVESTIGATE,
            intent_style="probing",
            consequence_hint="may uncover hidden information",
        )

    # ── Slot 2: NEUTRAL — companion-aware or wait-and-observe ──
    if comp_name and comp_influence > 30:
        neutral_sug = ActionSuggestion(
            label=f"Ask {comp_name} about this place",
            intent_text=f"Say: '{comp_name}, ever been here before? What should I know?'",
            category=ACTION_CATEGORY_SOCIAL,
            risk_level=ACTION_RISK_SAFE,
            strategy_tag=STRATEGY_TAG_OPTIMAL,
            tone_tag=TONE_TAG_NEUTRAL,
            intent_style="tactical",
            consequence_hint=f"{comp_name} may share local knowledge",
        )
    else:
        neutral_sug = ActionSuggestion(
            label="Wait and observe",
            intent_text="Find a vantage point and watch for movement or activity",
            category=ACTION_CATEGORY_EXPLORE,
            risk_level=ACTION_RISK_SAFE,
            strategy_tag=STRATEGY_TAG_OPTIMAL,
            tone_tag=TONE_TAG_NEUTRAL,
            intent_style="tactical",
            consequence_hint="patience may reveal what rushing won't",
        )

    # ── Slot 3: INVESTIGATE/PARAGON — hidden access or terminals ──
    hidden_access = [ap for ap in access_points if ap.get("visibility") in ("hidden", "secret")]
    if hidden_access:
        slot3_sug = ActionSuggestion(
            label="Search for hidden passages",
            intent_text=f"Carefully examine the walls and floor of {loc_readable} for concealed exits",
            category=ACTION_CATEGORY_EXPLORE,
            risk_level=ACTION_RISK_RISKY,
            strategy_tag=STRATEGY_TAG_OPTIMAL,
            tone_tag=TONE_TAG_INVESTIGATE,
            intent_style="probing",
            consequence_hint="may reveal a secret route",
        )
    elif "slicer" in services or "market" in services:
        slot3_sug = ActionSuggestion(
            label="Browse what's for sale",
            intent_text=f"Check the vendor stalls or terminals in {loc_readable} for useful gear",
            category=ACTION_CATEGORY_EXPLORE,
            risk_level=ACTION_RISK_SAFE,
            strategy_tag=STRATEGY_TAG_OPTIMAL,
            tone_tag=TONE_TAG_INVESTIGATE,
            intent_style="probing",
            consequence_hint="might find something worth buying",
        )
    else:
        slot3_sug = ActionSuggestion(
            label="Check for terminals or consoles",
            intent_text=f"Look for any computer terminals or datapads in {loc_readable}",
            category=ACTION_CATEGORY_EXPLORE,
            risk_level=ACTION_RISK_SAFE,
            strategy_tag=STRATEGY_TAG_OPTIMAL,
            tone_tag=TONE_TAG_INVESTIGATE,
            intent_style="probing",
            consequence_hint="digital records often hold secrets",
        )

    # ── Slot 4: COMMIT/ALTERNATIVE — travel link or keep moving ──
    if travel_links:
        dest_id = travel_links[0].get("to_location_id", "")
        dest_readable = _humanize_location_for_suggestion(dest_id)
        slot4_sug = ActionSuggestion(
            label=f"Head to {dest_readable}",
            intent_text=f"Leave {loc_readable} and travel to {dest_readable}",
            category=ACTION_CATEGORY_COMMIT,
            risk_level=ACTION_RISK_SAFE,
            strategy_tag=STRATEGY_TAG_ALTERNATIVE,
            tone_tag=TONE_TAG_NEUTRAL,
            intent_style="tactical",
            consequence_hint="change scenery and find new leads",
        )
    else:
        slot4_sug = ActionSuggestion(
            label="Keep moving",
            intent_text=f"Continue through {loc_readable} toward the next area",
            category=ACTION_CATEGORY_COMMIT,
            risk_level=ACTION_RISK_SAFE,
            strategy_tag=STRATEGY_TAG_ALTERNATIVE,
            tone_tag=TONE_TAG_NEUTRAL,
            intent_style="tactical",
            consequence_hint="press onward to the next encounter",
        )

    suggestions = [investigate_sug, neutral_sug, slot3_sug, slot4_sug]

    # High stress: swap last option with calming one
    if stress_level > 7:
        suggestions[-1] = ActionSuggestion(
            label="Take a moment to steady yourself",
            intent_text="Pause, breathe, and center yourself before continuing",
            category=ACTION_CATEGORY_EXPLORE,
            risk_level=ACTION_RISK_SAFE,
            strategy_tag=STRATEGY_TAG_ALTERNATIVE,
            tone_tag=TONE_TAG_PARAGON,
            intent_style="empathetic",
            consequence_hint="reduce stress and regain focus",
        )
    return suggestions[:SUGGESTED_ACTIONS_TARGET]
