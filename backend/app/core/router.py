"""Router: classify user input for TALK vs MECHANIC routing. Security: only DIALOGUE_ONLY skips Mechanic."""
from __future__ import annotations

import re
from backend.app.models.state import (
    RouterOutput,
    ROUTER_ROUTE_TALK,
    ROUTER_ROUTE_MECHANIC,
    ROUTER_ROUTE_META,
    ROUTER_ACTION_CLASS_DIALOGUE_ONLY,
    ROUTER_ACTION_CLASS_DIALOGUE_WITH_ACTION,
    ROUTER_ACTION_CLASS_PHYSICAL_ACTION,
    ROUTER_ACTION_CLASS_META,
)

# High-signal action verbs: if present, never treat as DIALOGUE_ONLY (prevents smuggling violence/theft into dialogue)
ACTION_VERBS = frozenset({
    "stab", "stabs", "stabbing", "stabbed",
    "shoot", "shoots", "shooting", "shot",
    "steal", "steals", "stealing", "stole", "stolen",
    "punch", "punches", "punching", "punched",
    "grab", "grabs", "grabbing", "grabbed",
    "run", "runs", "running", "ran",
    "sneak", "sneaks", "sneaking", "sneaked", "snuck",
    "hack", "hacks", "hacking", "hacked",
    "pickpocket", "pickpockets", "pickpocketing", "pickpocketed",
    "attack", "attacks", "attacking", "attacked",
    "kill", "kills", "killing", "killed",
    "hit", "hits", "hitting",
    "slash", "slashes", "slashing", "slashed",
    "strike", "strikes", "striking", "struck",
    "pull", "pulls", "pulling", "pulled",  # e.g. "pull my blaster"
    "draw", "draws", "drawing", "drew", "drawn",  # draw weapon
    "throw", "throws", "throwing", "threw", "thrown",
    "take", "takes", "taking", "took", "taken",  # take item / take action
    "push", "pushes", "pushing", "pushed",
    "kick", "kicks", "kicking", "kicked",
    "strangle", "strangles", "strangling", "strangled",
    "poison", "poisons", "poisoning", "poisoned",
    "lockpick", "lockpicks", "lockpicking", "lockpicked",
    "pick", "picks", "picking", "picked",  # pick lock, pick pocket
})

# Persuasion/intimidation/deception: dialogue that changes the world → must go to Mechanic (requires_resolution=True)
# Word-boundary so we don't match "believe" for "lie", or "negotiation" only when intended as verb form.
PERSUASION_VERBS = frozenset({
    "persuade", "persuades", "persuading", "persuaded",
    "convince", "convinces", "convincing", "convinced",
    "intimidate", "intimidates", "intimidating", "intimidated",
    "deceive", "deceives", "deceiving", "deceived",
    "negotiate", "negotiates", "negotiating", "negotiated",
    "bribe", "bribes", "bribing", "bribed",
    "threaten", "threatens", "threatening", "threatened",
    "demand", "demands", "demanding", "demanded",
    "blackmail", "blackmails", "blackmailing", "blackmailed",
})
# "lie" as verb: "I lie" / "I'm lying" / "lying" (avoid "believe", "unlikely" via word boundary)
LIE_VERB_PATTERN = re.compile(r"\b(lie|lies|lying|lied)\b", re.IGNORECASE)
# "ask ... to" = ask someone TO do something (behavior change), not just "ask where/when/what"
ASK_TO_PATTERN = re.compile(r"\bask\s+(him|her|them|you|the\s+\w+)\s+to\b", re.IGNORECASE)


def _tokenize_for_verbs(text: str) -> set[str]:
    """Lowercase word tokens for guardrail check."""
    if not text or not text.strip():
        return set()
    # Remove punctuation for word-boundary check, then split
    cleaned = re.sub(r"[^\w\s]", " ", (text or "").lower())
    return set(cleaned.split())


def action_verb_guardrail_triggers(user_input: str) -> bool:
    """True if user input contains high-signal action verbs (must not skip Mechanic)."""
    tokens = _tokenize_for_verbs(user_input)
    return bool(tokens & ACTION_VERBS)


def persuasion_guardrail_triggers(user_input: str) -> bool:
    """True if dialogue attempts persuasion/intimidation/deception or materially changes NPC behavior (must go to Mechanic)."""
    if not user_input or not user_input.strip():
        return False
    low = user_input.lower().strip()
    tokens = _tokenize_for_verbs(user_input)
    if tokens & PERSUASION_VERBS:
        return True
    if LIE_VERB_PATTERN.search(user_input):
        return True
    if ASK_TO_PATTERN.search(user_input):
        return True
    return False


def route(user_input: str) -> RouterOutput:
    """
    Classify user input into route and action_class.
    Only when route==TALK and action_class==DIALOGUE_ONLY should the pipeline skip the Mechanic.

    V2.7: Supports combined [DIALOGUE] <text> [ACTION] <text> format from split action UI.
    """
    raw = (user_input or "").strip()
    low = raw.lower()

    # V2.7: Parse combined dialogue + action format
    # Format: "[DIALOGUE] <dialogue text> [ACTION] <action text>"
    dialogue_match = re.search(r"\[DIALOGUE\]\s*(.+?)(?=\[ACTION\]|$)", raw, re.IGNORECASE | re.DOTALL)
    action_match = re.search(r"\[ACTION\]\s*(.+?)$", raw, re.IGNORECASE | re.DOTALL)

    if dialogue_match and action_match:
        # Both dialogue and action present → treat as DIALOGUE_WITH_ACTION
        dialogue_text = dialogue_match.group(1).strip()
        action_text = action_match.group(1).strip()
        combined = f"{dialogue_text} {action_text}"
        return RouterOutput(
            intent_text=combined,
            route=ROUTER_ROUTE_MECHANIC,
            action_class=ROUTER_ACTION_CLASS_DIALOGUE_WITH_ACTION,
            requires_resolution=True,
            confidence=1.0,
            rationale_short="split UI: dialogue + action combined",
        )
    elif dialogue_match and not action_match:
        # Only dialogue → treat as DIALOGUE_ONLY (skip Mechanic unless it has action verbs)
        dialogue_text = dialogue_match.group(1).strip()
        # Re-route through normal classification to check for action verbs
        raw = dialogue_text
        low = raw.lower()
    elif action_match and not dialogue_match:
        # Only action → treat as PHYSICAL_ACTION
        action_text = action_match.group(1).strip()
        return RouterOutput(
            intent_text=action_text,
            route=ROUTER_ROUTE_MECHANIC,
            action_class=ROUTER_ACTION_CLASS_PHYSICAL_ACTION,
            requires_resolution=True,
            confidence=1.0,
            rationale_short="split UI: action only",
        )

    # 1) Heuristic: pure dialogue cues -> TALK + DIALOGUE_ONLY (candidate)
    looks_like_dialogue_only = False
    rationale = ""

    if low.startswith("say:"):
        looks_like_dialogue_only = True
        rationale = "say: prefix"
    elif '"' in raw or "'" in raw:
        # Quoted speech
        looks_like_dialogue_only = True
        rationale = "quoted speech"
    elif re.search(r"\bi\s+(ask|tell|say|reply|answer|whisper|shout)\s+(him|her|them|you|the\s+)", low):
        # "I ask him...", "I tell her...", "I say to the guard..."
        looks_like_dialogue_only = True
        rationale = "I ask/tell/say pattern"
    elif re.search(r"\bi('m| am)\s+(just\s+)?(saying|asking|telling)", low):
        looks_like_dialogue_only = True
        rationale = "I'm saying/asking/telling"
    elif re.search(r"^(tell|ask)\s+(him|her|them|you)\b", low):
        looks_like_dialogue_only = True
        rationale = "tell/ask him/her"

    # 2) Deterministic guardrail: action verbs -> never META, never DIALOGUE_ONLY (must hit Mechanic)
    if action_verb_guardrail_triggers(raw):
        if looks_like_dialogue_only or '"' in raw or "'" in raw or "say" in low or "tell" in low or "ask" in low:
            return RouterOutput(
                intent_text=raw,
                route=ROUTER_ROUTE_MECHANIC,
                action_class=ROUTER_ACTION_CLASS_DIALOGUE_WITH_ACTION,
                requires_resolution=True,
                confidence=1.0,
                rationale_short="guardrail: action verb in input",
            )
        return RouterOutput(
            intent_text=raw,
            route=ROUTER_ROUTE_MECHANIC,
            action_class=ROUTER_ACTION_CLASS_PHYSICAL_ACTION,
            requires_resolution=True,
            confidence=1.0,
            rationale_short="guardrail: action verb",
        )

    # 2b) Persuasion/intimidation/deception: dialogue that changes the world -> Mechanic (requires_resolution=True)
    if persuasion_guardrail_triggers(raw):
        return RouterOutput(
            intent_text=raw,
            route=ROUTER_ROUTE_MECHANIC,
            action_class=ROUTER_ACTION_CLASS_DIALOGUE_WITH_ACTION,
            requires_resolution=True,
            confidence=1.0,
            rationale_short="guardrail: persuasion/intimidation/deception or ask ... to",
        )

    # 3) Meta: save/load/help/quit — only when no action verb (so "I ask for help and stab him" -> Mechanic)
    if re.search(r"\b(save|load|help|menu|quit)\b", low) and not re.search(r"\b(save\s+him|load\s+the)\b", low):
        # Normalize intent_text for meta
        if re.search(r"\bhelp\b", low):
            meta_intent = "help"
        elif re.search(r"\bsave\b", low):
            meta_intent = "save"
        elif re.search(r"\bload\b", low):
            meta_intent = "load"
        elif re.search(r"\b(quit|menu)\b", low):
            meta_intent = "quit"
        else:
            meta_intent = "help"
        return RouterOutput(
            intent_text=meta_intent,
            route=ROUTER_ROUTE_META,
            action_class=ROUTER_ACTION_CLASS_META,
            requires_resolution=False,
            confidence=0.9,
            rationale_short="meta command",
        )

    # 4) Dialogue-only path: skip Mechanic only when safe (no persuasion guardrail triggered above)
    if looks_like_dialogue_only:
        return RouterOutput(
            intent_text=raw,
            route=ROUTER_ROUTE_TALK,
            action_class=ROUTER_ACTION_CLASS_DIALOGUE_ONLY,
            requires_resolution=False,
            confidence=0.85,
            rationale_short=rationale or "dialogue-only",
        )

    # 5) Default: send to Mechanic
    return RouterOutput(
        intent_text=raw,
        route=ROUTER_ROUTE_MECHANIC,
        action_class=ROUTER_ACTION_CLASS_PHYSICAL_ACTION,
        requires_resolution=True,
        confidence=0.8,
        rationale_short="default to mechanic",
    )
