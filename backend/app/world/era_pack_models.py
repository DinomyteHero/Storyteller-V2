"""Pydantic models for Era Packs (Bible data).

V2 adds gameplay-grade metadata for fully dynamic adventures:
- Location affordances (services, access points, security, encounters)
- NPC templates with spawn rules + levers/authority/knowledge
- New authored pack files: quests/events/rumors/meters (and optional facts)
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ALLOWED_SCENE_TYPES: set[str] = {
    "dialogue",
    "stealth",
    "combat",
    "travel",
    "investigation",
    # Extended scene types (V2.20+)
    "puzzle",
    "philosophical_dialogue",
    "meditation",
    "tech_investigation",
    "survival",
    "exploration",
    "training",
}
ALLOWED_PATROL_INTENSITY: set[str] = {"low", "medium", "high", "constant", "none"}
ALLOWED_SERVICES: set[str] = {
    "briefing_room",
    "medbay",
    "arms_dealer",
    "slicer",
    "transport",
    "bounty_board",
    "safehouse",
    # Extended services (V2.20+)
    "market",
    "cantina",
}
_CORE_BYPASS_METHODS: set[str] = {
    # Physical
    "violence",
    "sneak",
    "stealth",  # alias for sneak
    "climb",
    "navigate",
    # Social
    "bribe",
    "charm",
    "intimidate",
    "deception",
    "credential",
    # Tech
    "hack",
    "slice",
    "disable",
    # Generic special
    "logic_puzzle",
}


def _load_setting_bypass_methods() -> set[str]:
    """Load setting-specific bypass methods from SETTING_BYPASS_METHODS env var.

    Default: Star Wars-specific methods (force, force_dark, sith_amulet).
    Other settings can override: e.g. SETTING_BYPASS_METHODS="magic,potion,enchantment"
    """
    import os
    env_val = os.environ.get("SETTING_BYPASS_METHODS", "").strip()
    if env_val:
        return {m.strip().lower() for m in env_val.split(",") if m.strip()}
    # Default: Star Wars methods
    return {"force", "force_dark", "sith_amulet"}


ALLOWED_BYPASS_METHODS: set[str] = _CORE_BYPASS_METHODS | _load_setting_bypass_methods()
LeverRating = Literal["low", "medium", "high", "false"]
RumorScope = Literal["global", "location"]
RumorCredibility = Literal["rumor", "likely", "confirmed"]


class NpcMatchRules(BaseModel):
    """Alias matching rules for deterministic NPC tagging."""
    model_config = ConfigDict(extra="forbid")

    min_tokens: int = 1
    require_surname: bool = False
    case_sensitive: bool = False
    allow_single_token: bool = False


class EraFaction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    tags: List[str] = Field(default_factory=list)
    home_locations: List[str] = Field(default_factory=list)
    goals: List[str] = Field(default_factory=list)
    hostility_matrix: Dict[str, int | str] | None = None
    # Flexible extension point: store additional structured metadata without changing the schema.
    metadata: Dict[str, object] = Field(default_factory=dict)


class EraLocationSecurity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    controlling_faction: str | None = None
    security_level: int = 50  # 0..100
    patrol_intensity: str = "medium"  # low|medium|high
    inspection_chance: str = "medium"  # low|medium|high

    @field_validator("security_level")
    @classmethod
    def _bounds_security_level(cls, v: int) -> int:
        if v < 0 or v > 100:
            raise ValueError("security.security_level must be within 0..100")
        return v

    @field_validator("patrol_intensity", "inspection_chance")
    @classmethod
    def _validate_intensity(cls, v: str) -> str:
        low = (v or "").strip().lower()
        if low not in ALLOWED_PATROL_INTENSITY:
            raise ValueError(f"security intensity must be one of: {sorted(ALLOWED_PATROL_INTENSITY)}")
        return low


class EraAccessPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: str = "door"
    visibility: str = "public"  # public|restricted|hidden|secret (free-form but useful)
    bypass_methods: List[str] = Field(default_factory=list)

    @field_validator("bypass_methods")
    @classmethod
    def _validate_bypass_methods(cls, v: List[str]) -> List[str]:
        out: list[str] = []
        for m in v or []:
            token = str(m).strip().lower()
            if not token:
                continue
            if token not in ALLOWED_BYPASS_METHODS:
                raise ValueError(f"Unknown bypass_methods token: {token}")
            out.append(token)
        return out


class EraEncounterEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: str
    weight: int = 1
    conditions: Any | None = None

    @field_validator("weight")
    @classmethod
    def _validate_weight(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("encounter_table.weight must be > 0")
        return v


class EraTravelLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to_location_id: str
    method: str = "travel"
    risk: str | int | None = None
    cost: int | None = None


class EraLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    tags: List[str] = Field(default_factory=list)
    region: str | None = None
    controlling_factions: List[str] = Field(default_factory=list)
    description: str | None = None
    threat_level: str | None = None  # low, moderate, high, extreme
    planet: str | None = None  # e.g., "Tatooine", "Coruscant", "Hoth"
    # --- V2 gameplay metadata ---
    parent_id: str | None = None
    scene_types: List[str] = Field(default_factory=list)  # dialogue|stealth|combat|travel|investigation
    security: EraLocationSecurity = Field(default_factory=EraLocationSecurity)
    services: List[str] = Field(default_factory=list)
    access_points: List[EraAccessPoint] = Field(default_factory=list)
    encounter_table: List[EraEncounterEntry] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    travel_links: List[EraTravelLink] = Field(default_factory=list)
    # Flexible extension point: e.g., coordinates, population, economy, points_of_interest.
    metadata: Dict[str, object] = Field(default_factory=dict)

    @field_validator("travel_links", mode="before")
    @classmethod
    def _normalize_travel_links(cls, v: Any) -> List[dict]:
        """Convert string location IDs to EraTravelLink dicts for YAML compatibility."""
        if not isinstance(v, list):
            return []
        result = []
        for item in v:
            if isinstance(item, str):
                # Convert "loc-foo" → {"to_location_id": "loc-foo"}
                result.append({"to_location_id": item})
            elif isinstance(item, dict):
                result.append(item)
        return result

    @field_validator("controlling_factions", mode="before")
    @classmethod
    def _filter_null_factions(cls, v: Any) -> List[str]:
        """Filter out None/null values from controlling_factions for YAML compatibility."""
        if not isinstance(v, list):
            return []
        return [str(x) for x in v if x is not None]

    @field_validator("scene_types")
    @classmethod
    def _validate_scene_types(cls, v: List[str]) -> List[str]:
        out: list[str] = []
        seen: set[str] = set()
        for t in v or []:
            low = str(t).strip().lower()
            if not low:
                continue
            if low not in ALLOWED_SCENE_TYPES:
                raise ValueError(f"Unknown scene_types entry: {low}")
            if low in seen:
                continue
            seen.add(low)
            out.append(low)
        return out

    @field_validator("services")
    @classmethod
    def _validate_services(cls, v: List[str]) -> List[str]:
        out: list[str] = []
        seen: set[str] = set()
        for s in v or []:
            token = str(s).strip()
            if not token:
                continue
            if token not in ALLOWED_SERVICES:
                raise ValueError(f"Unknown service: {token}")
            if token in seen:
                continue
            seen.add(token)
            out.append(token)
        return out

    @model_validator(mode="after")
    def _validate_encounter_weights(self) -> EraLocation:
        if self.encounter_table:
            total = sum(int(e.weight) for e in self.encounter_table)
            if total <= 0:
                raise ValueError(f"encounter_table weights must sum to > 0 for location {self.id}")
        # Ensure access_points ids are unique within a location
        ap_ids = [ap.id for ap in self.access_points or [] if ap and ap.id]
        if len(ap_ids) != len(set(ap_ids)):
            raise ValueError(f"Duplicate access_point id in location {self.id}")
        return self

    def affordances(self) -> dict[str, Any]:
        """Gameplay-facing affordances derived from location metadata."""
        return {
            "scene_types": list(self.scene_types or []),
            "services": list(self.services or []),
            "access_points": [ap.model_dump(mode="json") for ap in (self.access_points or [])],
            "security": self.security.model_dump(mode="json") if self.security else {},
            "keywords": list(self.keywords or []),
        }


class NpcSpawnRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_tags_any: List[str] = Field(default_factory=list)
    location_types_any: List[str] = Field(default_factory=list)
    min_alert: int = 0
    max_alert: int = 100
    conditions: Any | None = None

    @field_validator("min_alert", "max_alert")
    @classmethod
    def _bounds_alert(cls, v: int) -> int:
        if v < 0 or v > 100:
            raise ValueError("spawn.min_alert/max_alert must be within 0..100")
        return v

    @model_validator(mode="after")
    def _validate_alert_range(self) -> NpcSpawnRules:
        if self.min_alert > self.max_alert:
            raise ValueError("spawn.min_alert must be <= spawn.max_alert")
        return self


class NpcLevers(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bribeable: LeverRating = "false"
    intimidatable: LeverRating = "false"
    charmable: LeverRating = "false"
    triggers: Any | None = None

    @field_validator("bribeable", "intimidatable", "charmable", mode="before")
    @classmethod
    def _normalize_lever_rating(cls, v: Any) -> str:
        """Convert Python bool to string 'false' for YAML compatibility."""
        if isinstance(v, bool):
            return "false" if not v else "medium"  # True → medium as sensible default
        return v


class NpcAuthority(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clearance_level: int = 0  # 0..5
    can_grant_access: List[str] = Field(default_factory=list)

    @field_validator("clearance_level")
    @classmethod
    def _bounds_clearance(cls, v: int) -> int:
        if v < 0 or v > 5:
            raise ValueError("authority.clearance_level must be within 0..5")
        return v


class NpcKnowledge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rumors: List[str] = Field(default_factory=list)
    quest_facts: List[str] = Field(default_factory=list)
    secrets: List[str] = Field(default_factory=list)


class NpcVoice(BaseModel):
    """V2 NPC voice metadata for deeper characterization."""
    model_config = ConfigDict(extra="forbid")

    belief: str  # Core belief (1 sentence)
    wound: str  # Formative wound (1 sentence)
    taboo: str  # Personal taboo (short phrase)
    rhetorical_style: str  # e.g., Socratic, blunt, poetic, coldly_practical
    tell: str  # Physical/verbal mannerism


class EraNpcEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    aliases: List[str] = Field(default_factory=list)
    banned_aliases: List[str] = Field(default_factory=list)
    match_rules: NpcMatchRules = Field(default_factory=NpcMatchRules)
    tags: List[str] = Field(default_factory=list)
    faction_id: str | None = None
    default_location_id: str | None = None
    home_locations: List[str] = Field(default_factory=list)
    role: str | None = None
    archetype: str | None = None
    traits: List[str] = Field(default_factory=list)
    motivation: str | None = None
    secret: str | None = None
    voice_tags: List[str] = Field(default_factory=list)
    species: str | None = None
    rarity: str = "common"  # common | rare | legendary
    # --- V2 gameplay metadata ---
    voice: NpcVoice | None = None
    spawn: NpcSpawnRules | None = None
    levers: NpcLevers = Field(default_factory=NpcLevers)
    authority: NpcAuthority = Field(default_factory=NpcAuthority)
    knowledge: NpcKnowledge = Field(default_factory=NpcKnowledge)
    metadata: Dict[str, object] = Field(default_factory=dict)


class EraNpcTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    role: str
    archetype: str | None = None
    traits: List[str] = Field(default_factory=list)
    motivations: List[str] = Field(default_factory=list)
    secrets: List[str] = Field(default_factory=list)
    voice_tags: List[str] = Field(default_factory=list)
    species: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    namebank: str | None = None
    # --- V2 gameplay metadata ---
    voice: NpcVoice | None = None
    spawn: NpcSpawnRules | None = None
    levers: NpcLevers = Field(default_factory=NpcLevers)
    authority: NpcAuthority = Field(default_factory=NpcAuthority)
    knowledge: NpcKnowledge = Field(default_factory=NpcKnowledge)
    metadata: Dict[str, object] = Field(default_factory=dict)


class EraNpcPack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anchors: List[EraNpcEntry] = Field(default_factory=list)
    rotating: List[EraNpcEntry] = Field(default_factory=list)
    templates: List[EraNpcTemplate] = Field(default_factory=list)


class BackgroundChoiceEffect(BaseModel):
    """Effects applied when a background question choice is selected."""
    model_config = ConfigDict(extra="allow")

    faction_hint: str | None = None
    location_hint: str | None = None
    thread_seed: str | None = None
    stat_bonus: Dict[str, int] = Field(default_factory=dict)


class BackgroundChoice(BaseModel):
    """A single choice within a background question."""
    model_config = ConfigDict(extra="forbid")

    label: str
    concept: str
    tone: str = "NEUTRAL"
    effects: BackgroundChoiceEffect = Field(default_factory=BackgroundChoiceEffect)


class BackgroundQuestion(BaseModel):
    """A question within a background's branching chain."""
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    subtitle: str = ""
    condition: str | None = None  # e.g., "loyalty.tone == PARAGON"
    choices: List[BackgroundChoice] = Field(default_factory=list)


class EraBackground(BaseModel):
    """A selectable character background within an era pack."""
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str = ""
    icon: str | None = None
    starting_stats: Dict[str, int] = Field(default_factory=dict)
    questions: List[BackgroundQuestion] = Field(default_factory=list)
    # V2.10: Optional starship assignment for backgrounds that grant a starting ship
    starting_starship: str | None = None
    # V2.10: Optional starting faction reputation modifiers
    starting_reputation: Dict[str, int] = Field(default_factory=dict)


class EraMetersBounds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min: int
    max: int
    default: int
    decay_per_tick: int | None = None

    @model_validator(mode="after")
    def _validate_bounds(self) -> EraMetersBounds:
        if self.min > self.max:
            raise ValueError("meters bounds require min <= max")
        if self.default < self.min or self.default > self.max:
            raise ValueError("meters default must be within [min,max]")
        return self


class EraMeters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reputation_by_faction: EraMetersBounds = Field(default_factory=lambda: EraMetersBounds(min=-100, max=100, default=0))
    heat_global: EraMetersBounds = Field(default_factory=lambda: EraMetersBounds(min=0, max=100, default=0, decay_per_tick=1))
    heat_by_location: EraMetersBounds = Field(default_factory=lambda: EraMetersBounds(min=0, max=100, default=0, decay_per_tick=2))
    control_shift: Dict[str, Any] = Field(default_factory=dict)


class EraRumor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    tags: List[str] = Field(default_factory=list)
    scope: RumorScope = "global"
    credibility: RumorCredibility = "rumor"


class EraQuestStage(BaseModel):
    model_config = ConfigDict(extra="allow")

    stage_id: str
    objective: str = ""
    objectives: Any | None = None
    branch_points: Any | None = None
    success_conditions: Any | None = None
    fail_conditions: Any | None = None
    on_enter_effects: Any | None = None
    on_exit_effects: Any | None = None


class EraQuest(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    description: str = ""
    entry_conditions: Any | None = None
    stages: List[EraQuestStage] = Field(default_factory=list)
    consequences: Any | None = None


class EraEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    type: str
    triggers: Any | None = None
    location_selector: Any | None = None
    effects: Any | None = None
    broadcast_rules: Any | None = None


class EraFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    subject: str
    predicate: str
    object: str
    confidence: float | None = None


class EraCompanionRecruitment(BaseModel):
    """How and where a companion is first met and recruited."""
    model_config = ConfigDict(extra="forbid")

    unlock_conditions: str = ""  # free-text: "complete quest X" or "reach affinity 20"
    first_meeting_location: str | None = None  # location_id
    first_scene_template: str | None = None  # optional template_id for intro scene


class EraCompanionVoice(BaseModel):
    """Deep voice characterisation (mirrors NpcVoice but companion-specific)."""
    model_config = ConfigDict(extra="forbid")

    belief: str = ""          # core belief (1 sentence)
    wound: str = ""           # formative wound (1 sentence)
    taboo: str = ""           # personal taboo (short phrase)
    rhetorical_style: str = ""  # Socratic, blunt, poetic, coldly_practical, etc.
    tell: str = ""            # physical/verbal mannerism


class EraCompanionInfluence(BaseModel):
    """Influence tuning for a companion."""
    model_config = ConfigDict(extra="forbid")

    starts_at: int = 0
    min: int = -100
    max: int = 100
    triggers: List[Dict[str, Any]] = Field(default_factory=list)  # optional: [{intent: "threaten", delta: -5}, ...]


class EraCompanionBanter(BaseModel):
    """Banter tuning for a companion."""
    model_config = ConfigDict(extra="forbid")

    frequency: str = "normal"  # low | normal | high
    style: str = "warm"  # warm | snarky | stoic | etc. (matches BANTER_POOL keys)
    triggers: List[str] = Field(default_factory=list)  # optional topic triggers: ["jedi", "empire"]


class EraCompanion(BaseModel):
    """Era-pack companion definition: character + mechanics + recruitment."""
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    species: str = "Human"
    gender: str | None = None
    archetype: str | None = None
    faction_id: str | None = None
    role_in_party: str = "companion"  # companion | specialist | mentor | rival

    # Voice and personality (replaces top-level voice_tags/motivation/speech_quirk for era-pack companions)
    voice_tags: List[str] = Field(default_factory=list)
    motivation: str | None = None
    speech_quirk: str | None = None
    voice: EraCompanionVoice = Field(default_factory=EraCompanionVoice)

    # Trait axes (for companion reactions: idealist_pragmatic, merciful_ruthless, lawful_rebellious)
    traits: Dict[str, int] = Field(default_factory=dict)
    default_affinity: int = 0

    # Recruitment
    recruitment: EraCompanionRecruitment = Field(default_factory=EraCompanionRecruitment)

    # Mechanics
    tags: List[str] = Field(default_factory=list)
    enables_affordances: List[str] = Field(default_factory=list)  # e.g. ["slice_terminal", "medic_heal"]
    blocks_affordances: List[str] = Field(default_factory=list)  # e.g. ["imperial_salute"]

    # Influence tuning
    influence: EraCompanionInfluence = Field(default_factory=EraCompanionInfluence)

    # Banter tuning
    banter: EraCompanionBanter = Field(default_factory=EraCompanionBanter)

    # Personal quest (optional)
    personal_quest_id: str | None = None

    # Flexible extension
    metadata: Dict[str, object] = Field(default_factory=dict)


class SettingRules(BaseModel):
    """Universe-specific text carried through the pipeline to prevent cross-setting contamination.

    Defaults are Star Wars Legends — zero behavior change for existing setup.
    Other settings (Harry Potter, LOTR, etc.) override these fields via their EraPack.
    """
    model_config = ConfigDict(extra="forbid")

    setting_name: str = "Star Wars Legends"
    setting_genre: str = "science fantasy"
    # Agent prompt role strings
    biographer_role: str = "a biographer for a Star Wars narrative RPG"
    architect_role: str = "the World Architect for a Star Wars narrative RPG"
    director_role: str = "the Director for an interactive Star Wars story engine"
    suggestion_style: str = "a Star Wars KOTOR-style game"
    # Setting-specific data for prompts
    common_species: List[str] = Field(
        default=["Twi'lek", "Rodian", "Wookiee", "Zabrak", "Bothan", "Chiss", "Human"],
    )
    example_factions: List[str] = Field(
        default=["Rebellion", "Empire", "criminal syndicates"],
    )
    historical_lore_label: str = "established Star Wars Legends lore"
    concept_location_map: Dict[str, List[str]] = Field(default_factory=dict)
    location_display_names: Dict[str, str] = Field(default_factory=dict)
    bypass_methods: List[str] = Field(default=["force", "force_dark", "sith_amulet"])
    fallback_background: str = "A traveler in a vast galaxy."


class EraPack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    era_id: str
    schema_version: int | None = None
    file_index: Dict[str, str] = Field(default_factory=dict)
    start_location_pool: List[str] = Field(default_factory=list)
    global_event_templates: List[str] = Field(default_factory=list)
    travel_graph: List[EraTravelLink] = Field(default_factory=list)
    default_scene_pacing: Dict[str, Any] = Field(default_factory=dict)

    factions: List[EraFaction] = Field(default_factory=list)
    locations: List[EraLocation] = Field(default_factory=list)
    npcs: EraNpcPack = Field(default_factory=EraNpcPack)
    namebanks: Dict[str, List[str]] = Field(default_factory=dict)
    backgrounds: List[EraBackground] = Field(default_factory=list)
    quests: List[EraQuest] = Field(default_factory=list)
    events: List[EraEvent] = Field(default_factory=list)
    rumors: List[EraRumor] = Field(default_factory=list)
    meters: EraMeters | None = None
    facts: List[EraFact] = Field(default_factory=list)
    companions: List[EraCompanion] = Field(default_factory=list)
    faction_relationships: Dict[str, Any] | None = None
    style_ref: str | None = None
    # V3.1: Per-pack background figures for universe modularity
    background_figures: Dict[str, List[str]] = Field(default_factory=dict)
    # V3.1: Setting name for prompts (e.g. "Star Wars Legends", "Harry Potter")
    setting_name: str | None = None
    # V3.2: Universe rules — all setting-specific text for agent prompts
    setting_rules: SettingRules = Field(default_factory=SettingRules)
    metadata: Dict[str, object] = Field(default_factory=dict)

    def all_npcs(self) -> List[EraNpcEntry]:
        """Return anchors + rotating as a single list."""
        return list(self.npcs.anchors) + list(self.npcs.rotating)

    def location_by_id(self, location_id: str) -> EraLocation | None:
        """Find a location by id."""
        for loc in self.locations:
            if loc.id == location_id:
                return loc
        return None

    def companion_by_id(self, comp_id: str) -> EraCompanion | None:
        """Find a companion by id."""
        for comp in self.companions or []:
            if comp.id == comp_id:
                return comp
        return None

    @model_validator(mode="after")
    def _validate_references(self) -> EraPack:
        # Allow lenient validation for WIP era packs via config flag
        import logging
        from shared.config import ERA_PACK_LENIENT_VALIDATION
        lenient_mode = ERA_PACK_LENIENT_VALIDATION
        logger = logging.getLogger(__name__)

        def _check_ref(condition: bool, error_msg: str) -> None:
            """Raise ValueError if condition is False (strict) or log warning (lenient)."""
            if not condition:
                if lenient_mode:
                    logger.warning(f"Era pack validation (lenient mode): {error_msg}")
                else:
                    raise ValueError(error_msg)

        location_ids = {l.id for l in self.locations}
        faction_ids = {f.id for f in self.factions}
        template_ids = {t.id for t in (self.npcs.templates or [])}
        rumor_ids = {r.id for r in (self.rumors or [])}
        quest_ids = {q.id for q in (self.quests or [])}
        quest_stages: dict[str, set[str]] = {q.id: {s.stage_id for s in (q.stages or [])} for q in (self.quests or [])}
        fact_ids = {f.id for f in (self.facts or [])}

        # Location parent/travel refs
        for loc in self.locations:
            if loc.parent_id and loc.parent_id not in location_ids:
                _check_ref(False, f"locations[{loc.id}].parent_id references missing location id: {loc.parent_id}")
            for link in loc.travel_links or []:
                if link.to_location_id not in location_ids:
                    # Log warning but don't fail validation (allows WIP era packs to load)
                    import logging
                    logging.getLogger(__name__).warning(
                        f"locations[{loc.id}].travel_links references missing location id: {link.to_location_id}"
                    )

            # Encounter templates must exist (warn if missing but allow WIP packs)
            for e in loc.encounter_table or []:
                if e.template_id not in template_ids:
                    import logging
                    logging.getLogger(__name__).warning(
                        f"locations[{loc.id}].encounter_table references missing npc template id: {e.template_id}"
                    )

        # Era-level travel graph refs
        for link in self.travel_graph or []:
            if link.to_location_id not in location_ids:
                _check_ref(False, f"travel_graph references missing location id: {link.to_location_id}")

        # Start pool must exist
        for lid in self.start_location_pool or []:
            if lid not in location_ids:
                import logging
                logging.getLogger(__name__).warning(
                    f"start_location_pool references missing location id: {lid}"
                )

        # Faction home locations must exist (warn but allow WIP packs)
        for f in self.factions or []:
            for hl in f.home_locations or []:
                if hl not in location_ids:
                    import logging
                    logging.getLogger(__name__).warning(
                        f"faction[{f.id}].home_locations references missing location id: {hl}"
                    )

        # NPC refs: factions / locations / knowledge
        for npc in self.all_npcs():
            if npc.faction_id:
                _check_ref(npc.faction_id in faction_ids, f"npc[{npc.id}].faction_id references missing faction id: {npc.faction_id}")
            if npc.default_location_id:
                _check_ref(npc.default_location_id in location_ids, f"npc[{npc.id}].default_location_id references missing location id: {npc.default_location_id}")
            for hl in npc.home_locations or []:
                _check_ref(hl in location_ids, f"npc[{npc.id}].home_locations references missing location id: {hl}")
            if npc.knowledge:
                for rid in npc.knowledge.rumors or []:
                    if rid not in rumor_ids:
                        _check_ref(False, f"npc[{npc.id}].knowledge.rumors references missing rumor id: {rid}")
                for fid in npc.knowledge.secrets or []:
                    if fid not in fact_ids:
                        _check_ref(False, f"npc[{npc.id}].knowledge.secrets references missing fact id: {fid}")
                for qref in npc.knowledge.quest_facts or []:
                    raw = str(qref).strip()
                    if not raw:
                        continue
                    if ":" in raw:
                        qid, sid = raw.split(":", 1)
                        qid = qid.strip()
                        sid = sid.strip()
                        if qid not in quest_ids:
                            _check_ref(False, f"npc[{npc.id}].knowledge.quest_facts references missing quest id: {qid}")
                        if sid and sid not in quest_stages.get(qid, set()):
                            _check_ref(False, f"npc[{npc.id}].knowledge.quest_facts references missing quest stage: {qid}:{sid}")
                    else:
                        if raw not in quest_ids:
                            _check_ref(False, f"npc[{npc.id}].knowledge.quest_facts references missing quest id: {raw}")

        # Companion refs: locations, quests, factions
        for comp in self.companions or []:
            if comp.faction_id and comp.faction_id not in faction_ids:
                _check_ref(False, f"companion[{comp.id}].faction_id references missing faction id: {comp.faction_id}")
            if comp.recruitment and comp.recruitment.first_meeting_location:
                if comp.recruitment.first_meeting_location not in location_ids:
                    _check_ref(False, f"companion[{comp.id}].recruitment.first_meeting_location references missing location id: {comp.recruitment.first_meeting_location}")
            if comp.personal_quest_id and comp.personal_quest_id not in quest_ids:
                _check_ref(False, f"companion[{comp.id}].personal_quest_id references missing quest id: {comp.personal_quest_id}")

        # Template knowledge refs (optional but validate if present)
        for t in self.npcs.templates or []:
            if t.knowledge:
                for rid in t.knowledge.rumors or []:
                    if rid not in rumor_ids:
                        _check_ref(False, f"npc_template[{t.id}].knowledge.rumors references missing rumor id: {rid}")
                for fid in t.knowledge.secrets or []:
                    if fid not in fact_ids:
                        _check_ref(False, f"npc_template[{t.id}].knowledge.secrets references missing fact id: {fid}")

        return self


# Naming alias for clarity in newer codepaths.
EraPackV2 = EraPack
