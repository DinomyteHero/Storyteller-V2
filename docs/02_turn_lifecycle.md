# 02 — Turn Lifecycle

## Overview

A single turn flows through a LangGraph `StateGraph` that is compiled once on first use (see `backend/app/core/graph.py`). The pipeline is invoked by `run_turn(conn, state)`, which injects the SQLite connection as `state["__runtime_conn"]` and strips it after graph execution.

**V5.0 changes:**
- `moments` node added between `companion_reaction` and `arc_planner`
- `suggestion_refiner` replaced by `choice_crafter` (authoritative LLM; no deterministic fallback)
- `run_turn()` now catches `AgentFailureError` from authoritative agents and returns a structured error in `GameState`

**V7.0 changes:**
- Shared pipeline executor via `_run_pipeline_with_timings()` — streaming and non-streaming paths share the same node sequence via `get_pre_narrator_steps()`/`get_post_narrator_steps()`
- Deferred maintenance agents (MemoryAgent, QuestWeaver, ProgressionAgent, PsychArchivist) run post-commit via `deferred_agents.py`, writing to `pending_world_state_patches` table
- Turn snapshots written to `turn_snapshots` table after each successful commit (rewind support)

**V11.0 changes:**
- No pipeline topology changes. Visual layer (portraits/key art) is post-pipeline decoration in the response builder — `portrait_url` and `location_art_url` are resolved after Commit when `ENABLE_PORTRAITS=1`
- `lore_sources` table tracks ingested source metadata; no pipeline impact
- Universe & Story UX is frontend-only; no pipeline changes
- Canon event checking for Historical mode campaigns via `canon_scheduler.py`
- Consequence propagation via `consequence_propagator.py` (ripple/wave/tsunami tiers)
- Turn idempotency via `Idempotency-Key` header and `turn_idempotency` table

**V8.0 changes:**
- Multi-arc campaign lifecycle (2-5 arcs by scale) with interlude scenes between arcs
- Epilogue system (3-turn wind-down) with campaign completion flag
- Consequence surfacing: wave/tsunami tiers mandate narrator references
- Prose-choice bridge: SCENE ENDING extraction feeds ChoiceCrafter

**V10.0 changes (Narrative Intelligence):**
- Router detects `creative_deviation` when free-text input doesn't match any suggested action (similarity < 0.4)
- Companion reaction node tracks wound/reveal layers — 3-tier depth (surface/deep/core) unlocked at affinity thresholds
- Arc planner injects foreshadowing hooks (SETUP/RISING), thematic echoes (CLIMAX), and arc mood profiles into `arc_guidance`
- Director receives 10 new prompt injection sections: dramatic irony, creative input, narrative rhythm, revelation queue, callback seeds, player tendencies, foreshadowing, thematic echoes, mood profile, companion revelations
- 3 new deferred agents run post-commit: RevelationAgent (every 5 turns), CallbackCrystallizerAgent (every 10 turns), PlayerProfileAgent (every 10 turns, deterministic)
- Commit node records choice history for player profiling

## Pipeline Topology (V11.0)

```mermaid
flowchart TD
    START([Player Input]) --> ROUTER

    ROUTER{Router Node}
    ROUTER --> | "intent=META"| META[Meta Node]
    ROUTER --> | "intent=TALK"| ENCOUNTER[Encounter Node]
    ROUTER --> | "intent=ACTION"| MECHANIC[Mechanic Node]

    META --> COMMIT[Commit Node]

    MECHANIC --> ENCOUNTER
    ENCOUNTER --> WORLDSIM[WorldSim Node]
    WORLDSIM --> MOMENTS[Moments Node]
    MOMENTS --> ARCPLAN[Arc Planner Node]
    ARCPLAN --> INTERLUDE[Interlude Node]
    INTERLUDE --> SCENEFRAME[Scene Frame Node]
    SCENEFRAME --> DIRECTOR[Director Node]
    DIRECTOR --> COMPANION[Companion Reaction Node]
    COMPANION --> NARRATOR[Narrator Node]
    NARRATOR --> VALIDATOR[Narrative Validator Node]
    VALIDATOR --> CHOICECRAFTER[Choice Crafter Node]
    CHOICECRAFTER --> COMMIT

    COMMIT --> END_NODE([Return GameState])

    style ROUTER fill:#f9f,stroke:#333
    style COMMIT fill:#ff9,stroke:#333
    style WORLDSIM fill:#9ff,stroke:#333
    style ARCPLAN fill:#cfc,stroke:#333
    style INTERLUDE fill:#ffc,stroke:#333
    style VALIDATOR fill:#fcf,stroke:#333
    style CHOICECRAFTER fill:#f9c,stroke:#333
    style MOMENTS fill:#cff,stroke:#333
```

## Node-by-Node Detail

### 1) Router + Meta

**Files:**

- Router: `backend/app/core/nodes/router.py` (delegates to `backend/app/core/router.py`)
- Meta: `backend/app/core/nodes/router.py`

**Purpose:** Classify input into one of three intents:

- `META`: help/save/load/quit-style commands (no world time, no events)
- `TALK`: dialogue-only (skips Mechanic but still runs Encounter -> WorldSim -> ...)
- `ACTION`: full pipeline

**Key rules:**

- Only true dialogue-only (`route=TALK`, `action_class=DIALOGUE_ONLY`, `requires_resolution=false`) becomes `intent=TALK`.
- Action/persuasion guardrails force `intent=ACTION` even if input contains dialogue cues.

**V10.0 addition — Creative Deviation Detection:**
- After routing, if the input is free-text (no `structured_intent`) and `suggested_actions` from the previous turn exist, the router compares the input against all suggestions via `SequenceMatcher`.
- If the best match ratio is below `CREATIVE_DEVIATION_SIMILARITY_THRESHOLD` (0.4), `state["creative_deviation"] = True` is set.
- The Director then receives a `CREATIVE PLAYER INPUT` section encouraging it to reward the player's unexpected action.

**Output keys set:**

- `intent`, `route`, `action_class`, `intent_text`, `router_output`, `creative_deviation` (V10.0)
- For `intent=TALK`: a minimal `mechanic_result` is synthesized with `time_cost_minutes=DIALOGUE_ONLY_MINUTES` (default 8).
- Meta node sets deterministic `final_text` + `suggested_actions` and skips all LLM/RAG work.

---

### 2) Mechanic

**File:** `backend/app/core/nodes/mechanic.py`

**Purpose:** Deterministic action resolution (dice/DC/events/time). No LLM.

Key features:

- 3-tier risk levels: SAFE, RISKY, DANGEROUS (affects DC modifiers and stress delta)
- Dynamic difficulty: `_ARC_DC_MODIFIER` adjusts DCs by arc stage (SETUP=-2, CLIMAX=+3)
- Environmental modifiers: `environmental_modifiers()` infers location tag, weapon check, time-of-day
- Player stat advantage computation

Outputs:

- `mechanic_result` (serialized `MechanicOutput`): `action_type`, `events`, `narrative_facts`, `time_cost_minutes`, `success`, `outcome_summary`, `modifiers`, `stress_delta`, `critical_outcome`, `world_reaction_needed`, plus tone/alignment scaffolding.

---

### 3) Encounter

**File:** `backend/app/core/nodes/encounter.py` (uses `backend/app/core/agents/encounter.py`)

**Purpose:** Determine `present_npcs` at the player's effective location and stage any NPC introduction events.

Behavior (current/default):

- Reads DB connection from `state["__runtime_conn"]`.
- Queries existing NPCs for `(campaign_id, effective_location)`.
- If none exist:
  - If `ENABLE_BIBLE_CASTING=1`, chooses NPCs deterministically from Era Packs via `ContentRepository`.
  - If `ENABLE_PROCEDURAL_NPCS=1`, generates a deterministic procedural NPC (fallback when Bible selection yields none).
  - Emits `NPC_SPAWN` events (staged in memory; committed later) when encounter throttling allows introductions.
- **Legacy path:** If both `ENABLE_BIBLE_CASTING=0` and `ENABLE_PROCEDURAL_NPCS=0`, the EncounterManager uses a legacy 10% "spawn request" and the node may call the LLM-based `CastingAgent` (still gated by encounter throttling).
- Dynamic NPC cap: `MAX_NPCS_BY_LOC_TAG` limits NPCs per location type, plus background figures (5-tuple return).

Also:

- Stages hidden throttle events (`NPC_INTRODUCTION_RECORDED`, `LAST_LOCATION_UPDATED`) that are applied inside Commit's DB transaction.
- Loads `active_rumors` via `get_recent_public_rumors(limit=3)`.

**Output keys set:** `present_npcs`, `spawn_events`, `throttle_events`, `active_rumors`

---

### 4) WorldSim (Living World)

**File:** `backend/app/core/nodes/world_sim.py` (calls `backend/app/core/agents/world_mind_agent.py` or `backend/app/world/faction_engine.py`)

**Purpose:** Run off-screen simulation on tick-boundary crossing or travel.

**Trigger logic:**

- Let `t0 = campaign.world_time_minutes` and `dt = mechanic_result.time_cost_minutes` and `t1 = t0 + dt`.
- Run WorldSim when:
  - tick boundary crossed: `floor(t0/tick_minutes) != floor(t1/tick_minutes)`, where `tick_minutes = WORLD_TICK_INTERVAL_HOURS*60` (default 240), **or**
  - travel occurred (MOVE event or `action_type == "TRAVEL"`).

**When triggered:**

- Loads current `active_factions` from DB (`campaigns.world_state_json.active_factions`).
- Calls `WorldMindAgent.simulate()` (LLM with deterministic fallback) or the deterministic `faction_engine.simulate_faction_tick()`.
- Produces:
  - `world_sim_events` (hidden faction moves / plot ticks)
  - `world_sim_rumors` as public rumor events (`is_public_rumor=true`)
  - `world_sim_factions_update` (new `active_factions` list to persist)
  - `campaign.news_feed` (ME-style briefing, derived from rumors via `rumors_to_news_feed()`)
  - `faction_memory` updates (multi-turn plan tracking)
  - `npc_states` updates (20% movement chance per tick, faction-aware goals)
- Always sets `pending_world_time_minutes = t1` for Commit.

---

### 5) Moments (V5.0)

**File:** `backend/app/core/nodes/moments.py`

**Purpose:** Check and fire `EraMoment` triggers defined in the era pack.

**Pipeline position:** `world_sim → moments → arc_planner`

**Trigger conditions (all specified must pass):**
- `companion_id + affinity_threshold`: companion affinity >= threshold
- `arc_stage`: current arc stage matches
- `turn_number_min`: current turn >= minimum
- `location_tags_any`: current location has any of these tags
- `quest_id_completed`: quest is in the completed quests list
- `alignment_min`: player alignment axis >= minimum value

**When a moment fires:**
- The moment ID is added to `world_state["fired_moments"]` for once-only enforcement.
- The moment's `narrative_beat` is prepended to `arc_guidance["scene_instructions"]` so the Director sees it.
- All fired beats are collected in `arc_guidance["fired_moments_beats"]`.

**Failure handling:** Non-fatal — any exception returns the unchanged state. Only fires once per moment ID (unless `once_only=False`).

**Output keys set:** `arc_guidance` (updated with fired moment beats), `campaign.world_state_json` (fired_moments list updated)

---

### 6) Arc Planner

**File:** `backend/app/core/nodes/arc_planner.py`

**Purpose:** Deterministic story arc tracking and pacing guidance.

- Reads `turn_number`, `ledger`, `arc_state` from world_state_json.
- Outputs `arc_guidance`: arc stage, tension level, priority threads, pacing hints, suggested action weights, active themes, hero_beat, archetype_hints, theme_guidance, era_transition_pending, and any fired moment beats from the Moments node.
- Tracks Hero's Journey beats (12 beats), genre triggers, and era transition readiness.
- **V10.0 — Arc Mood Profiles:** Reads `world_state["arc_mood_profile"]` (default "heroic") and includes stage-specific mood directive in `arc_guidance["mood_directive"]`. 5 profiles: heroic, noir, tragic, kishotenketsu, mystery.
- **V10.0 — Foreshadowing Hooks:** During SETUP/RISING, seeds `arc_guidance["foreshadow_hints"]` from dangling hooks of previous arcs and NPC agendas containing hidden/secret keywords.
- **V10.0 — Thematic Resonance:** At CLIMAX, reads the first arc's `thematic_signature` from `arc_consequences["arc_history"]` and injects `arc_guidance["thematic_echoes"]` with a resonance note referencing early campaign themes.

No DB writes, no LLM.

---

### 7) Interlude (V8.0)

**File:** `backend/app/core/nodes/interlude.py`

**Purpose:** Lightweight deterministic scene between arcs — provides breathing room between arc RESOLUTION and new arc SETUP.

**Pipeline position:** `arc_planner → interlude → scene_frame`

**Behavior:**

- Checks `arc_guidance.get("interlude_active")`.
- If `False`: pass-through — returns state unchanged.
- If `True`: builds downtime context from:
  - `campaign.news_feed` (up to 2 items)
  - `state.active_rumors` (up to 3 items)
  - `world_state.banter_queue` (first item)
- Constructs `director_instructions` for a reflective, low-stakes scene.
- Advances `pending_world_time_minutes` by `INTERLUDE_TIME_SKIP_HOURS * 60`.

No DB access. No LLM calls. Deterministic.

**State fields read:** `arc_guidance`, `campaign`, `world_state_json`, `active_rumors`, `pending_world_time_minutes`

**Output keys set:** `director_instructions`, `pending_world_time_minutes`

---

### 8) Scene Frame

**File:** `backend/app/core/nodes/scene_frame.py`

**Purpose:** Builds scene framing context for the Director.

- Extracts `topic_primary`, `subtext`, `npc_agenda` from current scene state.
- These fields are available to the ChoiceCrafter node (passed via state).

---

### 9) Director (LLM)

**File:** `backend/app/core/nodes/director.py` (agent in `backend/app/core/agents/director.py`)

**Purpose:** Pacing instructions (text-only) for the Narrator.

The Director generates **text-only scene instructions** (no JSON schema, no suggestion generation in the LLM call). All player-facing choices are now generated by the ChoiceCrafter node.

- Checks `is_hub_location()` and injects hub-mode context if at a hub location.
- Uses RAG (4-lane style retrieval):
  - `retrieve_style_layered()` from `backend/app/rag/style_retriever.py`
  - Adventure hook lore from `backend/app/rag/lore_retriever.py`
  - KG context from `backend/app/rag/kg_retriever.py`
- Uses `personality_profile` blocks for NPC characterization.
- Uses episodic memories (`shared_episodic_memories`) for narrative continuity.
- Uses `known_npcs` for per-NPC naming.
- Uses `SettingRules` from `get_setting_rules(state)` for setting-agnostic context.
- Adds turn warnings when it has to fallback, trim context, or lint/pad actions.

**Output keys set:** `director_instructions`, `warnings`, `shared_kg_character_context`, `shared_episodic_memories`

---

### 10) Companion Reaction

**File:** `backend/app/core/nodes/companion.py` (uses `backend/app/core/agents/companion_system_agent.py` and `backend/app/core/companion_reactions.py`)

**Purpose:** Party/alignment/faction updates + banter + inter-party dynamics. Runs after Director so companion reactions can be informed by scene context.

**Pipeline position:** `director → companion_reaction → narrator`

- Applies alignment + faction reputation deltas (currently derived from tone tags and heuristics).
- Updates `party_affinity`, `loyalty_progress`, and queues 0-1 banter lines from BANTER_POOL (17 styles).
- May enqueue a short "news banter" line based on briefing items.
- **Inter-party tensions:** `compute_inter_party_tensions()` detects opposing reactions among companions and generates tension context for Director/Narrator.
- **Companion-initiated events:**
  - `COMPANION_REQUEST` at TRUSTED loyalty level
  - `COMPANION_QUEST` at LOYAL loyalty level
  - `COMPANION_CONFRONTATION` on sharp affinity drop
- Companion reactions summary (`companion_reactions_summary`) injected into campaign for Narrator context.
- **V10.0 — Wound/Reveal Layers:** After affinity updates, checks each companion's `revelation_stages` (from `data/companions.yaml`). When affinity crosses a threshold, advances the companion's wound layer (surface → deep → core), sets `revealed_this_turn = True`, and stores in `world_state["companion_revelations"]`. The Director receives trigger text to weave the revelation into the scene. Max one stage advancement per companion per turn.

LLM calls via `generate_companion_reactions()` from CompanionSystemAgent module. No DB access.

---

### 11) Narrator (LLM)

**File:** `backend/app/core/nodes/narrator.py` (agent in `backend/app/core/agents/narrator.py`; prompt construction in `narrator_prompt.py`; output post-processing in `narrator_postprocess.py`)

**Purpose:** Final prose narration (prose-only, no choices).

The Narrator writes **only prose** (5-8 sentences, max 250 words). `embedded_suggestions` is always `None`. The `_prose_stop_rule` instructs the LLM to stop after the last narrative sentence.

- Uses RAG:
  - Lore chunks (`doc_type in {novel, sourcebook}`, `section_kind in {lore, location, faction}`)
  - Character voice snippets from `backend/app/rag/character_voice_retriever.py`
- Uses shared RAG data (KG context, episodic memories) from Director node to avoid duplicate retrieval.
- Uses token budgeting (`backend/app/core/context_budget.py`) and emits warnings when trimming occurs.
- Uses companion reactions summary and inter-party tension context.
- Appends one queued banter line if not in high-stakes combat.
- **Post-processing pipeline** (implemented in `backend/app/core/agents/narrator_postprocess.py`):
  - `_strip_structural_artifacts()` catches 12+ patterns
  - `_truncate_overlong_prose()` caps at 250 words, breaks at sentence boundary
  - `_enforce_pov_consistency()` strips meta-narrator endings
  - `_flag_unknown_entities()` warns on hallucinated NPC names not in `present_npcs`

**Output keys set:** `final_text`, `lore_citations`, `embedded_suggestions` (always `None`), `campaign` (banter queue consumed), `warnings`

---

### 12) Narrative Validator

**File:** `backend/app/core/nodes/narrative_validator.py`

**Purpose:** Deterministic post-narration checks.

- Validates narrative consistency against mechanic outcomes.
- Checks potential contradictions against ledger constraints.
- Appends non-blocking warnings/notes (`validation_notes`, `warnings`); does not halt the turn.

---

### 13) Choice Crafter (V5.0 — replaces Suggestion Refiner)

**File:** `backend/app/core/nodes/choice_crafter_node.py`

**Purpose:** LLM-driven player choice generation from the Narrator's prose and scene context.

**Key differences from the former Suggestion Refiner:**
- **Authoritative:** No deterministic fallback. On LLM failure, raises `AgentFailureError` (caught at graph level in `run_turn()`).
- **Setting-agnostic:** Uses `get_setting_rules(state)` for `suggestion_style` — no hardcoded universe names.
- **Richer context:** Uses `npc_utterance`, `scene_frame` fields (`topic_primary`, `subtext`, `npc_agenda`), companion hint, player history hint, consequence hints, arc stage, tension level, and stat summary.

**Calls into:**
- `backend/app/core/agents/choice_crafter_agent.py:generate_choices()` — LLM call
- `backend/app/core/suggestion_engine.py:classify_suggestion()` + `ensure_tone_diversity()`
- `backend/app/core/action_lint.py:lint_actions()`
- `backend/app/core/suggestion_engine.py:action_suggestions_to_player_responses()` — converts to `PlayerResponse` dicts

**Output keys set:** `suggested_actions` (list of `ActionSuggestion` dicts), `player_responses` (list of `PlayerResponse` dicts for the DialogueTurn), `warnings`

---

### 14) Commit (Single Transaction Boundary)

**File:** `backend/app/core/nodes/commit.py`

**Purpose:** **The only node that writes to the DB.**

In one SQLite transaction, Commit:

1. Advances `campaigns.world_time_minutes` (from `pending_world_time_minutes` or `mechanic_result.time_cost_minutes`)
2. Persists `campaigns.world_state_json` (active_factions + party state + news_feed + ledger + **arc_state** + throttling state + **known_npcs** + **companion_memories** + **era_summaries** + **opening_beats** + **act_outline** + **faction_memory** + **npc_states** + **quest_log** + **fired_moments** + **party_state**)
3. Appends all staged events to `turn_events`
4. Applies projections to normalized tables (`characters`, `inventory`, etc.) via `backend/app/core/projections.py` (alias for `state_reducer.py`)
5. Applies staged encounter-throttle effects (`NPC_INTRODUCTION_RECORDED`, `LAST_LOCATION_UPDATED`)
6. Writes the rendered turn transcript (`rendered_turns`) with `suggested_actions` from the ChoiceCrafter pipeline
7. Persists episodic memories to `episodic_memories` table
8. Updates `known_npcs` (present NPCs become known after commit)
9. Persists era transitions and era summaries when detected
10. Processes quest tracker (`process_quests_for_turn()`) and updates `quest_log`
11. Upserts truth ledger facts via `truth_ledger.upsert_facts()`

After commit, it reloads and returns a refreshed `GameState` from the DB so the API response is consistent with persisted data.

**V7.0 post-commit operations:**
12. Writes a turn snapshot to `turn_snapshots` table (rewind support)
13. Checks and records canon events for Historical mode campaigns via `canon_scheduler.py`
14. Processes consequence propagation via `consequence_propagator.py` (ripple/wave/tsunami tiers)
15. Runs deferred maintenance agents via `deferred_agents.py`:
    - `MemoryAgent` — long-term memory management
    - `QuestWeaverAgent` — quest narrative generation (on maintenance turns)
    - `ProgressionAgent` — player/story progression tracking (on maintenance turns)
    - `PsychArchivistAgent` — psychology profile updates (on maintenance turns)
    - `RevelationAgent` (V10.0) — evaluates hidden information and queues revelations (every 5 turns)
    - `CallbackCrystallizerAgent` (V10.0) — identifies peak moments and stores callback seeds (every 10 turns)
    - `PlayerProfileAgent` (V10.0) — analyzes player choice patterns, deterministic (every 10 turns, min 10 turns)
    These agents write to the `pending_world_state_patches` table rather than directly modifying world state. Patches are applied on the next turn load via `apply_pending_patches()`.
16. Records choice metadata in `world_state["choice_history"]` for player behavioral profiling (V10.0)

---

## State Flow Summary (Key Fields)

Most fields are defined in `backend/app/models/state.py`.

| Key | Set By | Notes |
| ----- | -------- | ------ |
| `intent`, `route`, `action_class`, `router_output` | Router | Security routing (META/TALK/ACTION) |
| `mechanic_result` | Router (TALK) or Mechanic (ACTION) | TALK uses a synthesized result (time cost only) |
| `present_npcs`, `spawn_events`, `throttle_events`, `active_rumors` | Encounter | `spawn_events`/`throttle_events` are committed later |
| `pending_world_time_minutes`, `world_sim_*`, `new_rumors` | WorldSim | WorldSim is pure (no DB writes) |
| `arc_guidance.fired_moments_beats`, `arc_guidance.scene_instructions` | Moments Node (V5.0) | Prepended to scene instructions for Director |
| `arc_guidance` | Arc Planner | Arc stage, tension, hero beat, pacing |
| `director_instructions`, `pending_world_time_minutes` | Interlude (V8.0) | Pass-through when not between arcs |
| `scene_frame` | Scene Frame | `topic_primary`, `subtext`, `npc_agenda` |
| `director_instructions` | Director | Text-only pacing instructions for Narrator |
| `shared_kg_character_context`, `shared_episodic_memories` | Director | Shared for Narrator (avoids duplicate retrieval) |
| `campaign.party_*`, `campaign.alignment`, `campaign.faction_reputation`, `campaign.banter_queue` | Companion Reaction | Runs after Director; includes inter-party tensions |
| `suggested_actions` | ChoiceCrafter (V5.0) | 4 LLM-generated choices; `ActionSuggestion` dicts |
| `player_responses` | ChoiceCrafter (V5.0) | `PlayerResponse` dicts for `DialogueTurn` |
| `final_text`, `lore_citations` | Narrator | Prose-only; may append banter; may add warnings |
| `embedded_suggestions` | Narrator | Always `None` |
| `player_starship` | State Loader / Commit | `dict` or `None`; earned in-story |
| `known_npcs` | State Loader / Commit | `list[str]` of NPC IDs the player has encountered |
| `creative_deviation` (V10.0) | Router | `True` if free-text input doesn't match any suggested action |
| `warnings`, `context_stats` | Multiple nodes | Warnings surfaced in `TurnResponse.warnings` |
| `__runtime_conn` | `run_turn()` | Non-serializable runtime handle; never persisted |

## AgentFailureError Handling (V5.0)

```python
# backend/app/core/graph.py:run_turn()

try:
    result = _get_compiled_graph().invoke(initial)
except AgentFailureError as afe:
    # Return GameState with error surfaced to player
    error_dict["final_text"] = f"[SYSTEM] A narrative agent failed: {afe.agent_name}. ..."
    error_dict["suggested_actions"] = []
    error_dict["warnings"] += [f"[AGENT_FAILURE] {afe.agent_name}: {afe.original_error}"]
    return dict_to_state(error_dict)
```

The `authoritative_call()` utility in `error_handling.py` wraps agent calls with:
- 2 attempts (1 retry on any exception)
- Raises `AgentFailureError` if both fail
- Currently used by: `ChoiceCrafterNode` (and can be applied to other authoritative agents)
