"""LangGraph state packet: Pydantic models for the hot state flowing between nodes.

All models are JSON-serializable and constructible without DB calls.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.models.events import Event


# --- UI / intent ---

# Router route and action_class (security: only DIALOGUE_ONLY skips Mechanic; META skips Mechanic and time)
ROUTER_ROUTE_TALK = "TALK"
ROUTER_ROUTE_MECHANIC = "MECHANIC"
ROUTER_ROUTE_META = "META"
ROUTER_ACTION_CLASS_DIALOGUE_ONLY = "DIALOGUE_ONLY"
ROUTER_ACTION_CLASS_DIALOGUE_WITH_ACTION = "DIALOGUE_WITH_ACTION"
ROUTER_ACTION_CLASS_PHYSICAL_ACTION = "PHYSICAL_ACTION"
ROUTER_ACTION_CLASS_META = "META"


class RouterOutput(BaseModel):
    """Router output schema: intent classification and security routing."""
    intent_text: str = ""  # normalized or original user input
    route: str = ROUTER_ROUTE_MECHANIC  # TALK | MECHANIC | META
    action_class: str = ROUTER_ACTION_CLASS_PHYSICAL_ACTION  # DIALOGUE_ONLY | DIALOGUE_WITH_ACTION | PHYSICAL_ACTION | META
    requires_resolution: bool = True  # true if a check/outcome is needed (must not skip Mechanic)
    confidence: float = 0.0  # 0–1, optional
    rationale_short: str = ""  # optional, for debug


# Suggested action category and strategy (narrative UX)
ACTION_CATEGORY_SOCIAL = "SOCIAL"
ACTION_CATEGORY_EXPLORE = "EXPLORE"
ACTION_CATEGORY_COMMIT = "COMMIT"
ACTION_RISK_SAFE = "SAFE"
ACTION_RISK_RISKY = "RISKY"
ACTION_RISK_DANGEROUS = "DANGEROUS"
STRATEGY_TAG_OPTIMAL = "OPTIMAL"
STRATEGY_TAG_ALTERNATIVE = "ALTERNATIVE"

# KOTOR/ME dialogue wheel tone tags (map: SOCIAL->PARAGON, EXPLORE->INVESTIGATE, COMMIT->RENEGADE)
TONE_TAG_PARAGON = "PARAGON"
TONE_TAG_RENEGADE = "RENEGADE"
TONE_TAG_INVESTIGATE = "INVESTIGATE"
TONE_TAG_NEUTRAL = "NEUTRAL"
TONE_TAG_BY_CATEGORY = {
    ACTION_CATEGORY_SOCIAL: TONE_TAG_PARAGON,
    ACTION_CATEGORY_EXPLORE: TONE_TAG_INVESTIGATE,
    ACTION_CATEGORY_COMMIT: TONE_TAG_RENEGADE,
}


class ActionSuggestion(BaseModel):
    """Short UI label and intent text; KOTOR/ME dialogue wheel style (PARAGON/INVESTIGATE/RENEGADE)."""
    label: str  # short UI label, e.g. "Intimidate the guard"
    intent_text: str  # what gets sent as user_input if clicked
    category: str = ACTION_CATEGORY_EXPLORE  # SOCIAL | EXPLORE | COMMIT (distinct per turn)
    risk_level: str = ACTION_RISK_SAFE  # SAFE | RISKY | DANGEROUS
    strategy_tag: str = STRATEGY_TAG_OPTIMAL  # OPTIMAL | ALTERNATIVE (at least one ALTERNATIVE per turn)
    tone_tag: str = TONE_TAG_NEUTRAL  # PARAGON | RENEGADE | INVESTIGATE | NEUTRAL
    intent_style: str = ""  # short tag: "calm", "firm", "probing", "empathetic", etc.
    consequence_hint: str = ""  # 1 short clause: "may gain trust", "may escalate", "learn more"
    companion_reactions: dict[str, int] = Field(default_factory=dict)  # V2.9: {companion_id: affinity_delta}
    risk_factors: list[str] = Field(default_factory=list)  # V2.9: Why is this risky? ["Outnumbered 3-to-1", "No cover"]
    meaning_tag: str = ""  # V2.18: reveal_values|probe_belief|challenge_premise|seek_history|set_boundary|pragmatic|deflect


# --- Character ---


class CharacterSheet(BaseModel):
    """Lightweight character summary for the state packet (not authoritative)."""
    character_id: str
    name: str
    stats: dict[str, int] = Field(default_factory=dict)
    hp_current: int = 0
    location_id: str | None = None
    planet_id: str | None = None  # e.g., "Tatooine", "Coruscant"
    credits: int | None = None
    inventory: list[dict] = Field(default_factory=list)  # lightweight summary for UI
    psych_profile: dict = Field(default_factory=dict)  # V2.5: current_mood, stress_level, active_trauma
    background: str | None = None  # V2.6: POV identity — persisted from BiographerAgent
    cyoa_answers: dict | None = None  # V2.7: CYOA character creation answers (motivation, origin, inciting_incident, edge)
    gender: str | None = None  # V2.8: "male" or "female" — drives pronoun usage in narration


# --- Mechanic output (strict contract) ---


class MechanicCheck(BaseModel):
    """Single check: dc, skill, roll, result (optional, for debug)."""
    dc: int | None = None
    skill: str | None = None
    roll: int | None = None
    result: str | None = None  # e.g. "success" / "failure"


class MechanicOutput(BaseModel):
    """Strict validated output from the mechanic node. Fail-safe no-op uses invalid_action=True.
    KOTOR/ME consequence plumbing: tone_tag, alignment_delta, faction_reputation_delta, companion deltas."""
    action_type: str  # e.g. 'TRAVEL', 'ATTACK', 'TALK', 'INTERACT'
    time_cost_minutes: int = Field(default=0, ge=0, le=1440)  # 0–1440 (one day max)
    events: list[Event] = Field(default_factory=list)  # resolved_events: type + payload
    outcome_summary: str = ""  # short string for debug
    dc: int | None = None
    roll: int | None = None
    success: bool | None = None
    narrative_facts: list[str] = Field(default_factory=list)
    checks: list[MechanicCheck] = Field(default_factory=list)  # optional list of checks
    flags: dict[str, bool] = Field(default_factory=dict)  # optional: violence, stealth, etc.
    invalid_action: bool = False  # true = fail-safe no-op; narrator should ask for rephrase
    rephrase_message: str | None = None  # user-facing message when invalid_action (e.g. "That action is unclear—try rephrasing.")
    # KOTOR/ME choice impact (optional; parser defaults/clamps when absent)
    tone_tag: str = TONE_TAG_NEUTRAL  # PARAGON | RENEGADE | INVESTIGATE | NEUTRAL
    alignment_delta: dict[str, int] = Field(default_factory=dict)  # light_dark, paragon_renegade
    faction_reputation_delta: dict[str, int] = Field(default_factory=dict)  # faction_id -> delta
    companion_affinity_delta: dict[str, int] = Field(default_factory=dict)  # companion_id -> delta
    companion_reaction_reason: dict[str, str] = Field(default_factory=dict)  # companion_id -> short reason (<=8 words)
    # 3.3: Contextual advantage/disadvantage modifiers applied to roll
    modifiers: list[dict] = Field(default_factory=list)  # [{"source": str, "value": int}]
    # V2.5: stress delta for psych profile (computed by mechanic)
    stress_delta: int = 0
    # V2.5: critical outcome flag (CRITICAL_FAILURE | CRITICAL_SUCCESS | None)
    critical_outcome: str | None = None
    # V2.5: True when event demands immediate world-sim response
    world_reaction_needed: bool = False


# --- Game state packet ---


class GameState(BaseModel):
    """Packet passed between LangGraph nodes. Fully JSON-serializable."""

    # Persistent / core
    campaign_id: str
    player_id: str
    turn_number: int = 0
    current_location: str | None = None
    current_planet: str | None = None  # e.g., "Tatooine", "Coruscant"
    player: CharacterSheet | None = None
    campaign: dict | None = None  # Clock-tick: id, title, time_period, world_time_minutes, ...

    # Post-action world time (t0 + time_cost_minutes); set by WorldSim node, consumed by Commit
    pending_world_time_minutes: int | None = None
    # World-sim output contract (pure; persisted only in CommitNode)
    world_sim_ran: bool = False
    world_sim_rumors: list[dict] = Field(default_factory=list)  # Event-like dicts; committed by CommitNode
    world_sim_factions_update: list[dict] | None = None  # Updated active_factions; persisted in CommitNode
    world_sim_debug: str | None = None  # Optional diagnostics (e.g. elapsed_time_summary)
    # World-sim events to persist (legacy alias; committed by CommitNode)
    world_sim_events: list[dict] = Field(default_factory=list)
    # New rumors from WorldSimNode (for Director to use in prompt)
    new_rumors: list[str] = Field(default_factory=list)
    # Last N is_public_rumor events (for Narrator to reference subtly)
    active_rumors: list[str] = Field(default_factory=list)

    # V2.10: Starship ownership (persistent; loaded from world_state_json)
    player_starship: dict | None = None  # {"ship_type": "ship-reb-yt1300", "name": "...", ...} or None if no ship

    # V2.12: NPCs the player has been introduced to (persistent; loaded from world_state_json)
    known_npcs: list[str] = Field(default_factory=list)  # NPC names the player has met/seen

    # Memory (kept across turns)
    history: list[str] = Field(default_factory=list)  # last ~10 turn summaries
    last_user_inputs: list[str] = Field(default_factory=list)  # last ~10 raw inputs
    era_summaries: list[str] = Field(default_factory=list)  # compressed summaries of old turn ranges
    recent_narrative: list[str] = Field(default_factory=list)  # last 2-3 turns of actual narrated text

    # Transient (cleared every turn)
    user_input: str = ""
    intent: str | None = None  # router: "TALK" (skip mechanic) | "ACTION" (go to mechanic)
    route: str | None = None  # router: TALK | MECHANIC
    action_class: str | None = None  # router: DIALOGUE_ONLY | DIALOGUE_WITH_ACTION | PHYSICAL_ACTION | META
    router_output: RouterOutput | None = None  # full router result (for debug)
    debug_seed: int | None = None  # optional: seed for mechanic RNG (MECHANIC_SEED env override)
    mechanic_result: MechanicOutput | None = None
    director_instructions: str | None = None
    suggested_actions: list[ActionSuggestion] = Field(default_factory=list)
    embedded_suggestions: list[dict] | None = None  # Extracted from narrative text (if present)
    lore_context: str | None = None
    style_context: str | None = None
    present_npcs: list[dict] = Field(default_factory=list)
    final_text: str | None = None
    lore_citations: list[dict] = Field(default_factory=list)  # NarrationCitation-like dicts for transcript
    context_stats: dict | None = None  # Dev-only: token budgeting stats from ContextBudget
    warnings: list[str] = Field(default_factory=list)  # Turn warnings (LLM/RAG fallbacks)
    # V2.5: Arc planner output (deterministic arc guidance for Director)
    arc_guidance: dict | None = None
    # V2.5: Narrative validator output
    validation_notes: list[str] = Field(default_factory=list)

    # V2.17: DialogueTurn contract (transient — rebuilt each turn)
    scene_frame: dict | None = None  # SceneFrame snapshot (set by scene_frame node)
    npc_utterance: dict | None = None  # NPCUtterance (set by narrator node)
    player_responses: list[dict] = Field(default_factory=list)  # PlayerResponse list (set by suggestion_refiner)
    dialogue_turn: dict | None = None  # Assembled DialogueTurn (set by commit node)

    def cleared_for_next_turn(self) -> GameState:
        """Return a copy with transient fields reset; persistent and memory fields kept."""
        return self.model_copy(
            update={
                "user_input": "",
                "intent": None,
                "route": None,
                "action_class": None,
                "router_output": None,
                "mechanic_result": None,
                "director_instructions": None,
                "suggested_actions": [],
                "embedded_suggestions": None,
                "lore_context": None,
                "style_context": None,
                "present_npcs": [],
                "final_text": None,
                "lore_citations": [],
                "context_stats": None,
                "warnings": [],
                # WorldSim-related fields (transient, reset each turn)
                "world_sim_ran": False,
                "world_sim_rumors": [],
                "world_sim_factions_update": None,
                "world_sim_events": [],
                "new_rumors": [],
                "active_rumors": [],
                "world_sim_debug": None,
                "pending_world_time_minutes": None,
                # V2.5 transient fields
                "arc_guidance": None,
                "validation_notes": [],
                # V2.17 DialogueTurn fields
                "scene_frame": None,
                "npc_utterance": None,
                "player_responses": [],
                "dialogue_turn": None,
            }
        )
