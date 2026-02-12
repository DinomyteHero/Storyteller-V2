# 11 — Architecture & Gameplay Readiness Review (Post-Claude Update)

Date: 2026-02-12  
Scope: backend architecture, ingestion/RAG modularity, production readiness, gameplay and narrative engagement

## Implementation status update

Completed after this review was written:

- `GET /v2/campaigns` resume listing endpoint is implemented.
- `GET /health/detail` structured diagnostics endpoint is implemented.
- Ingestion CLI supports non-interactive `--yes/--non-interactive`.
- Deprecated simple ingestion pipeline is gated by `--allow-legacy`.
- Sprint A vector-store factory migration is implemented across lore/style/voice retrievers.
- Sprint B prompt versioning is implemented for SuggestionRefiner and exposed in `turn_contract.meta.prompt_versions`.

Still pending from this review roadmap:

- Service-layer split for `v2_campaigns`.
- Prompt regression/golden scenario tests beyond registry hashing checks.
- Ingestion SLA metrics + CI gates.
- Phase 2 gameplay loop depth work (consequence hooks, relationship arcs, scene-state suggestion diversity).

---

## Executive assessment

The recent changes materially improved the project:

- Clear direction toward modularity (`VectorStore` protocol, ingestion path helpers, role-specific model/timeout config)
- Better resilience (fallbacks, warnings, startup checks)
- Better deployability (Docker, production env template, runbook)
- Better narrative continuity (NPC memory, guardrails, expanded meaning tags)

**Current status:** the system is close to production-ready for a **single-node/single-writer** deployment, but not yet ready for reliable multi-user production at scale. The largest remaining risks are architectural concentration in a few files, incomplete adapter boundaries, deployment reproducibility drift, and content/prompt operations that are still mostly code-driven instead of data-driven.

---

## What is working well

1. **Pipeline architecture remains coherent.** LangGraph node order and a single commit boundary preserve deterministic mechanics and event-sourcing discipline.
2. **Good safety patterns.** Deterministic fallbacks, structured error handling, and warning surfacing reduce game-breaking failures.
3. **RAG quality direction is strong.** Layered style retrieval + character voice + KG is the right foundation for immersive narrative consistency.
4. **Operational intent exists.** Docker, CI/CD, and startup checks are in place; env templates are much improved.

---

## Key gaps and recommendations

## A) Modularity and architecture boundaries

### A1. Vector DB abstraction is defined but not fully adopted

- `backend/app/rag/vector_store.py` introduces `VectorStore`/`LanceDBStore`, but most retrievers and ingestion paths still call LanceDB directly.
- **Risk:** backend swap will require touching many modules (and likely tests).

**Recommendation (high priority):**

1. Introduce a `VectorStoreFactory` in one place (config-driven backend selection).
2. Refactor retrievers (`lore_retriever`, `style_retriever`, `character_voice_retriever`, `kg/chunk_reader`) to depend on the protocol only.
3. Move all backend-specific filter syntax to adapter classes.
4. Add adapter contract tests that run for all vector backends.

### A2. API layer remains monolithic

- `backend/app/api/v2_campaigns.py` is very large and mixes routing, orchestration, and domain policy.
- **Risk:** high change surface, difficult onboarding, harder reliability improvements.

**Recommendation (high priority):**

- Split into feature routers/services:
  - `setup_service`
  - `turn_service` (stream + sync variants)
  - `campaign_query_service`
  - `content_catalog_service`
- Keep route files thin; isolate logic and dependencies in service modules.

### A3. Legacy and modern ingestion are both exposed

- `ingestion/ingest.py` is deprecated but still wired through CLI (`storyteller ingest --pipeline simple`).
- **Risk:** support burden and inconsistent metadata quality.

**Recommendation (high priority):**

- Make `lore` the only default public path in the next minor release.
- Move `simple` pipeline behind `--allow-legacy` gate.
- Add a migration helper to convert legacy manifests/metadata to the new schema.

---

## B) Production readiness and portability

### B1. Environment and runtime drift still occurs across machines

- Runtime requires Python 3.11+, but local execution can silently use other versions.
- Some tooling remains interactive (CLI prompts), which hurts automation.

**Recommendation (high priority):**

1. Add a one-command non-interactive bootstrap script (`scripts/bootstrap.sh` + `.ps1`) that validates Python, installs deps, copies `.env`, verifies models, checks pack paths.
2. Add `--yes`/`--non-interactive` support to CLI flows that currently prompt.
3. Add `make check`/`task check` command that runs preflight + smoke tests + content checks.

### B2. Docker topology is useful but not yet "prod-safe by default"

- Good baseline compose exists, but production patterns need hardening.

**Recommendation (medium priority):**

- Add compose override for production:
  - read-only root FS where possible
  - explicit resource limits
  - restart/backoff tuning
  - external volume path docs
- Add reverse proxy reference config (TLS, auth headers, compression).
- Add backup/restore verification script (`scripts/verify_backup_restore.py`).

### B3. Startup environment checks need deeper coverage

- Current checks confirm reachability/path presence; they don’t validate operational correctness deeply.

**Recommendation (medium priority):**

- Extend startup diagnostics to verify:
  - required tables exist in LanceDB and include expected columns
  - era pack shape integrity (12-file contract)
  - model availability for active role configs
- Emit structured diagnostics endpoint (`/health/detail`) for deployment monitoring.

---

## C) Gameplay, narrative, and UX depth

### C1. Gameplay loop should become explicitly "intent -> consequence -> reflection"

You already have strong ingredients (mechanic determinism, memory, narrative guardrails). To increase player immersion, formalize this loop in data + UI:

1. **Intent:** action card + tone tag + risk stance (safe/bold/reckless)
2. **Consequence:** immediate world reaction + hidden long-tail consequence seeded
3. **Reflection:** NPC memory callback + ledger update + optional companion commentary

**Recommendation (high priority):**

- Add a `consequence hooks` layer executed post-commit that seeds delayed payoffs.
- Display subtle "world remembers" indicators in UI (not spoilery).

### C2. Companion/NPC systems need stronger authored + procedural blend

- Emotional volatility and memory exist, but engagement improves with predictable relational arcs.

**Recommendation (high priority):**

- Add relationship arc states per key companion (trust, dependency, ideological tension).
- Add scene directors for companion beats (e.g., confession, challenge, crisis, reconciliation).
- Gate some high-impact options by relationship state to create meaningful social gameplay.

### C3. Suggestion quality should be scene-state aware, not just text aware

**Recommendation (medium priority):**

- Include structured scene-state features in SuggestionRefiner inputs:
  - location danger level
  - faction heat
  - unresolved quest pressure
  - companion mood pressure
- Add diversity constraints (no repeated semantic intent across 4 options).

### C4. UX should make narrative systems legible without breaking immersion

**Recommendation (medium priority):**

- Add optional "Narrative Signals" drawer:
  - recent world-state shifts
  - faction movement
  - active hidden clocks (abstracted)
- Keep default UI diegetic; signals drawer can be opt-in for strategy-heavy players.

---

## D) Prompting and pipeline operations

### D1. Prompt strategy should be versioned and testable

**Recommendation (high priority):**

1. Move major system prompts into versioned prompt packs (`prompts/vX/`).
2. Add prompt regression tests using golden scenarios (tone, continuity, safety).
3. Track prompt hash/version in turn metadata for reproducibility.

### D2. Ingestion quality should shift from "best effort" to measurable SLAs

**Recommendation (high priority):**

- Add ingestion QA metrics and thresholds:
  - metadata completeness rate
  - chunk coherence score
  - duplicate chunk rate
  - embedding coverage by era/character/faction
- Fail CI for pack updates that degrade below configured thresholds.

### D3. Caching and retrieval observability can be expanded

**Recommendation (medium priority):**

- Instrument cache hit rate by lane (lore/style/voice/KG).
- Add top-k overlap diagnostics to detect retrieval drift after re-ingest.
- Emit trace IDs for end-to-end turn pipeline correlation.

---

## Prioritized implementation roadmap

## Phase 0 (1-2 weeks): stabilize + simplify startup

- Unify startup docs into a single "new machine" path with copy/paste commands.
- Add non-interactive bootstrap + preflight command.
- Gate legacy simple ingestion behind explicit flag.
- Add `/health/detail` and expand environment checks.

## Phase 1 (2-4 weeks): enforce modular data boundaries

- Complete VectorStore adapter adoption across retrievers and ingestion query paths.
- Introduce service layer split for `v2_campaigns`.
- Add contract tests for adapters and route/service boundaries.

## Phase 2 (3-6 weeks): narrative depth + UX legibility

- Implement consequence hooks and delayed payoff clocks.
- Add relationship arc states and companion beat directors.
- Add scene-state aware suggestion refinement and option diversity constraints.

## Phase 3 (ongoing): deployment confidence and content ops

- Prompt pack versioning + golden tests.
- Ingestion SLA metrics and CI gates.
- Backup/restore drills and performance SLO tracking.

---

## Success criteria (deployment-ready + engaging gameplay)

1. **Portability:** clean bootstrap to playable first turn on a fresh machine in <= 15 minutes.
2. **Reliability:** 99% of turns complete without hard failure under representative local load.
3. **Modularity:** vector backend swap requires adapter/config change only (no retriever edits).
4. **Narrative engagement:** measurable increases in session length, return rate, and companion interaction depth.
5. **Content operations:** ingestion quality metrics stable across releases with automated regression detection.

---

## Final opinion

Claude’s fixes are strong and move the project in the right direction. The next leap is **not adding more features first**; it is finishing boundaries, reducing operational friction, and making narrative systems visible and tunable through data. Do that, and the game can be both technically dependable and genuinely immersive.
