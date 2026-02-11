# 08 — Alignment Checklist

Use this checklist to validate whether the implementation matches the intended Storyteller AI V2.15 design goals.

Legend:
- ✅ Implemented
- ⚠️ Partial
- ❌ Not implemented / deferred

---

## Core Architecture

| # | Goal | Status | Evidence |
|---|------|--------|----------|
| A1 | LangGraph pipeline orchestration | ✅ | `backend/app/core/graph.py` (`build_graph`, `run_turn`) |
| A2 | Pipeline order: Router → (Meta or Mechanic) → Encounter → WorldSim → CompanionReaction → ArcPlanner → Director → Narrator → NarrativeValidator → Commit | ✅ | `backend/app/core/graph.py` edges; node impls in `backend/app/core/nodes/` |
| A3 | Single transaction boundary (Commit only writer) | ✅ | `backend/app/core/nodes/commit.py` |
| A4 | Graph compiled once (lazy singleton) | ✅ | `backend/app/core/graph.py:_get_compiled_graph()` |
| A5 | DB connection not captured in closures | ✅ | `run_turn()` injects `__runtime_conn`; nodes read it at invocation time |

---

## Living World System

| # | Goal | Status | Evidence |
|---|------|--------|----------|
| L1 | Every turn has a time cost (minutes) | ✅ | `backend/app/time_economy.py`, `backend/app/core/agents/mechanic.py` |
| L2 | WorldSim triggers on tick-boundary crossing | ✅ | `backend/app/core/nodes/world_sim.py:world_sim_tick_crosses_boundary()` |
| L3 | WorldSim triggers on travel | ✅ | `backend/app/core/nodes/world_sim.py` travel detection |
| L4 | WorldSim produces rumors + faction moves + optional updates | ✅ | `backend/app/core/agents/architect.py` (`simulate_off_screen`) |
| L5 | ME-style news feed derived from rumors | ✅ | `backend/app/models/news.py:rumors_to_news_feed()` |
| L6 | Deterministic faction engine (zero LLM, seeded RNG) | ✅ | `backend/app/world/faction_engine.py` |
| L7 | Era transitions | ✅ | `backend/app/core/era_transition.py` |

---

## Mechanic + Routing

| # | Goal | Status | Evidence |
|---|------|--------|----------|
| M1 | Deterministic mechanic (no LLM) | ✅ | `backend/app/core/agents/mechanic.py` |
| M2 | Router guardrails prevent mechanic bypass | ✅ | `backend/app/core/router.py` + `backend/app/core/nodes/router.py` |
| M3 | Only dialogue-only can skip Mechanic | ✅ | `backend/app/core/nodes/router.py` (TALK gating) |

---

## LLM Provider (Ollama-only)

| # | Goal | Status | Evidence |
|---|------|--------|----------|
| P1 | Per-role model configuration | ✅ | `backend/app/config.py` (`MODEL_CONFIG`) |
| P2 | Ollama-only provider enforcement | ✅ | `backend/app/core/agents/base.py` |
| P3 | JSON mode + deterministic repair retry | ✅ | `backend/app/core/agents/base.py` |

---

## RAG + Context Budgeting

| # | Goal | Status | Evidence |
|---|------|--------|----------|
| R1 | LanceDB-backed lore retrieval with metadata filters | ✅ | `backend/app/rag/lore_retriever.py` |
| R2 | Style retrieval (4-lane: Base SW + Era + Genre + Archetype) | ✅ | `backend/app/rag/style_retriever.py`, `backend/app/rag/style_mappings.py` |
| R3 | Retrieval bundles per agent role | ✅ | `backend/app/rag/retrieval_bundles.py` |
| R5 | Token-aware context trimming | ✅ | `backend/app/core/context_budget.py` (used by Director + Narrator agents) |
| R6 | Caching of encoder + LanceDB handles | ✅ | `backend/app/rag/_cache.py` |

---

## Companion System (Deep)

| # | Goal | Status | Evidence |
|---|------|--------|----------|
| C1 | Party seeding + trait storage | ✅ | `backend/app/core/companions.py` (`build_initial_companion_state`) |
| C2 | Affinity + loyalty progression | ✅ | `backend/app/core/companion_reactions.py` |
| C3 | Banter queue (rate-limited, 17 banter styles) | ✅ | `backend/app/core/companion_reactions.py` + `backend/app/constants.py` (BANTER_POOL) |
| C4 | Alignment + faction reputation tracking | ✅ | `backend/app/core/companion_reactions.py` |
| C5 | Companion-initiated events (REQUEST, QUEST, CONFRONTATION) | ✅ | `backend/app/core/companion_reactions.py` |
| C6 | Inter-party tensions (opposing reactions trigger tension context) | ✅ | `backend/app/core/companion_reactions.py:compute_inter_party_tensions()` |
| C7 | 108 companions with metadata (species, voice_tags, motivation, speech_quirk) | ✅ | `data/companions.yaml` |

---

## Director + Narrator (V2.15)

| # | Goal | Status | Evidence |
|---|------|--------|----------|
| D1 | KOTOR dialogue wheel (4 deterministic suggestions per turn) | ✅ | `backend/app/core/agents/director.py:generate_suggestions()`, `backend/app/core/action_lint.py` |
| D2 | Prose-only Narrator (no embedded suggestions) | ✅ | `backend/app/core/agents/narrator.py` (`embedded_suggestions=None` always) |
| D3 | Narrator prose: 5-8 sentences, max 250 words | ✅ | `backend/app/core/agents/narrator.py:_truncate_overlong_prose()` |
| D4 | Post-processing strips structural artifacts | ✅ | `backend/app/core/agents/narrator.py:_strip_structural_artifacts()` |
| D5 | Gender/pronoun system | ✅ | `backend/app/core/pronouns.py`, `backend/app/db/migrations/0015_add_gender.sql` |

---

## Arc Planning + Story Structure

| # | Goal | Status | Evidence |
|---|------|--------|----------|
| S1 | Hero's Journey arc planner with beats | ✅ | `backend/app/core/nodes/arc_planner.py` |
| S2 | Genre triggers | ✅ | `backend/app/core/genre_triggers.py` |
| S3 | Era transitions | ✅ | `backend/app/core/era_transition.py` |
| S4 | Episodic memory for long-term recall | ✅ | `backend/app/core/episodic_memory.py`, `backend/app/db/migrations/0014_episodic_memories.sql` |
| S5 | NPC personality profiles | ✅ | `backend/app/core/personality_profile.py` |

---

## Starship System

| # | Goal | Status | Evidence |
|---|------|--------|----------|
| V1 | Starship acquisition (quest/purchase/salvage/faction/theft) | ✅ | `backend/app/api/starships.py`, `backend/app/models/starship.py`, `backend/app/db/migrations/0017_starships.sql` |
| V2 | STARSHIP_ACQUIRED event + projections | ✅ | `backend/app/core/projections.py` |

---

## Ingestion Pipeline

| # | Goal | Status | Evidence |
|---|------|--------|----------|
| I1 | Hierarchical parent/child chunking (PDF/EPUB/TXT) | ✅ | `ingestion/ingest_lore.py` |
| I2 | Flat chunking (TXT/EPUB) | ✅ | `ingestion/ingest.py` |
| I3 | Optional ingestion tagger (LLM enrichment) | ✅ | `ingestion/tagger.py` (guarded by `INGESTION_TAGGER_ENABLED`) |
| I4 | Run manifest per ingest | ✅ | `ingestion/manifest.py` + `data/manifests/` |

## Warnings System

| # | Goal | Status | Evidence |
|---|------|--------|----------|
| W1 | Collect turn-level warnings | ✅ | `backend/app/core/warnings.py:add_warning()` |
| W2 | Surface warnings in the API response | ✅ | `backend/app/api/v2_campaigns.py` (`TurnResponse.warnings`) |

---

## Test Coverage (Regression Gates)

467+ tests passing (Feb 2026), 2 skipped (RAG cache tests need LanceDB).

| Area | Status | Evidence |
|------|--------|----------|
| Router/mechanic/world sim/ledger | ✅ | `backend/tests/test_router.py`, `test_ledger.py`, `test_world_sim.py` |
| RAG caching + retrieval | ✅ | `backend/tests/test_rag_cache.py` |
| Companion system (deep) | ✅ | `backend/tests/test_companion_deep.py`, `test_companion_metadata.py` |
| Embedded suggestions | ✅ | `backend/tests/test_embedded_suggestions.py` |
| Arc planner + dynamic arcs | ✅ | `backend/tests/test_arc_planner.py`, `test_dynamic_arc.py` |
| Genre triggers | ✅ | `backend/tests/test_genre_triggers.py` |
| Faction engine | ✅ | `backend/tests/test_faction_engine.py` |
| Personality profiles | ✅ | `backend/tests/test_personality_profile.py` |
| Starship acquisition | ✅ | `backend/tests/test_starship_acquisition.py` |
| Style layered retrieval | ✅ | `backend/tests/test_style_layered_retrieval.py` |
| Director suggestions | ✅ | `backend/tests/test_director_suggestions.py` |
| Narrator voice guardrail | ✅ | `backend/tests/test_narrator_voice_guardrail.py` |
| Ingestion | ✅ | `ingestion/test_*.py` |
| CLI smoke | ✅ | `tests/test_cli.py` |
