# Implementation Plan: Choice System & Narrative Experience Overhaul

## V11.0 Player Experience — IMPLEMENTED

Three features validated from external review (ChatGPT/Grok), grounded against actual codebase architecture. All three phases implemented and committed.

1. **Universe & Story UX** — Surface existing Settings + Sagas as first-class frontend flow
2. **UI-Exposed Lore Ingestion** — "Add Source Novels" in campaign wizard + Library
3. **Optional Visual Layer** — NPC portraits + location key art (feature-flagged, zero cost when off)

### Naming Convention (UI labels only — no backend renames)

| Backend Term | Player-Facing Term | Meaning |
|-------------|-------------------|---------|
| `setting_id` | **Universe** | A fictional world (Star Wars, LOTR, custom) |
| `saga_id` | **Story** | A player's multi-campaign playthrough within a Universe |
| `period_id` | **Era** | A time slice within a Universe (Rebellion, Dark Times) |
| `campaign_id` | **Chapter** | A single campaign within a Story |

---

### Phase 1: Universe & Story UX (Frontend only — no backend changes)

**What exists:** `sagas` table (migration 0027) with `universe_id`/`player_id`/`title`; `GET /v2/content/catalog` returning `(setting_id, period_id)` pairs; frontend `creation.ts` with `charSettingId`/`charPeriodId`; home page grouping campaigns by saga; `continueSagaContext` session handoff.

**What's missing:** No "Pick your Universe" step before character creation; no saga browser UI; no "Continue last Story" shortcut.

#### Step 1.1: Saga API client
**Create** `frontend/src/lib/api/sagas.ts`
- `listPlayerSagas(playerProfileId)` → `GET /v2/player/{id}/sagas`
- `getSagaDetail(sagaId)` → `GET /v2/sagas/{saga_id}`
- `createSaga(playerProfileId, universeId, title)` → `POST /v2/sagas`

#### Step 1.2: Last-played tracking
**Modify** `frontend/src/lib/stores/campaigns.ts`
- Add `lastPlayedSagaId` and `lastPlayedSettingId` to persisted local state
- Update on campaign load/resume

#### Step 1.3: Home page entry points
**Modify** `frontend/src/routes/+page.svelte`
- Add "Continue Story" button (visible when `lastPlayedSagaId` exists) — loads most recent campaign
- Change "New Campaign" to first show Universe selection before entering existing wizard

#### Step 1.4: Universe selection step in creation wizard
**Modify** `frontend/src/routes/create/+page.svelte`
- Insert Step 0: "Pick your Universe" — card grid of available settings (from catalog, deduplicated by `setting_id`)
- Each card: setting display name, era count, playable badge
- "Create New Universe" card → links to Library EraForge wizard
- If arriving via "Continue Story" (saga context set), skip Step 0 and pre-fill setting/era
- Existing Step 0 (name + era) becomes Step 1, eras filtered to selected Universe

#### Step 1.5: Story-grouped campaign load
**Modify** `frontend/src/routes/+page.svelte` (Load Campaign modal)
- Story card headers: title, Universe label, chapter count, last played date
- Campaigns listed as chapters under each Story
- Ungrouped campaigns under "Standalone Adventures"
- "Start New Chapter" button on each Story card → create with saga context

**Files:** `frontend/src/lib/api/sagas.ts` (NEW), `frontend/src/lib/stores/campaigns.ts` (MOD), `frontend/src/routes/+page.svelte` (MOD), `frontend/src/routes/create/+page.svelte` (MOD), `frontend/src/lib/stores/creation.ts` (MOD)

---

### Phase 2: UI-Exposed Lore Ingestion ("Add Source Novels")

**What exists:** Full ingestion pipeline (`ingestion/ingest_lore.py` — PDF/EPUB/TXT); `POST /v2/library/ingest` with background worker; `GET /v2/library/ingest/{job_id}/status` polling; `ingestion_jobs` table (migration 0035); Library page with upload + status; hierarchical chunking with SHA-256 dedup.

**What's missing:** No `lore_sources` table; Library shows raw chunks not source-level management; no way to delete a single book's chunks; creation wizard doesn't surface ingestion.

#### Step 2.1: `lore_sources` migration
**Create** `backend/app/db/migrations/0038_lore_sources.sql`
```sql
CREATE TABLE IF NOT EXISTS lore_sources (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    filename      TEXT NOT NULL,
    source_type   TEXT DEFAULT 'novel',  -- novel|sourcebook|reference|homebrew
    setting_id    TEXT DEFAULT '',
    period_id     TEXT DEFAULT '',
    chunk_count   INTEGER DEFAULT 0,
    status        TEXT DEFAULT 'pending', -- pending|ingesting|ready|failed
    job_id        TEXT,
    created_at    TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (job_id) REFERENCES ingestion_jobs(id)
);
```

#### Step 2.2: Source CRUD endpoints
**Modify** `backend/app/api/v2_library.py`
- `GET /v2/library/sources` — list sources, optional `?setting_id=` filter
- `GET /v2/library/sources/{source_id}` — single source detail
- `DELETE /v2/library/sources/{source_id}` — delete source + its LanceDB chunks
- Modify `POST /v2/library/ingest` to also create `lore_sources` row linked to `job_id`
- Background worker updates `lore_sources.status` and `chunk_count` on completion

#### Step 2.3: Source-scoped deletion in store
**Modify** `ingestion/store.py`
- Add `delete_by_source(source_title: str)` — filter LanceDB by `source` field, delete matching rows

#### Step 2.4: "Add Reference Material" in creation wizard
**Modify** `frontend/src/routes/create/+page.svelte`
- After Universe selection, add optional step: "Add Reference Material"
  - "No thanks, keep it lightweight" (skip — default)
  - "Add novels now" → inline upload with auto-filled Universe metadata
  - "Add later from Library" → skip
- Job status card: Extracting → Chunking → Embedding → Done
- "Start playing now" available immediately (don't block on ingestion)

#### Step 2.5: Source-based Library
**Modify** `frontend/src/routes/library/+page.svelte`
- Replace chunk-based book list with source-based list from `GET /v2/library/sources`
- Source card: title, type badge, Universe/Era, chunk count, status
- Delete button per source (with confirmation)
- Filter by Universe dropdown

#### Step 2.6: Source API client
**Create** `frontend/src/lib/api/sources.ts`
- `listSources(settingId?)`, `deleteSource(sourceId)`

**Files:** `backend/app/db/migrations/0038_lore_sources.sql` (NEW), `backend/app/api/v2_library.py` (MOD), `ingestion/store.py` (MOD), `frontend/src/routes/create/+page.svelte` (MOD), `frontend/src/routes/library/+page.svelte` (MOD), `frontend/src/lib/api/sources.ts` (NEW)

---

### Phase 3: Optional Visual Layer (Portraits + Key Art)

**Design:** Zero cost when disabled. No LLM calls, no image generation. `ENABLE_PORTRAITS=0` (default) = identical to today. When enabled, serves static images bundled in era packs.

**What exists:** `NPC_RENDER_ENABLED` flag (but for LLM text rendering, not images); `npc_renderer.py` (text intros/dialogue only); `EraBackground.icon` field (unused); frontend is pure text.

#### Step 3.1: Portrait metadata in era pack schema
**Modify** `backend/app/world/era_pack_models.py`
- Add `portrait_key: str | None = None` to `EraCompanionEntry` and `EraNpcEntry`
- Add `key_art: str | None = None` to `EraLocationEntry`
- All optional — `None` = no image rendered

#### Step 3.2: Portrait index + static serving
**Create** `data/static/portraits/` directory:
```
data/static/portraits/
  index.yaml        # {portrait_key: {file, alt_text, credit}}
  companions/       # companion portrait images
  npcs/             # NPC portrait images
  locations/        # location key art images
```

**Modify** `backend/main.py`
- When `ENABLE_PORTRAITS=1`, mount `/portraits` as static file directory
- When disabled, skip mount entirely

#### Step 3.3: Portrait fields in API responses
**Modify** `backend/app/api/campaign_models.py`
- Add `portrait_url: str | None = None` to `PartyStatusItem`
- Add `npc_portraits: dict[str, str] | None = None` to `TurnResponse`
- Add `location_art: str | None = None` to `TurnResponse`
- Resolution: when `ENABLE_PORTRAITS` is true, resolve `portrait_key` → URL; when false, all `None`

#### Step 3.4: Frontend image display
**Modify** `frontend/src/routes/play/+page.svelte`
- Optional location key art banner above narration (if `location_art` non-null)
- Optional companion portrait thumbnails in party status (if `portrait_url` non-null)
- Optional NPC portrait next to encounter text (if `npc_portraits` has entries)
- All guarded by `{#if}` — graceful no-op when null

#### Step 3.5: Feature flag
**Modify** `.env.example` — add `# ENABLE_PORTRAITS=0`
**Modify** `backend/app/config.py` — add `ENABLE_PORTRAITS = _env_flag("ENABLE_PORTRAITS", default=False)`

**Files:** `backend/app/world/era_pack_models.py` (MOD), `backend/app/api/campaign_models.py` (MOD), `backend/app/config.py` (MOD), `backend/main.py` (MOD), `.env.example` (MOD), `data/static/portraits/index.yaml` (NEW), `frontend/src/routes/play/+page.svelte` (MOD)

**No pipeline changes.** Portrait resolution is post-pipeline decoration in the response builder.

---

### Implementation Order

| Phase | Scope | Backend Changes | Frontend Changes |
|-------|-------|----------------|-----------------|
| Phase 1 | Universe & Story UX | None | 5 files (1 new, 4 modify) |
| Phase 2 | Lore Ingestion UI | 1 migration + 2 modified files | 3 files (1 new, 2 modify) |
| Phase 3 | Visual Layer (optional) | 4 modified files + 1 new YAML | 1 modified file |

### What We're NOT Doing (and why)

| Rejected Proposal | Source | Reason |
|------------------|--------|--------|
| RAG influence slider | ChatGPT | Exposes plumbing as UX; 4-lane retrieval handles weighting internally |
| Play while indexing | ChatGPT | Significant state complexity; "start now, add lore later" achieves same goal |
| `universes` DB table | ChatGPT | Duplicates existing `sagas` + `settings` infrastructure |
| Constrained generation overhaul | Grok | Already implemented: `ensure_json()`, `call_json()`, `json_repair.py` (39 occurrences, 19 files) |
| State machine refactor | Grok | Already implemented: `GameState` Pydantic pipeline, event sourcing, Truth Ledger |
| Backend provider abstraction | Grok | Already implemented: `LLMProviderProtocol` with Ollama/Anthropic/OpenAI dispatch |
| AI-generated portraits | - | Costs money per turn; static portraits achieve 90% of visual impact at zero marginal cost |

---

## V10.0 Narrative Intelligence — COMPLETED

Ten features across 4 phases, implementing the narrative skills that separate a good engine from one that feels like a human DM. Design principle: **no new pipeline nodes, no latency impact on turns** — all new intelligence runs as deferred agents (post-commit) or prompt engineering within existing nodes.

| Phase | Features | Description | Status |
|-------|----------|-------------|--------|
| Phase 1 | Features 2, 7, 8 | Director's Toolkit: dramatic irony tags, "Yes, And" engine, narrative rhythm hints | Done |
| Phase 2 | Features 1, 3, 4 | Intelligence Layer: revelation agent, callback crystallizer, player behavioral profiling | Done |
| Phase 3 | Features 5, 9, 10 | Arc-Level Intelligence: foreshadowing hooks, thematic resonance, arc mood profiles | Done |
| Phase 4 | Feature 6 | Companion Depth: NPC wound/reveal layers with 3-tier psychological depth | Done |

Key capabilities added:
- **Dramatic irony** — Hidden world events surfaced as environmental hints to the Director; reader senses danger character doesn't
- **Creative deviation detection** — Free-text that diverges from suggested actions triggers "Yes, And" reward guidance
- **Narrative rhythm** — Prose style adapts: staccato combat, languid exploration, loaded-silence dialogue
- **Revelation timing** — LLM deferred agent queues NPC agendas/faction moves for optimal dramatic reveal (`revelation_queue`)
- **Callback crystallization** — Peak moments captured as `callback_seeds` for future Director echo
- **Player profiling** — Deterministic analysis of choice patterns, play style, and engagement trends (`player_behavior_profile`)
- **Foreshadowing** — SETUP/RISING stages seeded with dangling hooks and NPC secrets from previous arcs
- **Thematic resonance** — CLIMAX stage receives echoes of dominant themes from the campaign's first arc
- **Arc mood profiles** — 5 profiles (heroic, noir, tragic, kishotenketsu, mystery) with per-stage tonal guidance
- **Companion wound/reveal layers** — 3-tier depth (surface/deep/core) unlocked at affinity thresholds in `data/companions.yaml`

New files: `revelation_agent.py`, `callback_crystallizer_agent.py`, `player_profile_agent.py`
Modified files: `constants.py`, `director.py`, `deferred_agents.py`, `arc_planner.py`, `arc_consequence_tracker.py`, `world_sim.py`, `router_node.py`, `commit.py`, `state.py`, `companion.py` (node), `companions.yaml`, `config.py`

---

## V9.0 Novel-Length Storytelling — COMPLETED

Novel-length storytelling and campaign settings support.

---

## V8.0 Road to 1.0 — COMPLETED

All six gates of the Road to 1.0 implementation plan have been completed:

| Gate | Description | Tests | Status |
|------|-------------|-------|--------|
| Gate 1 | Arc Engine: multi-arc chaining, epilogue, interlude, campaign lifecycle | 29 | Done |
| Gate 2 | Memory Pipeline: relevance scoring, NPC prioritization, adaptive truncation, cross-arc bridging | 32 | Done |
| Gate 3 | Player Agency: structured intent passthrough, companion loyalty stakes, choice prompt consistency | 14 | Done |
| Gate 4 | Narrative Coherence: companion presence weaving, prose-choice bridge, tiered scene loop escalation | 15 | Done |
| Gate 5 | Campaign Lifecycle: full 3-arc integration test, edge cases, era data audit | 17 | Done |
| Gate 6 | Ship It: frontend arc progress HUD, campaign completion banner, error recovery verification | -- | Done |

**Total: 107 new tests across 5 test files, 0 regressions.**

Key capabilities added:
- Multi-arc campaigns (2-5 arcs by scale) with interlude scenes between arcs
- Epilogue system (3-turn wind-down) with campaign completion flag
- Relevance-based context trimming (NPC, thread, fact prioritization)
- Cross-arc memory bridging via saga context injection
- Consequence surfacing (wave/tsunami mandatory narrator reference)
- Companion PRESENCE woven directive (replaces appended reaction lists)
- Prose-choice bridge (SCENE ENDING extraction for ChoiceCrafter)
- Tiered scene loop escalation (3 levels: hint → disruption → forced world event)
- Arc progress in TurnResponse (arc_stage, current_arc_number, campaign_complete)
- Frontend campaign completion banner

### Post-1.0 Roadmap
- Novel export (after multi-arc is proven)
- Additional era packs beyond Rebellion
- Companion voice profile enrichment (belief/wound/taboo)
- Centralized faction definitions file
- Lore RAG ingestion for Rebellion era
- Multiple rule systems

---

## Overview (Pre-V8.0 Phases — completed earlier)

Two parallel workstreams addressing the highest-impact pain points discovered during gameplay analysis:

1. **Choice System**: Evolve from rigid KOTOR-tone-first choices to intent-first structured actions
2. **Narrative Experience**: Fix context loss, NPC genericity, and prose-choice disconnection

Priority is ordered by **player-perceived impact** / **implementation effort**.

---

## PHASE 1: Structured Intent Passthrough (Highest Impact, Lowest Effort)

**Goal:** Stop throwing away structured metadata when a player selects a choice. Currently only `display_text` is sent to the backend — the router has to re-infer everything the choice crafter already knew.

### 1.1 Extend the frontend submission payload

**Files:**
- `frontend/src/lib/components/choices/ApproachCards.svelte` — Change `onPopulate` to pass full choice metadata, not just text
- `frontend/src/lib/api/types.ts` — Add `StructuredChoicePayload` type
- `frontend/src/routes/play/+page.svelte` — Modify `handleChoiceInput()` to accept and forward structured data
- `frontend/src/lib/api/campaigns.ts` — Update `runTurn()` and `streamTurn()` to send structured payload

**Changes:**
- When player clicks a choice card, send: `{ user_input: displayText, structured_intent: { tone_tag, meaning_tag, risk_level, action_type, impact_tier } }`
- When player uses free text ("Forge Your Own Path"), send: `{ user_input: text, structured_intent: null }` — router handles classification as before
- Keyboard shortcuts (1-4) also send structured intent

### 1.2 Backend receives and trusts structured intent

**Files:**
- `backend/app/api/v2/turn.py` (or equivalent turn endpoint) — Accept optional `structured_intent` in request body
- `backend/app/core/router.py` — When `structured_intent` is present, skip LLM classification and verb guardrails; construct `RouterOutput` directly from the structured data
- `backend/app/models/state.py` — Add `structured_intent` field to turn request model

**Changes:**
- Router fast-path: if `structured_intent` is not null, map directly:
  - `tone_tag=PARAGON + meaning_tag=reveal_values` → `route=TALK, action_class=DIALOGUE_ONLY`
  - `meaning_tag=set_boundary + risk=DANGEROUS` → `route=MECHANIC, action_class=DIALOGUE_WITH_ACTION`
  - Any `risk_level=RISKY|DANGEROUS` or combat-adjacent meaning → `route=MECHANIC`
- Free text still goes through full router classification (no regression)
- **Confidence = 1.0** for structured choices (eliminates "misunderstood me" for card-based play)

### 1.3 Add intent confirmation for free text

**Files:**
- `frontend/src/routes/play/+page.svelte` — New `showIntentConfirm` state and mini-modal
- `backend/app/api/v2/classify.py` (new, lightweight) — Endpoint that runs router classification without executing the turn
- `frontend/src/lib/api/campaigns.ts` — New `classifyIntent()` API call

**Changes:**
- When player types free text and hits Enter/ACT, call a lightweight `/v2/classify` endpoint
- Show: "I understood this as: **[INVESTIGATE] Search the body for ID** — Submit / Adjust?"
- Player confirms → full turn executes. Player adjusts → they edit and re-submit
- This is optional/toggleable in settings (power users can skip)

---

## PHASE 2: Flexible Choice Generation (Medium Impact, Medium Effort)

**Goal:** Remove the rigid 4-tone constraint. Let scenes generate the choices they need.

### 2.1 Relax choice crafter constraints

**Files:**
- `backend/app/core/agents/choice_crafter_agent.py` — Modify system prompt
- `backend/app/core/nodes/choice_crafter_node.py` — Update validation logic
- `backend/app/core/suggestion_engine.py` — Relax `ensure_tone_diversity()`

**Changes:**
- System prompt: Change "exactly 4 choices, 1 per tone" → "3-6 choices, ensure at least 2 different tones represented. Tone spread is a guideline, not a rigid requirement. Scene context determines what's natural."
- Validation: Accept 3-6 choices. Warn (but don't reject) if fewer than 2 tones present
- Remove the pad-to-4 logic in `_parse_choices()` that appends generic "Consider your options" filler
- Keep the PARAGON/INVESTIGATE/RENEGADE/NEUTRAL vocabulary — it's good shorthand. Just don't force all 4 every turn

### 2.2 Add action-type labels to choices

**Files:**
- `backend/app/core/agents/choice_crafter_agent.py` — Add `action_type` to output schema
- `backend/app/models/dialogue_turn.py` — Add `action_type` field to `PlayerResponse`
- `frontend/src/lib/components/choices/ApproachCards.svelte` — Display action-type tag
- `frontend/src/lib/api/types.ts` — Add `action_type` to `PlayerResponse` type

**Changes:**
- Choice crafter now outputs: `{ text, tone, meaning, risk, action_type, consequence_hint }`
- `action_type` is one of: `TALK`, `DO`, `INVESTIGATE`, `TRAVEL`, `USE_ABILITY`, `WAIT`
- UI shows a small tag prefix on each card: `[TALK]`, `[DO]`, `[INVESTIGATE]`, etc.
- This gives players the "what kind of thing am I doing?" clarity without rebuilding the UI
- Action type feeds directly into structured intent passthrough (Phase 1.1)

### 2.3 Show consequence hints to players

**Files:**
- `frontend/src/lib/components/choices/ApproachCards.svelte` — Already has `card-hint` div, currently hover-only
- `backend/app/models/dialogue_turn.py` — Mark `consequence_hint` as player-visible

**Changes:**
- Make consequence hints always visible on cards (not hover-only)
- Reduce hint text to max 60 chars (currently uncapped)
- This removes the "blind choice" feeling

---

## PHASE 3: Narrative Continuity Fixes (High Impact, Medium Effort)

**Goal:** Fix the "game forgot what happened" problem.

### 3.1 Increase memory windows

**Files:**
- `backend/app/constants.py` — Adjust memory constants
- `backend/app/core/state_loader.py` — Increase recent_narrative limit

**Changes:**
- `NPC_STATES_MAX`: 30 → 60 (prevent NPC forgetting for longer campaigns)
- `MEMORY_MAX_ERA_SUMMARIES`: 20 → 30
- `MEMORY_CRYSTALLIZED_MAX`: 25 → 40
- Recent narrative truncation: 200 words → 400 words per turn
- Recent narrative window: last 2-3 turns → last 4 turns

### 3.2 Run continuity agent more frequently

**Files:**
- `backend/app/constants.py` — `MAINTENANCE_AGENT_FREQUENCY`
- `backend/app/core/nodes/commit.py` — Maintenance scheduling

**Changes:**
- `MAINTENANCE_AGENT_FREQUENCY`: 5 → 3 (run LLM-backed continuity checks every 3 turns instead of 5)
- This closes the "4-turn contradiction window" identified in analysis
- Trade-off: slightly more LLM cost, but significantly better continuity

### 3.3 Improve era summary compression

**Files:**
- `backend/app/core/ledger.py` — `compress_turn_history()` function

**Changes:**
- Current compression only captures: locations, NPCs, items, damage, flags
- Add: relationship changes, key dialogue topics, emotional beats, quest progress
- Format: "Turns 11-20: Built trust with Kira (+15 influence); discovered hidden passage in cantina; Faction X turned hostile after theft; promised to return artifact by dawn"
- This preserves narrative texture, not just mechanical facts

### 3.4 Feed NPC memory into voice retrieval

**Files:**
- `backend/app/core/nodes/narrator.py` — NPC context injection
- `backend/app/core/agents/narrator_prompt.py` — Add NPC memory section

**Changes:**
- When building narrator prompt, include NPC's emotional state and recent memories from `npc_states`
- Format: "NPC MEMORY: Kira [wary, -3 affinity] — last seen Turn 12, remembers: player stole from her shop, player later apologized"
- Narrator can then write dialogue that reflects the relationship history
- This directly addresses "NPCs feel like strangers" pain point

---

## PHASE 4: Prose-Choice Coherence (Medium Impact, Medium Effort)

**Goal:** Make narrated prose lead naturally into available choices.

### 4.1 Feed choice previews back to narrator

**Files:**
- `backend/app/core/graph.py` — Reorder or add feedback step
- `backend/app/core/agents/narrator_prompt.py` — Add choice preview section

**Changes:**
- After choice crafter generates choices, optionally run a **prose polish** step that inserts 1-2 sentences at the end of narration that naturally lead toward the available options
- This is NOT regenerating all prose — it's appending a "bridge" paragraph
- Example: If choices include "investigate the scorch marks" and "confront the guard," the bridge paragraph might mention: "Scorch marks trail along the doorframe. The guard shifts uncomfortably, avoiding your gaze."
- This closes the "prose doesn't relate to my options" gap
- **Implementation note:** This is a lightweight LLM call (~50 tokens of output) that takes the narrator prose + choice texts as input

### 4.2 Fix NPC dialogue anchoring to player input

**Files:**
- `backend/app/core/agents/narrator_prompt.py` — Strengthen player-input requirement

**Changes:**
- Add explicit requirement in narrator system prompt: "The NPC utterance MUST directly respond to or acknowledge the player's stated action: '{user_input}'. If the player asked a question, the NPC answers it. If the player made a demand, the NPC reacts to that demand."
- Inject `user_input` as a separate clearly-labeled field in the narrator context
- This fixes the "NPC has no ears" problem where NPC dialogue ignores what the player said

### 4.3 Make mechanical consistency blocking (not warning-only)

**Files:**
- `backend/app/core/nodes/narrative_validator.py` — Upgrade critical checks from warn to block
- `backend/app/core/nodes/narrator.py` — Handle validator blocks with retry

**Changes:**
- Mechanic consistency check (success/fail contradiction): if validator detects "narrator wrote success but mechanic said fail" (or vice versa), trigger a **targeted rewrite** of the contradicting sentence (not full regeneration)
- This prevents "You succeed" showing when player failed a check — the most immersion-breaking bug

---

## PHASE 5: World Dynamism (Medium Impact, Higher Effort)

**Goal:** Make the world feel alive between player actions.

### 5.1 Inject rumors into prose naturally

**Files:**
- `backend/app/core/agents/narrator_prompt.py` — Add rumor injection block
- `backend/app/core/nodes/world_sim.py` — Expose recent rumors to narrator

**Changes:**
- When `new_rumors` exist in state, add a directive to narrator: "WEAVE this rumor into the scene naturally (overheard conversation, posted notice, NPC mention): '{rumor_text}'"
- This is a "should include," not a hard requirement — narrator adapts to scene
- Rumors stop being invisible state and become narrative texture

### 5.2 Make NPC death propagate to world state

**Files:**
- `backend/app/core/nodes/world_sim.py` — Add death event handler
- `backend/app/core/consequence_propagator.py` — Auto-flag NPC death as "wave" impact

**Changes:**
- When a `DAMAGE` event results in NPC death (HP ≤ 0), automatically:
  1. Create a "wave" consequence
  2. Generate a rumor about the death
  3. Update faction reputation if NPC was faction-affiliated
  4. Set NPC state to dead (immutable fact)
- This makes killing an NPC feel consequential

### 5.3 Scene loop detection using scene_hash

**Files:**
- `backend/app/core/nodes/scene_frame.py` — Use `compute_scene_hash()` for loop detection
- `backend/app/core/nodes/arc_planner.py` — React to scene loops

**Changes:**
- Track last 5 scene hashes in state
- If same hash appears 3+ times, flag `scene_loop_detected`
- Arc planner receives this flag and injects escalation guidance: "Scene is repeating — introduce a new element, interrupt, or force a transition"
- This prevents the "stuck in same conversation" loop

---

## PHASE 6: Companion Presence (Lower Impact, Medium Effort)

**Goal:** Make companions feel like participants, not afterthoughts.

### 6.1 Move companion reactions before narration

**Files:**
- `backend/app/core/graph.py` — Reorder graph nodes
- `backend/app/core/nodes/narrator.py` — Accept companion reactions as input

**Changes:**
- Current flow: Narrator → Companion → inject banter post-hoc
- New flow: Companion → Narrator (companion reactions available during prose generation)
- Narrator can naturally weave companion dialogue into the scene instead of appending it
- This fixes the "banter feels like commentary" problem

### 6.2 Add companion stakes

**Files:**
- `backend/app/core/nodes/companion.py` — Add loyalty breakpoint system
- `backend/app/constants.py` — Define loyalty thresholds

**Changes:**
- Define breakpoints: influence < -30 → companion becomes "reluctant" (won't help with risky plans), influence < -60 → companion threatens to leave, influence < -80 → companion leaves party
- These are signaled in companion_hint to choice crafter, which can generate choices like "Convince Kira to stay"
- Makes companion affinity feel consequential, not decorative

---

## Implementation Order

| Phase | Description | Effort | Impact | Dependencies |
|-------|-------------|--------|--------|--------------|
| 1.1-1.2 | Structured intent passthrough | 2-3 days | Very High | None |
| 1.3 | Free text intent confirmation | 1-2 days | High | 1.1-1.2 |
| 2.1 | Relax choice constraints | 1 day | High | None |
| 2.2 | Action-type labels | 1 day | High | None |
| 2.3 | Visible consequence hints | 0.5 day | Medium | None |
| 3.1 | Increase memory windows | 0.5 day | High | None |
| 3.2 | Frequent continuity checks | 0.5 day | High | None |
| 3.3 | Better era compression | 1 day | Medium | None |
| 3.4 | NPC memory → voice | 1-2 days | High | None |
| 4.1 | Prose-choice bridge | 1-2 days | Medium | 2.1 |
| 4.2 | NPC dialogue anchoring | 0.5 day | High | None |
| 4.3 | Blocking mechanic consistency | 1 day | High | None |
| 5.1 | Rumor injection | 1 day | Medium | None |
| 5.2 | NPC death propagation | 1-2 days | Medium | None |
| 5.3 | Scene loop detection | 1 day | Medium | None |
| 6.1 | Companion before narrator | 1-2 days | Medium | None |
| 6.2 | Companion stakes | 1-2 days | Medium | 6.1 |

**Recommended sprint order:** Phase 1 → Phase 3.1-3.2 → Phase 2 → Phase 4.2-4.3 → Phase 3.3-3.4 → Phase 5 → Phase 4.1 → Phase 6

---

## What We're NOT Doing (and Why)

1. **Full Intent Palette UI rebuild** (ChatGPT's primary suggestion) — Too much UI rework for marginal gain over structured passthrough. The approach cards already work well as a UI pattern.

2. **Removing KOTOR tone vocabulary** — PARAGON/INVESTIGATE/RENEGADE/NEUTRAL is good shorthand that players understand. We keep it as a coloring system, just stop forcing all 4 every turn.

3. **Tab/mode switching** (Talk/Do/Investigate/Travel tabs) — Adds cognitive overhead. Action-type labels on existing cards achieve the same clarity with zero extra clicks.

4. **Tone wheel as primary input** — Already dead in the UI (DialogueWheel.svelte imported but never rendered). No resurrection needed.

5. **Real-time world simulation** — Running world sim every turn is expensive and produces noise. The current tick-boundary approach is fine; we just need better rumor injection and consequence propagation.
