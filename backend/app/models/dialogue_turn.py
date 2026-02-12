"""V2.17+V2.18 DialogueTurn contract: canonical turn output with KOTOR-soul depth.

Every gameplay turn produces exactly ONE DialogueTurn that the UI renders.
Narration never embeds numbered options; choices come only from player_responses.
V2.18 adds topic anchoring, NPC voice profiles, meaning_tags, and depth budgets.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

class NPCRef(BaseModel):
    """Lightweight NPC reference within a scene."""
    id: str
    name: str
    role: str
    # V2.18: Compact voice profile (populated by SceneFrame node from personality_profile)
    # Keys: belief, wound, taboo, rhetorical_style, tell
    voice_profile: dict = Field(default_factory=dict)


class SceneFrame(BaseModel):
    """Immutable snapshot of the scene at decision time.

    Built once per turn by the SceneFrame node. Director, Narrator, and
    SuggestionRefiner all consume this — never contradict it.
    """
    location_id: str
    location_name: str                    # humanized, e.g. "the cantina"
    present_npcs: list[NPCRef] = Field(default_factory=list)
    immediate_situation: str = ""         # 1 sentence: what's happening RIGHT NOW
    player_objective: str = ""            # 1 sentence: what the player is trying to do
    allowed_scene_type: str = "dialogue"  # dialogue | combat | exploration | travel | stealth
    scene_hash: str = ""                  # deterministic hash for cache-keying / drift detection
    # V2.18: KOTOR-soul context (internal, not rendered by default)
    topic_primary: str = ""               # 1-3 words: "trust", "debt", "identity"
    topic_secondary: str = ""             # optional secondary topic
    subtext: str = ""                     # 1 sentence: what scene is REALLY about emotionally
    npc_agenda: str = ""                  # 1 sentence: what the NPC wants from the player
    scene_style_tags: list[str] = Field(default_factory=list)  # "Socratic", "noir", "military"
    pressure: dict = Field(default_factory=dict)  # {"alert": "Quiet|Watchful|Lockdown", "heat": "Low|Noticed|Wanted"}


class NPCUtterance(BaseModel):
    """Focused NPC speech (or narrator observation) for this turn.

    speaker_id is an NPC id from the SceneFrame or the literal "narrator".
    text is 1-3 lines of dialogue/observation, max ~500 chars.
    """
    speaker_id: str = "narrator"
    speaker_name: str = "Narrator"
    text: str = ""
    # V2.18: KOTOR-soul debug metadata
    subtext_hint: str = ""                                   # debug: "she's testing you"
    rhetorical_moves: list[str] = Field(default_factory=list)  # ["challenge", "probe"]


class PlayerAction(BaseModel):
    """Structured intent behind a player response."""
    type: str = "do"          # "say" | "do"
    intent: str = "observe"   # ask|agree|bluff|threaten|charm|refuse|observe|leave|attack|bribe|...
    target: str | None = None # npc_id or object — must be valid vs SceneFrame if present
    tone: str | None = None   # PARAGON | INVESTIGATE | RENEGADE | NEUTRAL


class PlayerResponse(BaseModel):
    """One numbered option the player can choose (KOTOR-style)."""
    id: str                              # "resp_1", "resp_2", …
    display_text: str                    # short, punchy line shown in UI
    action: PlayerAction
    risk_level: str = "SAFE"             # SAFE | RISKY | DANGEROUS
    consequence_hint: str = ""           # hidden hint (debug only)
    tone_tag: str = "NEUTRAL"            # drives UI colour
    # V2.18: meaningful response classification (internal, drives variety enforcement)
    meaning_tag: str = ""                # reveal_values|probe_belief|challenge_premise|seek_history|set_boundary|pragmatic|deflect


class ValidationReport(BaseModel):
    """Non-blocking validation results (debug only)."""
    checks_passed: list[str] = Field(default_factory=list)
    checks_failed: list[str] = Field(default_factory=list)
    repairs_applied: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Top-level contract
# ---------------------------------------------------------------------------

class DialogueTurn(BaseModel):
    """Canonical turn output: scene + NPC line + player choices.

    The UI renders ONLY this object. narrated_prose is stored for the
    journal/transcript but is NOT shown in the active dialogue panel.
    """
    turn_id: str                                         # "{campaign_id}_t{turn_number}"
    scene_frame: SceneFrame
    npc_utterance: NPCUtterance
    player_responses: list[PlayerResponse] = Field(default_factory=list)  # 3-6 responses
    # Meta / debug — NOT rendered in dialogue panel
    narrated_prose: str = ""                             # full Narrator prose (journal)
    validation: ValidationReport | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def compute_scene_hash(
    location_id: str,
    npc_ids: list[str],
    action_type: str = "",
) -> str:
    """Deterministic hash for a scene configuration.

    Same inputs always produce the same hash.  Used for drift detection
    and (future) cache-keying.
    """
    canonical = "|".join([
        location_id or "",
        ",".join(sorted(npc_ids)),
        (action_type or "").upper(),
    ])
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Intent inference from text (shared by converter + refiner)
# ---------------------------------------------------------------------------

# Verb → intent mapping (order matters: first match wins)
_INTENT_VERBS: dict[str, list[str]] = {
    "ask": ["ask", "question", "inquire"],
    "agree": ["agree", "accept", "nod", "comply"],
    "refuse": ["refuse", "decline", "reject", "deny"],
    "threaten": ["threaten", "intimidate", "warn", "menace"],
    "bluff": ["bluff", "deceive", "lie", "feint"],
    "charm": ["charm", "flatter", "compliment", "seduce"],
    "bribe": ["bribe", "pay", "offer"],
    "observe": ["observe", "watch", "wait", "scan", "examine", "search", "look", "check", "inspect"],
    "leave": ["leave", "depart", "flee", "escape", "retreat", "exit", "slip"],
    "attack": ["attack", "fight", "strike", "shoot", "stab", "ambush"],
    "say": ["say", "tell", "speak", "greet", "introduce", "comfort", "reassure"],
}


def infer_intent(text: str) -> str:
    """Infer a PlayerAction intent from display_text / label text."""
    words = set(re.findall(r"[a-zA-Z]+", text.lower()))
    lead = ""
    lead_match = re.match(r"([a-zA-Z]+)", text.lower())
    if lead_match:
        lead = lead_match.group(1)
    # Check lead verb first (highest signal)
    for intent, verbs in _INTENT_VERBS.items():
        if lead in verbs:
            return intent
    # Then check any word
    for intent, verbs in _INTENT_VERBS.items():
        if words & set(verbs):
            return intent
    return "observe"


def infer_action_type(intent_text: str) -> str:
    """Infer 'say' or 'do' from an intent_text string."""
    if re.match(r"(?:Say|Ask|Tell)\s*:", intent_text, re.I):
        return "say"
    return "do"


# ---------------------------------------------------------------------------
# V2.18: Meaning tag inference
# ---------------------------------------------------------------------------

# Lead verb → meaning_tag mapping
_MEANING_VERBS: dict[str, list[str]] = {
    "seek_history": ["ask", "question", "inquire", "learn", "discover", "find"],
    "probe_belief": ["press", "investigate", "examine", "probe", "study", "test"],
    "challenge_premise": ["challenge", "confront", "demand", "dispute", "counter", "deny", "refuse"],
    "reveal_values": ["help", "offer", "comfort", "protect", "share", "show", "give", "reassure", "encourage"],
    "set_boundary": ["threaten", "intimidate", "warn", "reject", "forbid", "block"],
    "pragmatic": ["search", "check", "scan", "wait", "observe", "focus", "plan", "prepare", "move"],
    "deflect": ["slip", "leave", "escape", "joke", "ignore", "shrug", "deflect", "avoid", "retreat"],
    "offer_alliance": ["join", "alliance", "together", "unite", "side"],
    "express_doubt": ["doubt", "unsure", "trust", "certain", "sure"],
    "invoke_authority": ["order", "authority", "command", "rank", "senate"],
    "show_vulnerability": ["afraid", "scared", "help", "need", "please"],
    "make_demand": ["demand", "insist", "must", "now", "require"],
}


def infer_meaning_tag(text: str) -> str:
    """Infer a meaning_tag from display_text / label text."""
    words = set(re.findall(r"[a-zA-Z]+", text.lower()))
    lead = ""
    lead_match = re.match(r"([a-zA-Z]+)", text.lower())
    if lead_match:
        lead = lead_match.group(1)
    # Check lead verb first
    for tag, verbs in _MEANING_VERBS.items():
        if lead in verbs:
            return tag
    # Then check any word
    for tag, verbs in _MEANING_VERBS.items():
        if words & set(verbs):
            return tag
    return "pragmatic"


# ---------------------------------------------------------------------------
# V2.18: Depth budget policy (not persisted — used by validators)
# ---------------------------------------------------------------------------

class DepthBudget(BaseModel):
    """Policy object for enforcing KOTOR-style depth constraints."""
    max_scene_sentences: int = 3
    max_npc_lines: int = 4
    max_response_words: int = 16
    min_meaning_tags: int = 3    # distinct tags required for 4+ options
    min_tone_tags: int = 3       # distinct tones required for 4+ options


# Singleton default budget
DEFAULT_DEPTH_BUDGET = DepthBudget()
