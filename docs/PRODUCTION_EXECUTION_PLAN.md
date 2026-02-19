# Storyteller-V2 Production Execution Plan

Last updated: February 19, 2026

## Goal

Ship a production-ready build that is:
- behaviorally consistent across streaming and non-streaming paths
- operationally reliable under real player usage
- maintainable with accurate docs, observability, and test gates

## Scope

This plan focuses on production readiness, not feature expansion.

In scope:
- turn-loop correctness
- frontend/backend state consistency
- reliability, observability, security hardening
- release process and quality gates

Out of scope (for this plan):
- major new gameplay systems
- multiplayer
- large UX redesigns

---

## Release Gates (Must Pass)

1. `Correctness Gate`
- Streamed vs non-streamed turn parity validated
- No critical turn-blocking regressions

2. `Quality Gate`
- Backend targeted suites pass
- Frontend tests run in CI
- E2E smoke flow passes: create -> play -> resume -> complete

3. `Ops Gate`
- Structured logs + request IDs + timing telemetry available
- Health detail endpoint reflects real service readiness

4. `Security Gate`
- Auth + CORS + rate limits hardened for production mode
- Input limits enforced on turn endpoints

---

## Phased Execution (4 Weeks)

## Phase 0 (Week 1): Critical Correctness + Source of Truth

### PR-001: SSE pipeline parity fix
Priority: P0  
Owner: Backend  
Files:
- `backend/app/api/v2_campaigns.py`
- `backend/app/core/graph.py`

Implementation:
- Add `moments_node` to `_run_pre_narrator_pipeline()` in the streaming path.
- Verify streamed/non-streamed node sequence parity for ACTION/TALK.
- Add/extend tests to assert moments trigger in both paths.

Acceptance criteria:
- Stream and non-stream produce equivalent state transitions for moments.
- No regression in `/turn_stream` contract.

Validation:
- `pytest backend/tests/test_phase2_core_loop.py -q`
- `pytest backend/tests/test_worldsim_events.py -q`
- Add/execute a focused streaming parity test.

---

### PR-002: Campaign listing source-of-truth unification
Priority: P0  
Owner: Full-stack  
Files:
- `frontend/src/lib/stores/campaigns.ts`
- `frontend/src/routes/+page.svelte`
- `frontend/src/lib/api/campaigns.ts`
- `backend/app/api/v2_campaigns.py` (only if API response needs enrichment)

Implementation:
- Use backend `/v2/campaigns` for load/resume list.
- Keep local storage as optional cache/metadata only.
- Gracefully handle stale/deleted local entries.

Acceptance criteria:
- Fresh browser/device can list campaigns from backend.
- Resume works without pre-existing local registry.
- Saga grouping still works when API data is present.

Validation:
- Manual: create campaign, refresh browser, resume.
- Add frontend test coverage for list/load states.

---

### PR-003: Authoritative failure recovery UX
Priority: P0  
Owner: Full-stack  
Files:
- `backend/app/core/graph.py`
- `frontend/src/routes/play/+page.svelte`

Implementation:
- Standardize failure envelope for narrator/choice-crafter failures.
- Add explicit retry affordance in play UI.
- Ensure last known playable state is preserved.

Acceptance criteria:
- Failure shows actionable message and retry path.
- User is not left in dead-end UI state.

Validation:
- Simulate model-down path; verify recoverability.

---

## Phase 1 (Week 2): Observability + CI + Docs Truth

### PR-004: Turn observability baseline
Priority: P0  
Owner: Backend  
Files:
- `backend/app/core/graph.py`
- `backend/app/core/agents/base.py`
- `backend/main.py`
- `backend/app/api/campaign_models.py`

Implementation:
- Add/standardize request/turn IDs in logs.
- Ensure node timings + llm timings emitted consistently.
- Include a minimal timing payload in response debug contract (guarded if needed).

Acceptance criteria:
- Any turn can be traced end-to-end in logs.
- Timing data available for latency triage.

Validation:
- Run sample turns and inspect structured logs.

---

### PR-005: Frontend tests runnable in CI
Priority: P0  
Owner: Full-stack/DevOps  
Files:
- `.github/workflows/*`
- `frontend/package.json` (if scripts need normalization)

Implementation:
- Ensure frontend dependencies install in CI.
- Run `vitest` in pipeline.
- Add one E2E smoke script (or API+UI integration smoke) in CI.

Acceptance criteria:
- PR checks fail on frontend test regressions.
- E2E smoke job green on main branch.

Validation:
- CI run with intentional failing test to confirm gate behavior.

---

### PR-006: Documentation truth pass
Priority: P0  
Owner: Engineering  
Files:
- `README.md`
- `docs/IMPLEMENTATION_PLAN.md`
- `docs/07_known_issues_and_risks.md`

Implementation:
- Remove stale claims already implemented (choice fallback, streaming refiner mismatch, etc.).
- Align docs with actual runtime behavior and tests.

Acceptance criteria:
- No known contradictions between docs and current code for P0/P1 systems.

Validation:
- Spot-audit doc claims against referenced files/line paths.

---

## Phase 2 (Week 3): Reliability + Security Hardening

### PR-007: Turn idempotency + concurrency guardrails
Priority: P1  
Owner: Backend  
Files:
- `backend/app/api/v2_campaigns.py`
- `backend/app/core/event_store.py`
- Possibly migration for idempotency key persistence

Implementation:
- Add idempotency key support to turn endpoints.
- Protect per-campaign turn submission from duplicate parallel commits.
- Return deterministic response for replayed idempotent requests.

Acceptance criteria:
- Double-submit does not create duplicate turns/events.
- Parallel requests for same campaign are serialized or safely rejected.

Validation:
- Concurrency test with repeated identical requests.

---

### PR-008: Health detail + degraded mode hardening
Priority: P1  
Owner: Backend  
Files:
- `backend/main.py`

Implementation:
- Expand `/health/detail` to include:
  - migration readiness
  - DB mode/checkpoint health
  - vector table readiness
  - model availability summary
- Standardize degraded vs healthy semantics.

Acceptance criteria:
- Health output supports operational dashboards and user-facing banners.

Validation:
- Simulate partial failures (model down, missing vectors) and verify signal quality.

---

### PR-009: Production security defaults
Priority: P1  
Owner: Backend  
Files:
- `backend/main.py`
- related config/env docs

Implementation:
- Ensure production mode requires API token.
- Tighten CORS in production path.
- Add explicit input size limits for `user_input`.
- Verify rate limit policy for `/turn` + `/turn_stream`.

Acceptance criteria:
- Production startup fails fast on unsafe configuration.
- Oversized inputs rejected with clear error.

Validation:
- Targeted API tests for auth/rate/input limits.

---

## Phase 3 (Week 4): Performance Stabilization + Launch Prep

### PR-010: Commit-path latency profiling and tuning
Priority: P1  
Owner: Backend  
Files:
- `backend/app/core/nodes/commit.py`
- `backend/app/constants.py`

Implementation:
- Measure heavy-turn latency by agent segment.
- Tune maintenance cadence/parallelism using real timing data.
- Keep narrative quality stable while reducing p95 latency.

Acceptance criteria:
- Defined latency target met (set baseline, then improve p95 materially).

Validation:
- Before/after timing report on representative turn set.

---

### PR-011: Setting-agnostic UX polish
Priority: P2  
Owner: Frontend  
Files:
- `frontend/src/routes/+page.svelte`

Implementation:
- Remove Star Wars-only landing copy.
- Use setting-neutral language or active setting labels.

Acceptance criteria:
- First-screen messaging aligns with setting-agnostic architecture.

---

### PR-012: Release candidate checklist and runbook
Priority: P1  
Owner: Engineering  
Files:
- `docs/RELEASE_CHECKLIST.md` (new)
- `docs/OPERATIONS_RUNBOOK.md` (new)

Implementation:
- Add reproducible release steps:
  - migrations
  - env validation
  - smoke tests
  - rollback plan
  - incident triage steps

Acceptance criteria:
- New environment can be deployed by following docs only.

---

## Task Board Template

For each PR ticket above, track:
- `Status`: TODO / IN_PROGRESS / REVIEW / DONE
- `Owner`
- `Risk`: Low / Medium / High
- `Dependencies`
- `Test Evidence`
- `Rollback Notes`

---

## Definition of Done (Global)

A ticket is done only when:
1. Code merged
2. Tests added/updated and passing
3. Docs updated
4. Observability added for changed behavior (if runtime-impacting)
5. Manual validation notes captured

---

## Suggested Execution Order

1. PR-001, PR-002, PR-003
2. PR-004, PR-005, PR-006
3. PR-007, PR-008, PR-009
4. PR-010, PR-011, PR-012

---

## Immediate Next Action

Start with `PR-001 (SSE parity)` and `PR-002 (campaign list unification)` first; both directly reduce production risk and user-visible inconsistency.
