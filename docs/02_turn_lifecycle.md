# 02 — Turn Lifecycle

## Overview

A single turn flows through a LangGraph `StateGraph` that is compiled once on first use (see `backend/app/core/graph.py`). The pipeline is invoked by `run_turn(conn, state)`, which injects the SQLite connection as `state["__runtime_conn"]` and strips it after graph execution.

## Pipeline Topology

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
    WORLDSIM --> COMPANION[Companion Reaction Node]
    COMPANION --> ARCPLAN[Arc Planner Node]
    ARCPLAN --> DIRECTOR[Director Node]
    DIRECTOR --> NARRATOR[Narrator Node]
    NARRATOR --> VALIDATOR[Narrative Validator Node]
    VALIDATOR --> REFINER[Suggestion Refiner Node]
    REFINER --> COMMIT

    COMMIT --> END_NODE([Return GameState])

    style ROUTER fill:#f9f,stroke:#333
    style COMMIT fill:#ff9,stroke:#333
    style WORLDSIM fill:#9ff,stroke:#333
    style ARCPLAN fill:#cfc,stroke:#333
    style VALIDATOR fill:#fcf,stroke:#333
    style REFINER fill:#ffc,stroke:#333
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

**Output keys set:**

- `intent`, `route`, `action_class`, `intent_text`, `router_output`
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
  - If `ENABLE_BIBLE_CASTING=1`, chooses NPCs deterministically from Era Packs (`data/static/era_packs/*`).
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

**File:** `backend/app/core/nodes/world_sim.py` (calls `backend/app/core/agents/architect.py`)

**Purpose:** Run off-screen simulation on tick-boundary crossing or travel.

**Trigger logic:**

- Let `t0 = campaign.world_time_minutes` and `dt = mechanic_result.time_cost_minutes` and `t1 = t0 + dt`.
- Run WorldSim when:
  - tick boundary crossed: `floor(t0/tick_minutes) != floor(t1/tick_minutes)`, where `tick_minutes = WORLD_TICK_INTERVAL_HOURS*60` (default 240), **or**
  - travel occurred (MOVE event or `action_type == "TRAVEL"`).

**When triggered:**

- Loads current `active_factions` from DB (`campaigns.world_state_json.active_factions`).
- Calls `CampaignArchitect.simulate_off_screen(...)`.
- Produces:
  - `world_sim_events` (hidden faction moves / plot ticks)
  - `world_sim_rumors` as public rumor events (`is_public_rumor=true`)
  - `world_sim_factions_update` (new `active_factions` list to persist)
  - `campaign.news_feed` (ME-style briefing, derived from rumors)
  - `faction_memory` updates (multi-turn plan tracking)
  - `npc_states` updates (20% movement chance per tick, faction-aware goals)
- Always sets `pending_world_time_minutes = t1` for Commit.

---

### 5) Companion Reaction

**File:** `backend/app/core/nodes/companion.py` (uses `backend/app/core/companion_reactions.py`)

**Purpose:** Deterministic party/alignment/faction updates + banter + inter-party dynamics.

- Applies alignment + faction reputation deltas (currently derived from tone tags and heuristics).
- Updates `party_affinity`, `loyalty_progress`, and queues 0-1 banter lines from BANTER_POOL (17 styles).
- May enqueue a short "news banter" line based on briefing items.
- **Inter-party tensions:** `compute_inter_party_tensions()` detects opposing reactions among companions and generates tension context for Director/Narrator.
- **Companion-initiated events:**
  - `COMPANION_REQUEST` at TRUSTED loyalty level
  - `COMPANION_QUEST` at LOYAL loyalty level
  - `COMPANION_CONFRONTATION` on sharp affinity drop
- Companion reactions summary (`companion_reactions_summary`) injected into campaign for Narrator context.

No DB access. No LLM calls.

---

### 6) Director

**File:** `backend/app/core/nodes/director.py` (agent in `backend/app/core/agents/director.py`)

**Purpose:** Pacing instructions (text-only) + deterministic suggestion generation.

The Director generates **text-only scene instructions** for the Narrator. No JSON schema, no suggestion generation in the LLM call. Suggestions are 100% deterministic.

- Uses RAG (4-lane style retrieval):
  - `retrieve_style_layered()` from `backend/app/rag/style_retriever.py` — Base SW (always-on) + Era + Genre + Archetype lanes
  - Adventure hook lore (`backend/app/rag/lore_retriever.py` with `doc_type=adventure`, `section_kind=hook`)
  - KG context from `backend/app/rag/kg_retriever.py`
- Uses `personality_profile` blocks for NPC characterization in scene instructions.
- Uses episodic memories (`shared_episodic_memories`) for narrative continuity.
- Uses `known_npcs` for per-NPC naming (name if known, descriptive role if not).
- **Deterministic suggestions:** Calls `generate_suggestions(state, mechanic_result)` from `director_validation.py`:
  - Produces exactly 4 KOTOR-style options based on game state, mechanic results, present NPCs, and scene context.
  - Post-combat: success/failure branches. Post-stealth: success/failure branches.
  - Exploration suggestions (`_exploration_suggestions()`) for no-NPC scenes.
  - High-stress calming option when `stress > 7`.
  - `classify_suggestion()` assigns tone (PARAGON/INVESTIGATE/RENEGADE/NEUTRAL), risk (SAFE/RISKY/DANGEROUS), and category.
  - `ensure_tone_diversity()` re-tags NEUTRAL suggestions to fill PARAGON/INVESTIGATE/RENEGADE gaps.
- Runs `ActionLint` to remove invalid suggestions (missing NPCs/items, travel-in-combat, etc.) and pads to exactly 4.
- Adds turn warnings when it has to fallback, trim context, or lint/pad actions.

**Output keys set:** `director_instructions`, `suggested_actions`, `warnings`

---

### 7) Narrator

**File:** `backend/app/core/nodes/narrator.py` (agent in `backend/app/core/agents/narrator.py`)

**Purpose:** Final prose narration (prose-only, no suggestions).

The Narrator writes **only prose** (5-8 sentences, max 250 words). `embedded_suggestions` is always `None`. The `_prose_stop_rule` instructs the LLM to stop after the last narrative sentence.

- Uses RAG:
  - Lore chunks (`doc_type in {novel, sourcebook}`, `section_kind in {lore, location, faction}`)
  - Character voice snippets (`backend/app/rag/character_voice_retriever.py`) — era-scoped
- Uses token budgeting (`backend/app/core/context_budget.py`) and emits warnings when trimming occurs.
- Uses companion reactions summary and inter-party tension context from Companion Reaction node.
- Appends one queued banter line if not in high-stakes combat.
- Applies a deterministic canon/voice guardrail that softens risky "new fact" claims when unsupported.
- **Post-processing pipeline:**
  - `_strip_structural_artifacts()` catches 12+ patterns:
    - "Option N (Tone):" inline choice blocks
    - Meta-game sections: Scene Continuation, Potential Complications, Next Steps, Stress Level Monitoring
    - Character sheet fields: Name:, Species:, Class:, Traits:, etc.
    - "Regardless of player choice" sections
  - `_truncate_overlong_prose()` caps at 250 words, breaks at sentence boundary.
  - `_enforce_pov_consistency()` strips meta-narrator endings ("What will you do?", "The choice is yours", etc.).
  - `_flag_unknown_entities()` warns on hallucinated NPC names not in `present_npcs`.
- Gender-aware: Pronoun blocks injected via `pronouns.py`.
- NPC emotional reactions: body language, facial expressions, surprise reactions required in prompt.
- Mechanic action narration: combat/stealth/intimidation actions narrated, not skipped to aftermath.

**Output keys set:** `final_text`, `lore_citations`, `embedded_suggestions` (always `None`), `campaign` (banter queue consumed), `warnings`

---

### 8) Narrative Validator

**File:** `backend/app/core/nodes/narrative_validator.py`

**Purpose:** Deterministic post-narration checks.

- Validates narrative consistency against mechanic outcomes.
- Checks potential contradictions against ledger constraints.
- Appends non-blocking warnings/notes (`validation_notes`, `warnings`); does not halt the turn.

---

### 9) Suggestion Refiner (V2.16)

**File:** `backend/app/core/nodes/suggestion_refiner.py`

**Purpose:** LLM-based refinement of player action suggestions using the Narrator's prose.

After the Narrative Validator, the Suggestion Refiner reads the Narrator's `final_text` and scene context (location, present NPCs, mechanic outcome) to generate 4 scene-aware KOTOR-style action suggestions that respond to what actually happened in the prose. Uses `qwen3:4b` (lightweight, ~2-5s latency).

- Feature-flagged via `ENABLE_SUGGESTION_REFINER` (default: `True`)
- When disabled or on any failure, the deterministic suggestions from the Director node are used unchanged
- 3-layer fallback: AgentLLM JSON retry -> node-level validation (tone/label checks) -> deterministic suggestions survive on failure
- Output passes through `classify_suggestion()`, `ensure_tone_diversity()`, and `lint_actions()` for consistency

**Output keys set:** `suggested_actions` (overrides Director's deterministic suggestions with scene-aware alternatives)

---

### 10) Commit (Single Transaction Boundary)

**File:** `backend/app/core/nodes/commit.py`

**Purpose:** **The only node that writes to the DB.**

In one SQLite transaction, Commit:

1. Advances `campaigns.world_time_minutes` (from `pending_world_time_minutes` or `mechanic_result.time_cost_minutes`)
2. Persists `campaigns.world_state_json` (active_factions + party state + news_feed + ledger + **arc_state** + throttling state + **known_npcs** + **companion_memories** + **era_summaries** + **opening_beats** + **act_outline** + **faction_memory** + **npc_states**)
3. Appends all staged events to `turn_events`
4. Applies projections to normalized tables (`characters`, `inventory`, etc.)
5. Applies staged encounter-throttle effects (`NPC_INTRODUCTION_RECORDED`, `LAST_LOCATION_UPDATED`)
6. Writes the rendered turn transcript (`rendered_turns`) with `suggested_actions` from the deterministic pipeline
7. Persists episodic memories to `episodic_memories` table
8. Updates `known_npcs` (present NPCs become known after commit)
9. Persists era transitions and era summaries when detected

After commit, it reloads and returns a refreshed `GameState` from the DB so the API response is consistent with persisted data.

---

## State Flow Summary (Key Fields)

Most fields are defined in `backend/app/models/state.py`.

| Key | Set By | Notes |
| ----- | -------- | ------ |
| `intent`, `route`, `action_class`, `router_output` | Router | Security routing (META/TALK/ACTION) |
| `mechanic_result` | Router (TALK) or Mechanic (ACTION) | TALK uses a synthesized result (time cost only) |
| `present_npcs`, `spawn_events`, `throttle_events`, `active_rumors` | Encounter | `spawn_events`/`throttle_events` are committed later |
| `pending_world_time_minutes`, `world_sim_*`, `new_rumors` | WorldSim | WorldSim is pure (no DB writes) |
| `campaign.party_*`, `campaign.alignment`, `campaign.faction_reputation`, `campaign.banter_queue` | Companion Reaction | Pure; includes inter-party tensions |
| `director_instructions`, `suggested_actions` | Director | Deterministic; linted/padded to 4; may add warnings |
| `final_text`, `lore_citations` | Narrator | Prose-only; may append banter; may add warnings |
| `embedded_suggestions` | Narrator | Always `None` in V2.15 (suggestions are deterministic via Director) |
| `player_starship` | State Loader / Commit | `dict` or `None`; earned in-story (V2.10) |
| `known_npcs` | State Loader / Commit | `list[str]` of NPC IDs the player has encountered |
| `shared_kg_*` | Director | KG context retrieved for prompt grounding |
| `shared_episodic_memories` | Director | Episodic memories retrieved for narrative continuity |
| `warnings`, `context_stats` | Multiple nodes | Warnings are surfaced in `TurnResponse.warnings` |
| `__runtime_conn` | `run_turn()` | Non-serializable runtime handle; never persisted |
