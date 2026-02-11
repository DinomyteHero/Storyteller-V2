# Storyteller AI - Comprehensive Engineering Review (V2.5)

> Note: the filename is historical. This document reflects the **current** repo state.

**Date (review):** 2026-02-01  
**Last updated:** 2026-02-05  
**Reviewer:** Senior Staff Engineer (LLM-assisted)  
**Scope:** Full repo - architecture, story quality, performance, reliability, documentation readiness

---

## 1) Executive Summary

- **Architecture is coherent and navigable.** V2.5 is a LangGraph pipeline (`backend/app/core/graph.py`) with node implementations in `backend/app/core/nodes/`, and a clear persistence boundary (Commit node only).
- **The core loop is wired end-to-end.** `POST /v2/campaigns/{campaign_id}/turn` (`backend/app/api/v2_campaigns.py`) loads state from SQLite, runs the graph, commits all events/projections/transcript in one transaction, refreshes state, and returns a strict UI response contract.
- **Director + Narrator are LLM-driven with deterministic fallbacks.** Both agents run through Ollama via `backend/app/core/agents/base.py:AgentLLM`. JSON outputs use `backend/app/core/json_reliability.py` and degradations surface via `warnings`.
- **RAG performance is addressed via caching.** SentenceTransformer encoder and LanceDB connections/tables are cached in `backend/app/rag/_cache.py` (shared by lore/style/voice retrievers).
- **Determinism is preserved where it matters.** Router + Mechanic + Companion reactions are deterministic; simulation and LLM nodes have safe fallbacks.
- **Documentation is organized and current.** Root-level docs plus `docs/00-09` form a review-friendly set.

---

## 2) Architecture Overview

### Runtime stack

- **UI:** Streamlit (`streamlit_app.py`) using `ui/api_client.py`
- **API:** FastAPI (`backend/main.py`) exposing V2 endpoints in `backend/app/api/v2_campaigns.py`
- **State/Persistence:** SQLite event sourcing + projections (`backend/app/core/event_store.py`, `backend/app/core/projections.py`, `backend/app/core/state_loader.py`)
- **RAG:** LanceDB (`data/lancedb/`) accessed via `backend/app/rag/*`
- **LLM:** Ollama-only, per-role config in `backend/app/config.py`

### Core turn loop (high level)

```
UI -> POST /v2/campaigns/{id}/turn
  -> build_initial_gamestate()            (SQLite read)
  -> run_turn()                          (LangGraph)
      router -> (meta | mechanic) -> encounter -> world_sim
             -> companion_reaction -> director -> narrator -> commit
  -> commit node                          (SQLite writes: events + projections + transcript)
  -> refresh state + return TurnResponse
```

### Key invariants (by design)

- **Commit-only writes:** All DB mutations happen in `backend/app/core/nodes/commit.py`.
- **Runtime DB handle:** Nodes that need DB access read `state["__runtime_conn"]`; the handle is stripped before returning a `GameState`.
- **Ollama-only:** `AgentLLM` supports only `provider=ollama`.

---

## 3) Current Findings (Open Items)

This section lists the notable, code-evidenced issues that remain **open** as of 2026-02-05. For the canonical living list, also see `docs/07_known_issues_and_risks.md`.

| # | Finding | Impact | Recommendation | Effort |
|---|---------|--------|----------------|--------|
| M1 | No auth + wide-open CORS (`backend/main.py`) | Unsafe if exposed beyond localhost | Add auth, restrict CORS origins, and consider per-campaign access control | M |
| M2 | Streamlit redundant state fetches (`streamlit_app.py`) | Extra HTTP/SQLite round-trips and UI latency | Cache state once per render in `st.session_state`; invalidate on new turn | S |
| L1 | Schema check per request (`backend/app/api/v2_campaigns.py:_get_conn`) | Small perf overhead | Move schema application to startup or a one-time guard | S |
| L2 | Mechanic "choice impact" deltas empty (`backend/app/core/agents/mechanic.py`) | Alignment/faction/affinity shifts rely mainly on heuristics/tone tags | Populate deltas for key action types and outcomes (tuning task) | M |
| L3 | Duplicate static NPC cast templates (legacy path) | Divergence risk if Bible casting disabled | Consolidate into one shared source or remove the legacy path | S |
| L4 | Single-writer assumption in Commit node | Concurrency hazards if multi-session ever added | Add optimistic locking/version checks if concurrency becomes a goal | M |
| T1 | `now_iso()` helper unused (`backend/app/core/agents/base.py`) | Minor dead code | Delete or reintroduce a call site (keep repo tidy) | S |

---

## 4) Recently Resolved (No Longer Findings)

- **Director suggestions are LLM-driven** with JSON reliability + validation (`backend/app/core/agents/director.py`).
- **Token budgeting is consistently applied** to both Director and Narrator (`backend/app/core/context_budget.py`).
- **RAG caching is in place** for encoder + LanceDB handles (`backend/app/rag/_cache.py`).
- **Character voice retrieval is filtered** (no full table scan) (`backend/app/rag/character_voice_retriever.py`).
- **Warnings are surfaced to the UI contract** (`TurnResponse.warnings` in `backend/app/api/v2_campaigns.py`).
- **Test suite exists** (`pytest.ini`, plus tests under `tests/` and `ingestion/`).

---

## 5) Review Guide (for external reviewers)

Suggested reading order:

1. `README.md` (what it is + repo map + key commands)
2. `QUICKSTART.md` (how to run locally)
3. `ARCHITECTURE_V2_5.md` (design intent + invariants)
4. `API_REFERENCE.md` (V2 response contract)
5. `docs/02_turn_lifecycle.md` + `docs/03_state_and_persistence.md` (execution + persistence)
6. `docs/07_known_issues_and_risks.md` (current open items)

Suggested technical review areas:

- **Correctness:** Commit-only-writes boundary and event/projection correctness (`backend/app/core/nodes/commit.py`)
- **Safety:** guardrails in Router/Mechanic/Narrator prompts; warnings and fallbacks
- **Performance:** RAG caching and UI request patterns
- **Maintainability:** node split (`backend/app/core/nodes/`), test coverage, and docs accuracy

---

## 6) Recommended Roadmap (Next 2-4 Iterations)

1. **UI latency:** cache state per render in Streamlit; reduce redundant API calls.
2. **Deployment hardening:** add auth + narrow CORS (even a simple token gate if needed).
3. **Mechanic impact tuning:** populate alignment/faction/affinity deltas and validate companion reactions.
4. **Startup hygiene:** move schema checks to startup; add a single "boot" command path.
5. **Optional quality:** improve token estimation and/or add reranking if retrieval relevance becomes an issue.

