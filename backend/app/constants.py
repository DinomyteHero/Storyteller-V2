"""Centralized tuning constants shared across the app.

All numeric tuning parameters live here (not in agent code or config.py).
Environment-variable overrides live in config.py; this file holds defaults only.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.app.banter_pool import BANTER_POOL, BANTER_MEMORY_POOL  # noqa: F401

# ── Campaign scale tiers ─────────────────────────────────────────────
# Controls how many locations, NPCs, quests, and per-scene caps a campaign uses.
# Stored in world_state_json["campaign_scale"] at creation time.

VALID_CAMPAIGN_SCALES = ("small", "medium", "large", "epic")


class CampaignScaleTier(str, Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    EPIC = "epic"


@dataclass(frozen=True)
class CampaignScaleProfile:
    """Numeric profile for a campaign scale tier."""
    generated_locations: int
    generated_npcs: int
    generated_quests: int
    max_present_npcs: int       # Default per-scene NPC cap (replaces MAX_PRESENT_NPCS)
    npc_cap_multiplier: float   # Applied to location-tag NPC caps
    early_game_npc_cap: int     # Max new named NPCs during early-game window
    background_figure_count: int


CAMPAIGN_SCALE_PROFILES: dict[CampaignScaleTier, CampaignScaleProfile] = {
    CampaignScaleTier.SMALL: CampaignScaleProfile(
        generated_locations=3,
        generated_npcs=5,
        generated_quests=2,
        max_present_npcs=1,
        npc_cap_multiplier=0.75,
        early_game_npc_cap=2,
        background_figure_count=2,
    ),
    CampaignScaleTier.MEDIUM: CampaignScaleProfile(
        generated_locations=5,
        generated_npcs=10,
        generated_quests=4,
        max_present_npcs=2,
        npc_cap_multiplier=1.0,
        early_game_npc_cap=3,
        background_figure_count=3,
    ),
    CampaignScaleTier.LARGE: CampaignScaleProfile(
        generated_locations=8,
        generated_npcs=16,
        generated_quests=6,
        max_present_npcs=3,
        npc_cap_multiplier=1.5,
        early_game_npc_cap=5,
        background_figure_count=4,
    ),
    CampaignScaleTier.EPIC: CampaignScaleProfile(
        generated_locations=12,
        generated_npcs=24,
        generated_quests=8,
        max_present_npcs=4,
        npc_cap_multiplier=2.0,
        early_game_npc_cap=7,
        background_figure_count=5,
    ),
}


def get_scale_profile(scale: str | None = None) -> CampaignScaleProfile:
    """Get the scale profile for a campaign scale tier. Defaults to MEDIUM."""
    if not scale:
        return CAMPAIGN_SCALE_PROFILES[CampaignScaleTier.MEDIUM]
    try:
        tier = CampaignScaleTier(scale.lower())
    except ValueError:
        return CAMPAIGN_SCALE_PROFILES[CampaignScaleTier.MEDIUM]
    return CAMPAIGN_SCALE_PROFILES[tier]


# ── Narrative ledger limits ───────────────────────────────────────────
# Maximum items retained in each ledger list. Oldest are evicted FIFO when full.
LEDGER_MAX_FACTS = 40           # Established facts (world truths the Narrator must respect)
LEDGER_MAX_THREADS = 10         # Open narrative threads (unresolved plot hooks)
LEDGER_MAX_GOALS = 10           # Active player/party goals
LEDGER_MAX_CONSTRAINTS = 10     # Hard constraints (e.g., "NPC X is dead")
LEDGER_MAX_TONE_TAGS = 5        # Tone descriptors for the current narrative mood

# ── Memory compression ────────────────────────────────────────────────
# Controls how turn history is compressed into summaries for LLM context.
MEMORY_RECENT_TURNS = 10                # Number of recent turns kept verbatim in hot state
MEMORY_COMPRESSION_CHUNK_SIZE = 10      # Turns grouped per era summary during compression
MEMORY_MAX_ERA_SUMMARIES = 30           # Maximum era summaries retained (was 20)
MEMORY_ERA_SUMMARY_MAX_CHARS = 800      # Max characters per era summary

# Phase 3.2 tiered memory controls
MEMORY_HOT_TURNS = 10                   # Full-fidelity near-term turn window
MEMORY_WARM_TURNS = 50                  # Mid-term retrieval window
MEMORY_COLD_MAX_SUMMARIES = 30          # Long-tail compressed summaries retained (was 20)
MEMORY_COLD_SUMMARY_MAX_CHARS = 800     # Max chars for cold summaries
MEMORY_CRYSTALLIZED_MAX = 40            # Permanent important moments per campaign (was 25)

# Phase 3.1 long-campaign performance controls
MAINTENANCE_AGENT_FREQUENCY = 3         # Run non-critical commit LLM agents every N turns (was 5)
NPC_STATES_MAX = 60                     # Cap world_state_json["npc_states"] to most-recently-seen NPCs (was 30)
COMMIT_GROUP2_MAX_WORKERS = 2           # Parallel worker count for MemoryAgent + QuestWeaverAgent
PROGRESSION_INTERVAL_BASE = 10          # Progression cadence outside high-intensity arc stages
PROGRESSION_INTERVAL_HIGH_INTENSITY = 5 # Progression cadence during RISING/CLIMAX
QUEST_WEAVER_GENERATION_INTERVAL = 10   # Dynamic quest generation cadence (turn-based)

# ── Mechanic delta clamps ─────────────────────────────────────────────
# Maximum per-turn stat change from any single mechanic event.
# Prevents runaway stat inflation/deflation from a single action.
DELTA_CLAMP_MIN = -10
DELTA_CLAMP_MAX = 10

# ── Token estimation factors (ContextBudget) ──────────────────────────
# Rough ratios for estimating token counts without a tokenizer.
TOKEN_ESTIMATE_CHARS_PER_TOKEN = 4      # ~4 characters per token (English average)
TOKEN_ESTIMATE_WORDS_PER_TOKEN = 1.3    # ~1.3 words per token

# ── Retry counts ──────────────────────────────────────────────────────
DIRECTOR_MAX_RETRIES = 2                # Max LLM retries for Director instructions
JSON_RELIABILITY_MAX_RETRIES = 3        # Max retries for JSON parse/repair cycle

# ── Similarity thresholds ─────────────────────────────────────────────
INTENT_JACCARD_THRESHOLD = 0.6          # Min Jaccard similarity to consider intents equivalent

# ── Suggested actions UX contract ─────────────────────────────────────
# Flexible choice count: scene determines how many options (3-6).
# Tone spread is a guideline, not a rigid requirement.
SUGGESTED_ACTIONS_MIN = 3
SUGGESTED_ACTIONS_TARGET = 4            # Default target; scenes may produce 3-6
SUGGESTED_ACTIONS_MAX = 6              # Capped at 6 for UI readability (was 10)

# ── Knowledge Graph retrieval defaults ────────────────────────────────
KG_MAX_RELATIONSHIPS_PER_CHAR = 8       # Max relationship edges per character in KG context
KG_MAX_EVENTS = 3                       # Max recent events per character/location
KG_DIRECTOR_MAX_TOKENS = 600            # Token budget for Director's KG context section
KG_NARRATOR_MAX_TOKENS = 800            # Token budget for Narrator's KG context section

# ── Banter system ─────────────────────────────────────────────────────
# Controls companion banter injection frequency. Moved from banter_manager.py.
BANTER_COMPANION_COOLDOWN = 4           # Min turns between banter from the same companion
BANTER_GLOBAL_COOLDOWN = 2              # Min turns between any banter
BANTER_HISTORY_MAX = 20                 # Max unique LLM-generated banter lines tracked per companion

# ── Companion emotional volatility ────────────────────────────────────
# Emotional states modify companion reactions and banter style.
COMPANION_EMOTIONAL_STATES = ("calm", "agitated", "angry", "vulnerable", "elated")
COMPANION_EMOTION_DECAY_PER_TURN = 1    # Intensity decays by this much each turn toward calm
COMPANION_EMOTION_MAX_INTENSITY = 10    # Maximum emotional intensity (0 = calm)
# Mapping from (tone, emotion) -> affinity multiplier (1.0 = normal)
COMPANION_EMOTION_MULTIPLIERS: dict[tuple[str, str], float] = {
    ("RENEGADE", "angry"): 1.5,         # Angry companions react more strongly to aggression
    ("PARAGON", "vulnerable"): 1.5,     # Vulnerable companions react more to kindness
    ("RENEGADE", "vulnerable"): 0.5,    # Vulnerable companions hurt less by aggression
    ("PARAGON", "angry"): 0.5,          # Angry companions don't care about kindness
    ("INVESTIGATE", "agitated"): 1.3,   # Agitated companions value caution more
}

# ── Genre flavor directives ───────────────────────────────────────────
# Brief prose style guidance injected into Narrator context when genre shifts.
GENRE_FLAVOR_DIRECTIVES: dict[str, str] = {
    "noir": "Use shadow metaphors, moral ambiguity, and cynical internal monologue. Short declarative sentences.",
    "horror": "Emphasize isolation, dread, and sensory detail. Short sentences build tension. What is unseen matters.",
    "heist": "Focus on precision, timing, and the plan. Every detail matters. Build momentum through logistics.",
    "war": "Convey scale, sacrifice, and the fog of battle. Personal moments amid chaos. Visceral sensory detail.",
    "mystery": "Layer clues into environmental description. Let the reader notice before the character does.",
    "romance": "Heighten emotional subtext. Body language speaks louder than dialogue. Lingering details.",
    "thriller": "Escalating stakes. Ticking clocks. Paragraphs get shorter as tension rises.",
    "western": "Sparse prose. Let landscape mirror mood. Silence is as meaningful as speech.",
}

# ── Token budgeting: per-role defaults ────────────────────────────────
# Default max context tokens and reserved output tokens for each LLM role.
# 14b models (narrator/director/architect) get larger budgets;
# lighter models (casting/biographer/mechanic) get smaller.
# Override via env: STORYTELLER_{ROLE}_MAX_CONTEXT_TOKENS,
#                   STORYTELLER_{ROLE}_RESERVED_OUTPUT_TOKENS
ROLE_TOKEN_BUDGETS: dict[str, dict[str, int]] = {
    # Quality-critical roles: larger context for narrative/direction
    "architect": {"max_context_tokens": 8192, "reserved_output_tokens": 2048},
    "director": {"max_context_tokens": 8192, "reserved_output_tokens": 2048},
    "narrator": {"max_context_tokens": 8192, "reserved_output_tokens": 2048},
    # Lighter roles: smaller context for faster inference
    "casting": {"max_context_tokens": 4096, "reserved_output_tokens": 1024},
    "biographer": {"max_context_tokens": 4096, "reserved_output_tokens": 1024},
    "mechanic": {"max_context_tokens": 4096, "reserved_output_tokens": 1024},
    "npc_render": {"max_context_tokens": 2048, "reserved_output_tokens": 512},
    # Ingestion tagger: moderate context, low output
    "ingestion_tagger": {"max_context_tokens": 4096, "reserved_output_tokens": 512},
    # Knowledge graph extractor: moderate context, moderate output
    "kg_extractor": {"max_context_tokens": 6144, "reserved_output_tokens": 2048},
    # Suggestion refiner: small context (prose + scene), small output (JSON array)
    "suggestion_refiner": {"max_context_tokens": 2048, "reserved_output_tokens": 512},
    # Campaign init: generous output for world generation (cloud models have big windows)
    "campaign_init": {"max_context_tokens": 8192, "reserved_output_tokens": 4096},
}

# Thematic resonance (Phase 3)
LEDGER_MAX_THEMES = 3
THEME_REINFORCEMENT_KEYWORDS: dict[str, list[str]] = {
    "cost_of_loyalty": ["betray", "trust", "loyal", "sacrifice", "faith", "oath"],
    "power_corrupts": ["power", "corrupt", "control", "dominate", "authority"],
    "redemption": ["forgive", "atone", "redeem", "second chance", "regret"],
    "survival_vs_morality": ["survive", "moral", "choice", "cost", "compromise"],
    "identity_and_belonging": ["belong", "identity", "home", "outsider", "accept"],
    "hope_against_darkness": ["hope", "dark", "light", "resist", "endure", "defiance"],
    "duty_vs_desire": ["duty", "desire", "want", "must", "obligation", "freedom"],
}

# Dynamic arc staging (Phase 4)
ARC_MIN_TURNS: dict[str, int] = {"SETUP": 3, "RISING": 5, "CLIMAX": 5, "RESOLUTION": 3}
ARC_MAX_TURNS: dict[str, int] = {"SETUP": 10, "RISING": 25, "CLIMAX": 15, "RESOLUTION": 999}
ARC_SETUP_TO_RISING_MIN_THREADS = 2
ARC_SETUP_TO_RISING_MIN_FACTS = 3
ARC_RISING_TO_CLIMAX_MIN_THREADS = 4
ARC_CLIMAX_RESOLUTION_FLAG_PREFIX = "resolved"

# ── Scale auto-advisor thresholds (Phase 2a) ─────────────────────────
# Gated by ENABLE_SCALE_ADVISOR feature flag in config.py.
SCALE_SHIFT_COOLDOWN_TURNS = 15
SCALE_SHIFT_MIN_ARC_STAGE = "RISING"          # Don't advise scale shifts during SETUP
SCALE_ORDER: tuple[str, ...] = ("small", "medium", "large", "epic")
SCALE_UP_SCORE_THRESHOLD = 8                   # density_score >= this → recommend scale up
SCALE_DOWN_SCORE_THRESHOLD = 2                 # density_score <= this → recommend scale down
INTER_CAMPAIGN_SCALE_MAP: dict[str, str] = {
    "SETUP": "small",
    "RISING": "medium",
    "CLIMAX": "large",
    "RESOLUTION": "medium",
}

# ── Conclusion planner thresholds (Phase 2b) ─────────────────────────
# Minimum fraction of threads that must be resolved before a campaign
# can be considered "conclusion ready", keyed by ending style / scale.
CONCLUSION_RESOLVED_RATIO: dict[str, float] = {
    "small": 0.9,     # Nearly everything wrapped up
    "medium": 0.7,    # Most threads resolved
    "large": 0.5,     # Half resolved, half become hooks
    "epic": 0.3,      # Only the primary arc resolved
}
CONCLUSION_MIN_RESOLUTION_TURNS = 2            # At least 2 turns in RESOLUTION before ending
CONCLUSION_ENDING_STYLES: dict[str, str] = {
    "small": "closed",
    "medium": "soft_cliffhanger",
    "large": "open_bittersweet",
    "epic": "full_cliffhanger",
}

# ── Difficulty profiles (Phase 3d) ────────────────────────────────────
# dc_modifier: added to every DC roll
# damage_modifier: multiplier on damage dealt TO the player
# hp_modifier: multiplier on player starting HP
DIFFICULTY_PROFILES: dict[str, dict[str, float]] = {
    "easy":   {"dc_modifier": -2, "damage_modifier": 0.75, "hp_modifier": 1.25},
    "normal": {"dc_modifier": 0,  "damage_modifier": 1.0,  "hp_modifier": 1.0},
    "hard":   {"dc_modifier": 2,  "damage_modifier": 1.5,  "hp_modifier": 0.75},
}

# Phase 4.3: Sandbox impact tiers (choice intent scale -> mechanic difficulty gates).
# dc_modifier: additive check pressure for higher-world-impact actions.
SANDBOX_IMPACT_TIERS: dict[str, dict[str, int | str]] = {
    "ripple": {
        "dc_modifier": 0,
        "min_arc_stage": "SETUP",
        "description": "Local effects only",
    },
    "wave": {
        "dc_modifier": 5,
        "min_arc_stage": "RISING",
        "description": "Regional consequences",
    },
    "tsunami": {
        "dc_modifier": 10,
        "min_arc_stage": "CLIMAX",
        "description": "World-changing consequences",
    },
}

SANDBOX_ARC_STAGE_ORDER: dict[str, int] = {
    "SETUP": 0,
    "RISING": 1,
    "CLIMAX": 2,
    "RESOLUTION": 3,
}

# ── Historical Timeline Scheduler (Phase 3.1) ────────────────────────
# How many turns ahead to look when surfacing upcoming canon events to Director.
CANON_EVENT_LOOKAHEAD_TURNS = 3
# Maximum canon events to trigger in a single turn (prevent event storms).
CANON_EVENT_MAX_PER_TURN = 1

# ── Consequence Propagation (Phase 3.2) ──────────────────────────────
# Duration in turns that follow-on effects last per impact tier.
CONSEQUENCE_DURATION: dict[str, int] = {
    "ripple": 1,    # Local: fades after 1 turn
    "wave": 3,      # Regional: echoes for 3 turns
    "tsunami": 5,   # World-changing: reverberates for 5 turns
}
# Maximum active consequences per campaign (prevent unbounded growth).
CONSEQUENCE_MAX_ACTIVE = 8

# ── Between-Arc Interludes (Phase 3.3) ──────────────────────────────
# Low-stakes decompression turns between RESOLUTION → SETUP transition.
INTERLUDE_MIN_TURNS = 1
INTERLUDE_MAX_TURNS = 2
INTERLUDE_PACING_HINT = (
    "INTERLUDE: Low stakes. Focus on character reflection, companion conversations, "
    "camp scenes, shopping, or downtime activities. No combat or major plot advancement. "
    "Let the player decompress before the next arc begins."
)

# ── Multi-Arc Chaining (Gate 1 — Road to 1.0) ────────────────────────
# Number of arcs before a campaign reaches its conclusion, keyed by scale.
ARC_COUNT_BY_SCALE: dict[str, int] = {
    "small": 2,
    "medium": 3,
    "large": 4,
    "epic": 5,
}
# Epilogue turns after the final arc's RESOLUTION stage.
EPILOGUE_TURNS = 3
EPILOGUE_PACING_HINT = (
    "EPILOGUE: This is the final chapter. Focus on reflection, legacy, and closure. "
    "Show how the world changed. Give companions final moments. End with an evocative "
    "image that lingers."
)
# Time skip during interludes (in-game hours).
INTERLUDE_TIME_SKIP_HOURS = 48

# Companion loyalty breakpoints (Phase 6.2)
COMPANION_LOYALTY_RELUCTANT = -30    # Won't help with risky plans
COMPANION_LOYALTY_THREATENS_LEAVE = -60  # Threatens to leave party
COMPANION_LOYALTY_LEAVES = -80       # Actually leaves the party

# Deep companion system (Phase 5)
COMPANION_ARC_STRANGER_MAX = -10
COMPANION_ARC_ALLY_MIN = -9
COMPANION_ARC_TRUSTED_MIN = 30
COMPANION_ARC_LOYAL_MIN = 70
COMPANION_MAX_MEMORIES = 10
COMPANION_CONFLICT_SHARP_DROP = -8
COMPANION_CONFLICT_THRESHOLD_CROSS = -30

# Hero's Journey beats mapped to arc stages
# Each main stage contains 3 sub-beats that advance by turn count within the stage.
HERO_JOURNEY_BEATS: dict[str, list[dict[str, str]]] = {
    "SETUP": [
        {
            "beat": "ORDINARY_WORLD",
            "pacing": "Establish the character's normal life, routines, and relationships. Show what they stand to lose.",
        },
        {
            "beat": "CALL_TO_ADVENTURE",
            "pacing": "Introduce the inciting incident. Something disrupts the status quo and demands a response.",
        },
        {
            "beat": "REFUSAL_OF_THE_CALL",
            "pacing": "Show hesitation or doubt. The character resists the call — fear, duty, comfort hold them back.",
        },
    ],
    "RISING": [
        {
            "beat": "MEETING_THE_MENTOR",
            "pacing": "Introduce a guide figure who offers wisdom, training, or a crucial gift. Build trust.",
        },
        {
            "beat": "CROSSING_THE_THRESHOLD",
            "pacing": "The character commits to the journey. There is no going back. Raise stakes dramatically.",
        },
        {
            "beat": "TESTS_ALLIES_ENEMIES",
            "pacing": "Challenge the character with trials. Introduce allies and enemies. Build the world of the adventure.",
        },
    ],
    "CLIMAX": [
        {
            "beat": "APPROACH_INMOST_CAVE",
            "pacing": "Preparation for the central ordeal. Tension builds. Plans are made. Doubts resurface.",
        },
        {
            "beat": "ORDEAL",
            "pacing": "The supreme crisis. Life-or-death stakes. The character faces their greatest fear or enemy.",
        },
        {
            "beat": "REWARD",
            "pacing": "Victory or transformation after the ordeal. The character seizes what they came for.",
        },
    ],
    "RESOLUTION": [
        {
            "beat": "THE_ROAD_BACK",
            "pacing": "The journey home begins but new dangers arise. Consequences of the ordeal ripple outward.",
        },
        {
            "beat": "RESURRECTION",
            "pacing": "A final test that proves the character has truly changed. The last threshold.",
        },
        {
            "beat": "RETURN_WITH_ELIXIR",
            "pacing": "The character returns transformed, bearing gifts or wisdom for their community.",
        },
    ],
}

# NPC archetypes for Hero's Journey-aware generation
NPC_ARCHETYPES: dict[str, str] = {
    "MENTOR": "A wise guide who prepares the hero — offers training, advice, or a crucial artifact.",
    "SHADOW": "The primary antagonist or dark reflection of the hero. Embodies what the hero fears becoming.",
    "THRESHOLD_GUARDIAN": "A gatekeeper who tests the hero's resolve before they can advance. Not necessarily evil.",
    "ALLY": "A loyal friend who supports the hero through trials. Provides skills or knowledge the hero lacks.",
    "SHAPESHIFTER": "An ambiguous figure whose loyalty is uncertain. Keeps the hero (and player) guessing.",
    "HERALD": "The bringer of change — delivers the call to adventure or announces a new challenge.",
    "TRICKSTER": "A comic or chaotic figure who disrupts the status quo. Provides relief and unexpected insight.",
}

# Which NPC archetypes are most relevant at each Hero's Journey beat
BEAT_ARCHETYPE_HINTS: dict[str, list[str]] = {
    "ORDINARY_WORLD": ["ALLY"],
    "CALL_TO_ADVENTURE": ["HERALD"],
    "REFUSAL_OF_THE_CALL": ["THRESHOLD_GUARDIAN"],
    "MEETING_THE_MENTOR": ["MENTOR"],
    "CROSSING_THE_THRESHOLD": ["THRESHOLD_GUARDIAN", "ALLY"],
    "TESTS_ALLIES_ENEMIES": ["ALLY", "SHADOW", "TRICKSTER"],
    "APPROACH_INMOST_CAVE": ["SHAPESHIFTER", "SHADOW"],
    "ORDEAL": ["SHADOW"],
    "REWARD": ["ALLY", "MENTOR"],
    "THE_ROAD_BACK": ["SHADOW", "TRICKSTER"],
    "RESURRECTION": ["SHADOW", "MENTOR"],
    "RETURN_WITH_ELIXIR": ["ALLY", "HERALD"],
}


# Director entity guard stop-words (lowercase)
# ── Novel-Length Story: narrator mode word targets (V9.0) ─────────────
# Word budget matrix: narrator_mode x scene_weight -> max words.
# Used by narrator_postprocess.get_word_limit_for_scene_weight().
# "concise" matches the legacy SCENE_WORD_LIMITS with slight tuning.
# "novel" targets ~500-750 words for rich, layered prose.
# "epic" targets ~700-900 words for full cinematic treatment.
NARRATOR_MODE_WORD_TARGETS: dict[str, dict[str, int]] = {
    "concise": {
        "STANDARD": 230,
        "ELEVATED": 320,
        "CLIMAX": 430,
    },
    "novel": {
        "STANDARD": 500,
        "ELEVATED": 600,
        "CLIMAX": 750,
    },
    "epic": {
        "STANDARD": 700,
        "ELEVATED": 800,
        "CLIMAX": 900,
    },
}
VALID_NARRATOR_MODES: tuple[str, ...] = ("concise", "novel", "epic")
DEFAULT_NARRATOR_MODE = "concise"

# ── V10.0 Narrative Intelligence ─────────────────────────────────────

# Feature 8: Narrative rhythm hints — prose style guidance based on scene context.
# Maps composite keys to rhythm directives injected into the Director prompt.
NARRATIVE_RHYTHM_HINTS: dict[str, str] = {
    "combat_high": "Staccato. Short sentences. Fragments when impactful. Paragraphs get shorter as tension rises.",
    "combat_low": "Measured tension. Mix short action beats with brief pauses. Build momentum.",
    "dialogue_high": "Minimal prose between exchanges. Let voices carry the scene. Sharp, loaded silences.",
    "dialogue_low": "Conversational flow. Allow breathing room. Body language fills the gaps.",
    "exploration": "Languid. Sensory details. Let the world breathe. Longer sentences that unfold.",
    "revelation": "Let one sentence stand alone. Surround with silence. The weight of what's said needs space.",
    "emotional": "Internal texture. The character's body reacts before their mind catches up. Visceral detail.",
    "climax": "Everything tightens. Short paragraphs. Each sentence a decision. No wasted words.",
}


def get_rhythm_hint(action_class: str, tension_level: str, scene_weight: str) -> str:
    """Derive rhythm hint from scene context."""
    if scene_weight == "CLIMAX":
        return NARRATIVE_RHYTHM_HINTS["climax"]
    action_map = {
        "PHYSICAL_ACTION": "combat",
        "DIALOGUE_WITH_ACTION": "combat",
        "DIALOGUE_ONLY": "dialogue",
    }
    base_key = action_map.get(action_class, "exploration")
    intensity = "high" if tension_level in ("ESCALATING", "PEAK") else "low"
    return NARRATIVE_RHYTHM_HINTS.get(f"{base_key}_{intensity}", NARRATIVE_RHYTHM_HINTS["exploration"])


# Feature 2: Dramatic irony — max NPC-unaware hints injected into Director.
DRAMATIC_IRONY_MAX_HINTS = 3

# Feature 7: Creative deviation — similarity threshold for detecting player creativity.
CREATIVE_DEVIATION_SIMILARITY_THRESHOLD = 0.4

# Feature 4: Player behavioral profiling
PLAYER_PROFILE_INTERVAL = 10                  # Analyze every N turns
PLAYER_PROFILE_MIN_TURNS = 10                 # Don't profile until enough data
PLAYER_PROFILE_HISTORY_MAX = 100              # Max choice entries tracked
PLAYER_BOREDOM_REPETITION_THRESHOLD = 0.7     # Same tone >70% of last 10 → boredom
PLAYER_BOREDOM_INPUT_LENGTH_DECLINE = 0.5     # Avg input length dropped >50% → boredom

# Feature 1: Information Economy / Revelation timing
REVELATION_EVAL_INTERVAL = 5                  # Evaluate revelation queue every N turns
REVELATION_QUEUE_MAX = 10                     # Max queued revelations
REVELATION_EXPIRY_TURNS = 40                  # Expire if undelivered after N turns
REVELATION_URGENCY_TURNS = 15                 # Boost score for aging revelations
REVELATION_DIRECTOR_MAX = 3                   # Max revelations shown to Director per turn

# Feature 3: Callback Crystallizer
CALLBACK_CRYSTALLIZE_INTERVAL = 10            # Crystallize every N turns
CALLBACK_SEEDS_MAX = 15                       # Max stored callback seeds
CALLBACK_MAX_USES = 2                         # Max times a callback can echo
CALLBACK_DIRECTOR_MAX = 2                     # Max callbacks shown to Director per turn

# Feature 5: Foreshadowing hooks
FORESHADOW_MAX_HINTS = 2                      # Max foreshadowing hints per turn

# Feature 6: Companion wound stages
COMPANION_WOUND_STAGES = ("surface", "deep", "core")

# Feature 10: Arc mood profiles — tonal guidance by arc stage and campaign mood
ARC_MOOD_PROFILES: dict[str, dict[str, str]] = {
    "heroic": {
        "SETUP": "Wonder and discovery. The world is vast and full of possibility.",
        "RISING": "Growing stakes, forging alliances. Hope tested but enduring.",
        "CLIMAX": "Sacrifice and triumph. The hero stands at the threshold.",
        "RESOLUTION": "Peace earned. The world is changed, and so is the hero.",
    },
    "noir": {
        "SETUP": "Cynicism and mystery. Nothing is what it seems. Trust is currency.",
        "RISING": "Paranoia and betrayal. Every ally has an angle. Shadows deepen.",
        "CLIMAX": "Desperate truth. The cost of knowing is paid in full.",
        "RESOLUTION": "Pyrrhic victory. The case is closed but the scars remain.",
    },
    "tragic": {
        "SETUP": "Hope and ambition. The protagonist reaches for something greater.",
        "RISING": "Hubris and warnings ignored. The cracks are showing.",
        "CLIMAX": "The fall. Consequences of pride or blind faith crash down.",
        "RESOLUTION": "Acceptance or defiance. Not every story has a happy ending.",
    },
    "kishotenketsu": {
        "SETUP": "Introduction. Establish the world and its rhythms without conflict.",
        "RISING": "Development. Deepen understanding. Layer complexity without escalation.",
        "CLIMAX": "The twist. Something unexpected reframes everything — not through conflict but revelation.",
        "RESOLUTION": "Harmony. A new understanding integrates the twist into a richer whole.",
    },
    "mystery": {
        "SETUP": "The question. Something doesn't add up. Curiosity is the hook.",
        "RISING": "The trail. Each clue opens two doors. Red herrings and genuine leads intertwine.",
        "CLIMAX": "The reveal. All pieces click — or the detective becomes the suspect.",
        "RESOLUTION": "The reckoning. Truth has consequences. Some mysteries are better left buried.",
    },
}
DEFAULT_ARC_MOOD_PROFILE = "heroic"

# Feature 9: Thematic resonance — keywords for detecting themes from decisions
THEME_REINFORCEMENT_KEYWORDS: dict[str, list[str]] = {
    "cost_of_loyalty": ["loyal", "betray", "trust", "faith", "allegiance", "devoted"],
    "power_corrupts": ["power", "corrupt", "control", "dominate", "authority", "tyrant"],
    "redemption": ["redeem", "forgive", "atone", "second chance", "reform", "save"],
    "sacrifice": ["sacrifice", "gave up", "cost", "price", "lost", "surrendered"],
    "identity": ["who am i", "identity", "mask", "pretend", "true self", "disguise"],
    "justice_vs_mercy": ["justice", "mercy", "punish", "spare", "revenge", "forgive"],
    "survival": ["survive", "desperate", "hunger", "scarcity", "flee", "escape"],
    "forbidden_knowledge": ["secret", "forbidden", "hidden", "ancient", "taboo", "dark"],
}

DIRECTOR_ENTITY_STOP_WORDS = frozenset({
    "the", "a", "an", "say", "ask", "look", "go", "investigate", "talk", "take", "try",
    "press", "move", "check", "scan", "gather", "intel", "about", "with", "toward",
    "your", "my", "i", "you", "me", "we", "our", "what", "where", "who", "how",
    "can", "could", "would", "should", "will", "do", "it", "is", "are", "this",
    "that", "for", "from", "into", "around", "through", "on", "in", "at", "to",
    "of", "and", "or", "but", "up", "out", "off", "something", "someone", "here",
    "there", "area", "place", "situation", "objective", "goal", "action", "forward",
    "force", "details", "clues", "question", "more", "else", "risky", "carefully",
    "decisive", "firmly", "subtly", "quietly", "openly", "nearby", "local", "current",
    "new", "old", "safe", "dangerous", "approach", "confront", "explore", "commit",
    "social", "hi", "hello", "advance",
})
