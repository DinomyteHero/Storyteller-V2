# 04 — Agents & LLM Plumbing

## Agent Summary (Current — V12.0)

> **V7.0 change:** MemoryAgent, QuestWeaverAgent, ProgressionAgent, and PsychArchivistAgent now run as **deferred maintenance agents** post-commit via `deferred_agents.py`. They write to the `pending_world_state_patches` table rather than directly modifying world state during the turn transaction. This reduces transaction hold time from 10-20s to ~2s on maintenance turns.

> **V10.0 change:** Three new deferred agents added: **RevelationAgent** (LLM, every 5 turns — evaluates hidden info for dramatic timing), **CallbackCrystallizerAgent** (LLM, every 10 turns — captures peak moments for future echo), and **PlayerProfileAgent** (deterministic, every 10 turns — analyzes player choice patterns for Director guidance).

> **V11.0 change:** `BaseAgent` lightweight base class introduced for new agents — provides lazy `AgentLLM` initialization and `_complete_json()` / `_complete_text()` convenience methods.

All agent files are located in `backend/app/core/agents/`.

| Component | File | Deterministic? | LLM? | Authoritative? | Output | Fallback Behavior |
| ----------- | ------ | :---: | :---: | :---: | ------- | --------- |
| **MechanicAgent** | `mechanic.py` | No | Yes (via ResolutionAgent) | No | `MechanicOutput` (dice/DC/time/events) | Deterministic fallback in mechanic node |
| **ResolutionAgent** | `resolution_agent.py` | No | Yes | No | LLM-driven action resolution using Storyteller Core rules | Deterministic fallback |
| **EncounterManager** | `encounter.py` | Yes | No (default) | N/A | `present_npcs`, `spawn_events` | Deterministic; optional LLM cast path if both flags off |
| **DirectorAgent** | `director.py` | No | Yes | No | `director_instructions` (text-only) | Returns empty instructions; pipeline continues |
| **NarratorAgent** | `narrator.py` | No | Yes | Yes | `final_text` (prose) | `AgentFailureError` on failure (caught at graph level) |
| **ChoiceCrafterAgent** | `choice_crafter_agent.py` | No | Yes | Yes | 4x player choices (setting-agnostic) | `AgentFailureError` on failure (caught at graph level) |
| **WorldMindAgent** | `world_mind_agent.py` | No | Yes | No | World events, rumors, faction updates | Falls back to deterministic faction engine |
| **CampaignArchitect** | `architect.py` | No | Yes | No | Campaign blueprint, off-screen simulation | Returns minimal scaffold |
| **BiographerAgent** | `biographer.py` | No | Yes | No | Character background text | Returns default background |
| **CastingAgent** | `casting.py` | No | Yes | No | NPC cast list | Falls back to Bible casting / procedural |
| **IntentRouter** | `intent_router_agent.py` | No | Yes | No | Route classification assist (function-based, no class) | Falls back to keyword-based routing |
| **CompanionSystem** | `companion_system_agent.py` | No | Yes | No | Extended companion interactions (function-based, no class) | Skipped on failure |
| **ContinuityAgent** | `continuity_agent.py` | No | Yes | No | Continuity check results (extends BaseAgent) | Skipped on failure |
| **EraTransitionSceneAgent** | `era_transition_scene_agent.py` | No | Yes | No | Era transition scene text | Skipped on failure |
| **MemoryAgent** | `memory_agent.py` | No | Yes | No | Long-term memory summaries (extends BaseAgent) | Skipped on failure |
| **ProgressionAgent** | `progression_agent.py` | No | Yes | No | Story/player progression updates (extends BaseAgent) | Skipped on failure |
| **PrologueScreenplayAgent** | `prologue_agent.py` | No | Yes | No | Campaign opening narration | Skipped on failure |
| **PsychArchivistAgent** | `psych_archivist_agent.py` | No | Yes | No | Psychology profile updates | Skipped on failure |
| **QuestWeaverAgent** | `quest_weaver_agent.py` | No | Yes | No | Quest narrative text (extends BaseAgent) | Skipped on failure |
| **CampaignBibleAgent** | `campaign_bible_agent.py` | No | Yes | No | Campaign screenplay bible | Skipped on failure |
| **EraForgeAgent** | `era_forge_agent.py` | No | Yes | No | Era pack auto-generation | Skipped on failure |
| **OriginScreenplayAgent** | `origin_agent.py` | No | Yes | No | Origin story / playable backstory generation | Skipped on failure |
| **ArcScreenplayAgent** | `arc_screenplay_agent.py` | No | Yes | No | Per-arc narrative blueprint | Skipped on failure |
| **ArcWeaverAgent** | `arc_weaver_agent.py` | No | Yes | No | Thread weaving between arcs | Skipped on failure |
| **LegacyAgent** | `legacy_agent.py` | No | Yes | No | Character legacy summaries for saga continuity | Skipped on failure |
| **RevelationAgent** (V10.0) | `revelation_agent.py` | No | Yes | No | Revelation queue updates | Skipped on failure |
| **CallbackCrystallizerAgent** (V10.0) | `callback_crystallizer_agent.py` | No | Yes | No | Callback seeds for peak moments | Skipped on failure |
| **PlayerProfileAgent** (V10.0) | `player_profile_agent.py` | Yes | No | No | Player behavior profile | Skipped on failure |

---

## Authoritative vs Non-Authoritative Agents

**The system distinguishes between authoritative and non-authoritative LLM agents (introduced V5.0):**

### Authoritative Agents
These agents produce output that is required for the pipeline to continue. On failure (after one retry), they raise `AgentFailureError`, which is caught at the graph level by `run_turn()` and returned as a structured error to the player.

- **NarratorAgent** — the prose narrative is required for every turn
- **ChoiceCrafterAgent** — player choices are required (no deterministic fallback)

### Non-Authoritative Agents
These agents provide enrichment. On failure, the pipeline continues with a default/empty value. The node logs a warning.

- DirectorAgent, WorldMindAgent, CampaignArchitect, BiographerAgent, CompanionSystemAgent, and all other agents

### `authoritative_call()` Pattern

```python
# backend/app/core/error_handling.py

def authoritative_call(agent_name: str, fn: Callable, *args, **kwargs):
    """Call an authoritative agent with one retry. Raises AgentFailureError on second failure."""
    for attempt in range(2):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if attempt == 0:
                logger.warning("Agent '%s' failed (attempt 1/2), retrying: %s", agent_name, exc)
            else:
                logger.error("Agent '%s' failed after retry: %s", agent_name, exc)
                raise AgentFailureError(agent_name, exc) from exc
```

---

## Per-Role LLM Configuration

Each agent role can be independently configured via environment variables. V7.0 adds per-role cloud provider routing — see `docs/HYBRID_CLOUD_SETUP.md` for full configuration guide.

```bash
# Pattern: STORYTELLER_{ROLE}_{CONFIG}
STORYTELLER_DIRECTOR_MODEL=mistral-nemo:latest
STORYTELLER_NARRATOR_MODEL=mistral-nemo:latest
STORYTELLER_ARCHITECT_MODEL=qwen3:4b
STORYTELLER_CASTING_MODEL=qwen3:4b
STORYTELLER_BIOGRAPHER_MODEL=qwen3:4b
STORYTELLER_KG_EXTRACTOR_MODEL=qwen3:4b
STORYTELLER_CHOICE_CRAFTER_MODEL=qwen3:8b

# Provider override (default: ollama)
STORYTELLER_DIRECTOR_PROVIDER=ollama
STORYTELLER_NARRATOR_PROVIDER=anthropic  # Switch to cloud

# Custom Ollama endpoint per role
STORYTELLER_DIRECTOR_BASE_URL=http://gpu-server:11434

# Timeout override (seconds)
STORYTELLER_NARRATOR_TIMEOUT=120
LLM_TIMEOUT=300  # Default fallback timeout
```

### Default Model Assignments

| Role | Default Model | Notes |
| ------ | ------------ | ------- |
| Director | `mistral-nemo:latest` | Quality-critical; generates scene instructions |
| Narrator | `mistral-nemo:latest` | Quality-critical; generates prose (authoritative) |
| ChoiceCrafter | `qwen3:8b` | Player choice generation (authoritative) |
| Mechanic | `qwen3:8b` | Action resolution via ResolutionAgent (LLM with deterministic fallback) |
| CompanionSystem | `qwen3:8b` | Extended companion interactions + voice |
| WorldMind | `qwen3:8b` | Contextual world simulation (LLM-driven) |
| QuestWeaver | `qwen3:8b` | Dynamic quest generation (deferred) |
| Memory | `qwen3:8b` | Long-term memory summaries (deferred) |
| Prologue | `qwen3:8b` | Campaign opening scene generation |
| ArcScreenplay | `qwen3:8b` | Per-arc narrative blueprint |
| Bible | `qwen3:8b` | Campaign bible generation (one-shot at setup) |
| EraForge | `qwen3:8b` | Era pack auto-generation |
| Origin | `qwen3:8b` | Origin story / playable backstory generation |
| Architect | `qwen3:4b` | Campaign blueprint + off-screen simulation |
| Casting | `qwen3:4b` | Legacy NPC casting path |
| Biographer | `qwen3:4b` | Character background |
| KG Extraction | `qwen3:4b` | Knowledge graph extraction |
| IntentRouter | `qwen3:4b` | LLM intent classification assist |
| ArcWeaver | `qwen3:4b` | Thread weaving between arcs |
| CampaignInit | `qwen3:4b` | Campaign initialization |
| Continuity | `qwen3:4b` | LLM-managed Truth Ledger (fact pruning) |
| Progression | `qwen3:4b` | Story/player progression (deferred) |
| PsychArchivist | `qwen3:4b` | Psychology profile updates (deferred) |
| RevelationAgent (V10.0) | `qwen3:4b` | Revelation timing evaluation (deferred, every 5 turns) |
| CallbackCrystallizer (V10.0) | `qwen3:4b` | Peak moment identification (deferred, every 10 turns) |
| PlayerProfileAgent (V10.0) | N/A (deterministic) | Choice pattern analysis (deferred, every 10 turns) |
| Embedding | `nomic-embed-text` | Ingestion + RAG retrieval |

---

## Agent Details

### MechanicAgent — `backend/app/core/agents/mechanic.py`

**LLM-based via ResolutionAgent.** Routes action resolution through `ResolutionAgent`, an LLM-based Game Master that resolves player actions using Storyteller Core rules. The mechanic node falls back to deterministic resolution if the LLM call fails.

**Responsibilities:**
- Map user action text to `action_type` (COMBAT, STEALTH, PERSUADE, INVESTIGATE, MOVE/TRAVEL, DIALOGUE_ONLY, USE_ITEM, CRAFT, SKILL_CHECK, GENERIC)
- Resolve actions via `ResolutionAgent` (LLM-driven DC, dice, events, consequences)
- Compute `time_cost_minutes` (action-type weighted, modified by success)
- Compute `stress_delta` (risk tier: SAFE=0, RISKY=+1, DANGEROUS=+2; critical_failure=+3)
- Compute alignment delta (PARAGON/RENEGADE tone scaffold for companion reactions)
- Compute faction reputation delta (faction-targeted actions)
- Determine `world_reaction_needed` flag (triggers WorldSim attention)
- Generate `events` list (typed event payloads from outcome)
- Generate `narrative_facts` (grounding facts for Narrator)

**Key Output: `MechanicOutput`**
```python
MechanicOutput(
    action_type="COMBAT",
    time_cost_minutes=15,
    success=True,
    roll=18,
    dc=14,
    outcome_summary="Critical hit! The guard goes down.",
    critical_outcome="critical_success",
    events=[...],
    narrative_facts=[...],
    stress_delta=2,
    world_reaction_needed=True,
    modifiers={"arc_stage": -2, "environmental": 1}
)
```

---

### DirectorAgent — `backend/app/core/agents/director.py`

**LLM call produces text-only output** (no JSON schema, no suggestion generation since V5.0).

**Responsibilities:**
- Build scene pacing instructions for the Narrator
- Check `is_hub_location()` → inject hub-mode context if at hub
- Incorporate arc guidance (stage, tension, pacing hints, fired moment beats)
- Incorporate scene frame context (topic_primary, subtext, npc_agenda)
- Use RAG (4 lanes):
  - Lane 0: Base style (always-on)
  - Lane 1: Era style
  - Lane 2: Genre style (detected by `genre_triggers.py`)
  - Lane 3: Archetype style
- Use KG character context (`shared_kg_character_context`)
- Use episodic memories (`shared_episodic_memories`) for continuity
- Use `personality_profile` blocks for present NPCs
- Use `known_npcs` for per-NPC naming consistency
- Use `SettingRules` for setting-agnostic context
- Use inter-party tension context
- Use `psych_profile` (current_mood, stress_level) for tone calibration

**Output:** `director_instructions` (plain text, ~500 tokens), plus `shared_kg_character_context`, `shared_episodic_memories` (for Narrator reuse).

---

### NarratorAgent — `backend/app/core/agents/narrator.py`

**Authoritative LLM agent.** Raises `AgentFailureError` on failure.

**Responsibilities:**
- Generate prose-only narration (5-8 sentences, max 250 words)
- Use `director_instructions` as pacing guidance
- Use `mechanic_result` for outcome grounding
- Use lore RAG (novel/sourcebook chunks)
- Use character voice RAG (dialogue samples)
- Use shared KG context + episodic memories from Director (avoid double retrieval)
- Apply pronoun system via `pronoun_block()` for consistent player-character references
- Apply banter queue (consume 1 item if not high-stakes combat)
- Apply inter-party tension context if companions present

**Post-Processing Pipeline** (`narrator_postprocess.py`):
1. `_strip_structural_artifacts()` — removes 12+ patterns (markdown headers, list bullets, OOC text, "Narrator:", etc.)
2. `_truncate_overlong_prose()` — caps at 250 words at sentence boundary
3. `_enforce_pov_consistency()` — strips meta-narrator endings ("What will you do?", etc.)
4. `_flag_unknown_entities()` — warns on NPC names not in `present_npcs`

**Output:** `final_text` (post-processed prose), `lore_citations`, `embedded_suggestions=None`

---

### ChoiceCrafterAgent — `backend/app/core/agents/choice_crafter_agent.py`

**Authoritative LLM agent (V5.0).** Raises `AgentFailureError` on failure. Replaces the old `SuggestionRefinerAgent`.

**Key design principle:** Setting-agnostic. Uses `SettingRules.suggestion_style` instead of hardcoded universe terms.

**Responsibilities:**
- Generate 4 player choices from the Narrator's `final_text` and scene context
- Build context from: location, present NPCs, mechanic outcome, NPC utterance, scene frame fields (`topic_primary`, `subtext`, `npc_agenda`), companion hint, player history (tone streak detection), consequence hints from ledger, arc stage + tension, stat summary, setting style, director intent
- Return raw choices as list of `{text, tone, meaning, risk, consequence_hint}` dicts

**Post-Processing Pipeline** (in `choice_crafter_node.py`):
1. `_to_action_suggestions()` — convert dicts to `ActionSuggestion` objects
2. `ensure_tone_diversity()` — guarantee all 4 tones (PARAGON, INVESTIGATE, RENEGADE, NEUTRAL) are represented
3. `lint_actions()` — validate NPC/item/travel references
4. `action_suggestions_to_player_responses()` — convert to `PlayerResponse` dicts for DialogueTurn

**Output:** `suggested_actions` (list of `ActionSuggestion` dicts), `player_responses` (list of `PlayerResponse` dicts)

---

### CampaignArchitect — `backend/app/core/agents/architect.py`

**Non-authoritative LLM agent.** Falls back to minimal deterministic scaffold.

**Two responsibilities:**

1. **Campaign blueprint generation** (used in `POST /v2/setup/auto`):
   - Generates arc scaffold: themes, opening threads, climax, act outline
   - Populates `world_state_json.act_outline`, `world_state_json.opening_beats`

2. **Off-screen simulation** (used by WorldSim node on tick boundary):
   - Simulates world events for `active_factions`
   - Generates new rumors, faction goals, NPC movements
   - Falls back to `faction_engine.simulate_faction_tick()` if LLM unavailable

---

### CompanionSystemAgent — `backend/app/core/agents/companion_system_agent.py`

**Non-authoritative LLM agent (V5.0).** Extended companion interactions beyond the deterministic `companion_reactions.py` layer.

**Responsibilities:**
- Generate companion-initiated dialogue or scene beats when triggered
- Handle `COMPANION_REQUEST`, `COMPANION_QUEST`, `COMPANION_CONFRONTATION` events
- Incorporate companion personality, voice tags, and affinity trajectory

---

### WorldMindAgent — `backend/app/core/agents/world_mind_agent.py`

**Non-authoritative LLM agent (V5.0).** LLM-driven world simulation.

**Responsibilities:**
- Generate off-screen world events from faction context
- Produce world-state rumors with narrative flavor
- Produce faction movement and goal updates
- Falls back to deterministic `faction_engine` on failure

---

### Other V5.0 Agents (brief)

| Agent | File | Primary Use |
| ------- | ------ | ----------- |
| **IntentRouterAgent** | `intent_router_agent.py` | Assist routing for ambiguous inputs (invoked by router node when confidence is low) |
| **ContinuityAgent** | `continuity_agent.py` | Post-narration continuity check (can flag contradictions for Validator) |
| **EraTransitionSceneAgent** | `era_transition_scene_agent.py` | Generate era-transition narrative scenes when `era_transition_pending=True` |
| **MemoryAgent** | `memory_agent.py` | Summarize episodic memories for long-running campaigns |
| **ProgressionAgent** | `progression_agent.py` | Track player skill/story progression milestones |
| **PrologueAgent** | `prologue_agent.py` | Generate campaign opening scene (invoked by `/v2/campaigns` creation) |
| **PsychArchivistAgent** | `psych_archivist_agent.py` | Update player psychology profile based on accumulated stress/choices |
| **QuestWeaverAgent** | `quest_weaver_agent.py` | Generate narrative context for quest stage transitions |
| **ResolutionAgent** | `resolution_agent.py` | Generate story resolution scenes for completed arcs |
| **ArcScreenplayAgent** | `arc_screenplay_agent.py` | Act-level screenplay planning (arc outline) |
| **ArcWeaverAgent** | `arc_weaver_agent.py` | Thread weaving between active story arcs |
| **BiographerAgent** | `biographer.py` | Character background text generation (used in campaign setup) |

---

### V10.0 Deferred Intelligence Agents

| Agent | File | LLM? | Frequency | Primary Use |
| ------- | ------ | :---: | ----------- | ----------- |
| **RevelationAgent** | `revelation_agent.py` | Yes | Every 5 turns | Scans NPC agendas, world_sim rumors, faction moves, and consequence hints. Tags each with dramatic_value (1-10) and optimal_reveal_conditions. Stores in `world_state["revelation_queue"]`. Director receives top revelations scored by scene fitness. |
| **CallbackCrystallizerAgent** | `callback_crystallizer_agent.py` | Yes | Every 10 turns | Scans recent turns for peak moments: CLIMAX/ELEVATED scene weights, large affinity deltas (|delta| > 3), major decisions. Stores `callback_seeds` with trigger conditions. Director echoes past moments when conditions match. |
| **PlayerProfileAgent** | `player_profile_agent.py` | No | Every 10 turns (min 10) | Analyzes `choice_history` for: tone distribution, action preferences, risk tolerance, companion engagement, creativity ratio, engagement trends. Derives play_style (diplomat/fighter/explorer/socialite) and boredom detection. Director receives behavioral hints. |

---

## Pydantic Models

### `GameState` — `backend/app/models/state.py`

The LangGraph pipeline packet. See `03_state_and_persistence.md` for full field list.

### `ActionSuggestion` — `backend/app/models/state.py`

Player choice object.

```python
class ActionSuggestion(BaseModel):
    label: str              # Short display text (e.g., "Press for details")
    intent_text: str        # Full action description sent as user_input
    category: str           # Action category (SOCIAL, COMBAT, INVESTIGATE, etc.)
    tone_tag: str           # PARAGON | INVESTIGATE | RENEGADE | NEUTRAL
    risk_level: str         # SAFE | RISKY | DANGEROUS
    consequence_hint: str   # Optional hint about likely outcome
    meaning_tag: str        # Semantic meaning tag for companion reactions
```

### `TurnContract` — `backend/app/models/turn_contract.py`

Structured turn result stored in `rendered_turns`.

```python
class TurnContract(BaseModel):
    meta: TurnMeta          # campaign_id, turn_number, intent, arc_stage
    mechanic: MechanicOutput | None
    narration: str          # final_text
    choices: list[Choice]   # Player-facing choices (from ChoiceCrafter)
    suggestions: list[ActionSuggestion]  # Sugested follow-ups
    facts: list[Fact]       # Facts for truth ledger upsert
    warnings: list[str]
```

### `Fact` — `backend/app/models/turn_contract.py`

```python
class Fact(BaseModel):
    fact_key: str       # e.g., "npc_location:darth_vader"
    fact_value: Any     # e.g., "Death Star"
```

### `SettingRules` — `backend/app/world/era_pack_models.py`

Setting-agnostic rules for agents. Stored in `world_state_json["setting_rules"]`.

```python
class SettingRules(BaseModel):
    setting_name: str = "Star Wars Legends"
    default_species: list[str] = ["Human", "Twi'lek", "Rodian"]
    suggestion_style: str = "Star Wars"   # Used by ChoiceCrafter for setting context
    faction_names: list[str] = [...]
    # ... other setting-specific config
```

### `EraMoment` — `backend/app/world/era_pack_models.py`

Scripted narrative moment definition (V5.0).

```python
class EraMomentTrigger(BaseModel):
    arc_stage: str | None = None
    turn_number_min: int | None = None
    location_tags_any: list[str] = []
    companion_id: str | None = None
    affinity_threshold: int | None = None
    quest_id_completed: str | None = None
    alignment_min: dict[str, int] = {}

class EraMoment(BaseModel):
    id: str
    title: str
    trigger: EraMomentTrigger
    narrative_beat: str    # Text injected into Director scene instructions
    once_only: bool = True
```

### `PartyState` / `CompanionRuntimeState` — `backend/app/core/party_state.py`

Persistent multi-axis companion state (V5.0).

```python
class CompanionRuntimeState(BaseModel):
    companion_id: str
    influence: int = 0      # -100..100 (primary relationship axis)
    trust: int = 0          # -100..100
    respect: int = 0        # -100..100
    fear: int = 0           # -100..100
    loyalty_progress: int = 0   # 0..100
    traits: dict[str, int] = {}
    memories: list[str] = []   # max 10 significant moments
    triggers_fired: list[str] = []
    banter_last_turn: int = 0

class PartyState(BaseModel):
    active_companions: list[str]
    companion_states: dict[str, CompanionRuntimeState]
```

---

## LLM Provider Architecture

### LLM Client Base — `backend/llm_client.py`

`LLMClient` is the primary HTTP client for Ollama. Key methods:

```python
class LLMClient:
    def chat(self, model, messages, temperature, format) -> str:
        """Ollama /api/chat endpoint."""

    def ensure_json(self, model, messages, schema, max_retries=3) -> dict:
        """Call with JSON mode, parse, repair, retry on malformed JSON."""
```

### LLM Provider Abstraction — `backend/app/core/llm_provider.py`

`AgentLLM` wraps the LLM client with per-role config:

```python
class AgentLLM:
    def __init__(self, role: str):
        # Reads STORYTELLER_{ROLE}_MODEL, _PROVIDER, _BASE_URL, _TIMEOUT from env

    def call(self, system: str, user: str, **kwargs) -> str:
        """Text-mode call (Director)."""

    def call_json(self, system: str, user: str, schema: dict) -> dict:
        """JSON-mode call with repair+retry (used by NarratorAgent, ChoiceCrafterAgent, etc.)."""
```

### JSON Reliability

`backend/app/core/json_reliability.py` + `json_repair.py` provide:

- `safe_parse_json(text)` — try direct parse, then regex extraction, then heuristic repair
- `repair_json(text)` — bracket matching, quote fixing, trailing comma removal
- `parse_with_retry(fn, max_retries=3)` — retry wrapper for LLM JSON calls

---

## Hub/Downtime System — `backend/app/core/hub_system.py`

The Hub System activates when the current location has `"hub"` in its era-pack `services` list, or when `world_state["hub_mode"] = True`.

**Director integration:**
```python
# In director node:
if is_hub_location(world_state, era_pack):
    hub_options = get_hub_options(world_state, party_ids)
    hub_context = build_hub_system_prompt_injection(world_state, hub_options)
    # inject hub_context into Director system prompt
```

**Hub options:** `rest`, `gather_intel`, `resupply`, `wait`, `talk_{companion_id}` (for each party member)

**`apply_rest(world_state)`:** Reduces `stress_level` by 10 (min 0) and `player_condition["fatigue"]` by 5. Sets `last_rest_turn`.
