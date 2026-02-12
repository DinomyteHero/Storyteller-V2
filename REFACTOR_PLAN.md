# Storyteller V2 Refactor Plan

## 1) Current Architecture Summary

### Runtime entrypoints
- **Primary launcher:** `run_app.py` starts API/UI, runs preflight checks, probes dependencies, and supports dev/check/api-only/ui-only modes.
- **API entrypoint:** `backend/main.py` wires FastAPI, CORS/auth middleware, health endpoints, startup validation, and mounts static files.
- **CLI entrypoint:** `storyteller/cli.py` dispatches to subcommands in `storyteller/commands/` (`setup`, `doctor`, `dev`, `ingest`, `query`, etc.).

### Main modules
- **`backend/app/`**: application logic (API routes, graph orchestration, agents/nodes, DB, RAG, world systems, KG).
- **`ingestion/`**: offline ingestion + metadata/tagging/chunking pipelines.
- **`shared/`**: cross-cutting config/schema/path helpers.
- **`frontend/`**: SvelteKit user interface.
- **`tests/`, `backend/tests/`, `ingestion/test_*.py`**: regression and module-level tests.

### Build/run/test tooling
- Python packaging and deps in `pyproject.toml`.
- `Makefile` provides `bootstrap`, `check`, and `test` commands.
- `pytest.ini` defines multi-suite test discovery.
- Several scripts in `scripts/` for smoke tests, validation, and ingestion maintenance.

### Architectural strengths
- Clear domain split between backend runtime, ingestion pipeline, and static content packs.
- Rich test footprint in backend + ingestion.
- Deterministic data/content model (Era Packs) gives good production reproducibility.

### Key pain points observed
- **Boundary leakage:** runtime concerns (startup checks, environment probing, process orchestration) are spread across multiple entry scripts.
- **Command wiring coupling:** CLI command registration is centralized in one file with hardcoded imports, which increases maintenance risk.
- **Config surface fragmentation:** environment/config handling spans multiple modules (`backend.app.config`, `shared.config`, launch wrappers).
- **Large module risk:** several files are multi-responsibility and harder to test in isolation.

---

## 2) Refactor Goals and Constraints

### Goals
- Improve clarity, modularity, and maintainability.
- Keep behavior stable and public interfaces compatible.
- Increase testability and production readiness.
- Make changes incremental and review-friendly.

### Non-goals (for this refactor stream)
- No product/feature redesign.
- No broad rewrite of graph logic, retrieval behavior, or API contracts.
- No unverified deletion of legacy code paths.

---

## 3) Target Architecture (Incremental)

### Desired layering
1. **Entrypoints** (`run_app.py`, `backend/main.py`, `storyteller/cli.py`)  
   Thin composition and process/bootstrap responsibilities only.
2. **Application services** (`backend/app/core`, `backend/app/world`, `backend/app/rag`, `backend/app/kg`)  
   Business orchestration and deterministic domain behavior.
3. **Adapters** (`backend/app/api`, DB stores, external LLM/vector integrations)  
   Input/output and infrastructure coupling.
4. **Shared utilities** (`shared/`)  
   Stable cross-cutting helpers with minimal side effects.

### Dependency direction
- Entrypoints -> app services -> adapters -> infra.
- Avoid reverse dependencies from domain/core back into entrypoint/process modules.

### Normalized conventions (rolling adoption)
- Prefer per-responsibility modules over single large multi-purpose files.
- Explicit registries for plugin-like systems (commands, retrievers, pipelines).
- Shared configuration helpers centralized and reused.
- Tests colocated by concern with small, deterministic fixtures.

---

## 4) Execution Phases

### Phase 1 — Establish refactor scaffolding in low-risk surfaces (this PR)
- Introduce explicit CLI command registry module and keep CLI behavior unchanged.
- Add targeted tests to lock current command-dispatch behavior.

**Acceptance criteria**
- `storyteller` subcommands remain identical.
- Tests pass for CLI registration/dispatch parsing.
- No API/runtime behavior change.

### Phase 2 — Consolidate configuration boundary
- Introduce a single typed configuration facade used by entrypoints.
- Keep env var names and defaults backward compatible.
- Add tests for env parsing and precedence.

**Acceptance criteria**
- Existing env variables still work.
- Startup checks produce equivalent outcomes.
- No route/CLI contract changes.

### Phase 3 — Extract entrypoint orchestration helpers
- Split large launcher and startup routines into focused modules (health checks, process management, safety checks).
- Keep existing command flags and startup semantics.

**Acceptance criteria**
- `run_app.py` behavior unchanged for supported flags.
- Equivalent process startup and health probes.
- Added unit tests for helper modules.

### Phase 4 — Core/app boundary tightening
- Reduce cross-module coupling in selected high-complexity backend core modules.
- Extract pure functions where possible for deterministic tests.

**Acceptance criteria**
- Existing backend tests remain green.
- New focused tests cover extracted units.
- No API schema/response regressions.

### Phase 5 — Documentation and operations alignment
- Update docs (repo map, runbook, developer onboarding) to match refactored structure.
- Add a refactor changelog and migration notes (if any compatibility layers added).

**Acceptance criteria**
- Docs accurately reflect entrypoints and module boundaries.
- Operational run commands validated.

---

## 5) Risk Table

| Risk | Impact | Mitigation | Verification |
|---|---|---|---|
| CLI command registration drift | Missing/broken subcommands | Use explicit registry + tests asserting expected command names | `pytest tests/test_cli_registry.py` |
| Env/config regressions | Startup/runtime failures | Introduce typed facade gradually; preserve var names/defaults | `python run_app.py --check` + config tests |
| Behavior regression in orchestration | Runtime instability | Extract helpers without changing call order or defaults | smoke tests + selected backend tests |
| Hidden dependencies in large modules | Refactor breakage | Small scoped extractions, phase-gated changes, high-signal tests | targeted pytest suites |
| Deleting still-used code | runtime failures | no deletions until references verified via ripgrep + tests | reference audit + CI tests |

---

## 6) Do Not Touch (without dedicated hardening plan)
- Core gameplay/deterministic mechanics semantics in graph nodes.
- Era Pack schemas/content contracts and campaign API payload shapes.
- Migration history and DB schema compatibility semantics.
- Prompt templates and retrieval lane behavior unless explicitly tested for parity.

---

## 7) Verification Strategy
- Keep each phase PR-sized and independently testable.
- Run focused tests for changed modules + existing smoke checks where feasible.
- Prefer additive tests before structural extraction in high-risk areas.


## 8) Progress Update (Implemented)

- ✅ **Phase 1 complete:** CLI command registry extraction + regression tests.
- ✅ **Phase 2 complete:** Shared runtime security env facade adopted by API and launcher.
- ✅ **Phase 3 complete (entrypoint extraction):** launcher helper functions moved into `storyteller/runtime/app_runner.py`; `run_app.py` now focuses on orchestration.
- ✅ **Phase 4 partial:** fixed a runtime typing defect (`Any` import) in `backend/main.py` to avoid annotation-time runtime errors.
- ✅ **Phase 5 partial:** documentation progress tracked in this plan and repo map updated for new runtime helper module.
