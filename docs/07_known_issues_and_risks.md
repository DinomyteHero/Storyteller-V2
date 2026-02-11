# 07 — Known Issues & Risks

This is a **living** list of code-evidenced issues and risks in the current repo state.

---

## Current Issues (Code-Evidenced)

### 1) No Auth + Wide-Open CORS

**Severity:** Medium (high if deployed beyond localhost)
**File:** `backend/main.py`

- No authentication or authorization is implemented.
- CORS allows all origins (`allow_origins=["*"]`).

**Impact:** Any network exposure becomes unsafe without adding auth and restricting CORS.

---

### 2) Schema Check on Every Request

**Severity:** Low (performance)
**File:** `backend/app/api/v2_campaigns.py`

The API helper that opens a connection runs schema application checks (`apply_schema(...)`) per request.

**Impact:** Extra overhead on every request (acceptable for single-user local use; wasteful at scale).

---

### 3) Mechanic "Choice Impact" Deltas Partially Populated

**Severity:** Low (functionality gap / tuning)
**File:** `backend/app/core/agents/mechanic.py`

`MechanicOutput` includes `alignment_delta`, `faction_reputation_delta`, and `companion_affinity_delta`. The `alignment_delta` and `faction_reputation_delta` fields still default to empty dicts in most cases, but `companion_affinity_delta` now works via trait scoring in the companion reaction system.

**Impact:** Alignment and faction reputation changes are driven primarily by deterministic companion-reaction heuristics and tone tags, rather than explicit mechanic outputs. Companion affinity is fully functional through trait-based scoring.

---

### 4) Duplicate Static NPC Cast Definitions (Legacy Path)

**Severity:** Low (maintainability)
**Files:** `backend/app/api/v2_campaigns.py`, `backend/app/core/agents/architect.py`

Both files embed a "12 NPC cast" template for non-Era Pack setups.

**Impact:** Divergence risk if legacy (non-Bible) setup paths are used.

---

### 5) Single-Writer Assumption (No Optimistic Locking)

**Severity:** Low (fine for local-only)
**File:** `backend/app/core/nodes/commit.py`

Commit assumes it is the only writer for a campaign (no version checks).

**Impact:** Concurrent sessions could race and overwrite state if multi-user/multi-process usage is introduced.

---

### 6) Character Facets Not Implemented

**Severity:** Low (feature gap)
**File:** `ingestion/build_character_facets.py`, `backend/app/config.py`

Character facets generation is disabled by default (`ENABLE_CHARACTER_FACETS=0`). The `build_character_facets.py` script produces unusable output and the feature is not wired into the pipeline.

**Impact:** Character voice retrieval works but lacks facet-based personality enrichment. Voice snippets fall back to era-scoped retrieval without facet filtering.

---

### 7) Suggestion Cache Is Basic

**Severity:** Low (optimization opportunity)
**File:** `backend/app/core/suggestion_cache.py`

The suggestion cache uses a one-turn TTL with a simple `(location, arc_stage)` composite key. Suggestions are regenerated every turn even when the scene context has not meaningfully changed.

**Impact:** Minimal for local single-user use, but a more sophisticated cache (e.g., scene-hash key, multi-turn TTL with invalidation on NPC/location change) could reduce redundant computation.

---

## Recently Resolved (No Longer Issues)

- **Director suggestions are 100% deterministic (V2.15)** — no JSON schema, no LLM retries. `generate_suggestions()` uses mechanic results, NPCs, arc stage, and tone for pure-Python suggestion generation.
- **Narrator is prose-only (V2.15)** — no more embedded suggestion extraction failures. Narrator writes 5-8 sentences of prose; `embedded_suggestions=None` always.
- **Companion system is fully functional** — 108 companions with gender, species, voice_tags, motivation, speech_quirk. 17 banter styles (BANTER_POOL). Trait-based affinity scoring, loyalty arcs, companion-initiated events (COMPANION_REQUEST, COMPANION_QUEST, COMPANION_CONFRONTATION).
- **Arc planner tracks Hero's Journey beats** — content-aware stage transitions (SETUP, RISING, CLIMAX, RESOLUTION), hero_beat, archetype_hints, theme_guidance, genre triggers, era transitions.
- **Faction engine is deterministic** — `faction_engine.py` uses zero LLM calls, seeded RNG for faction tick simulation.
- **Gender/pronoun system implemented (V2.8)** — male/female selection with pronoun injection into Director and Narrator prompts via `pronouns.py`.
- **4-lane style retrieval implemented (V2.8)** — Base SW (always-on) + Era + Genre + Archetype lanes in `style_retriever.py`.
- **Episodic memory system** — long-term recall via `episodic_memory.py`, persisted in `episodic_memories` table (migration 0014).
- **Starship acquisition system (V2.10)** — no starting ships; earned in-story via quest/purchase/salvage/faction/theft. STARSHIP_ACQUIRED event handler in projections.
- Token budgeting is applied to both Director and Narrator via `backend/app/core/context_budget.py`.
- SentenceTransformer and LanceDB handles are cached (`backend/app/rag/_cache.py`).
- Character voice retrieval uses filtered vector search (no full-table scan) (`backend/app/rag/character_voice_retriever.py`).
- Turn warnings are surfaced in `TurnResponse.warnings` (`backend/app/api/v2_campaigns.py`).
- `GameState.cleared_for_next_turn()` resets WorldSim fields (`backend/app/models/state.py`).

---

## Future Work (Non-Bugs)

- Add optimistic locking/versioning if concurrent writers are ever supported.
- Add reranking (cross-encoder / hybrid search) if retrieval relevance becomes a bottleneck.
- Replace token estimation heuristics with a tokenizer-based estimate if needed.
- Implement character facets pipeline for personality-enriched voice retrieval.
- Upgrade suggestion cache with scene-hash keys and multi-turn TTL.
