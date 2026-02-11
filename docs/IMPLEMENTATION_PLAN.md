# Storyteller V2 — Long-Term Stabilization & Migration Plan

> Goal: move from an era-pack/hardcoded-frontend hybrid to a stable, dynamic setting/period platform that remains playable while content is migrated.

---

## Executive Summary

This plan addresses the core mismatch discovered in the repo:

1. **Backend content loading supports setting/period composition**, but most public APIs still expose legacy `era` semantics.
2. **Frontend timeline options are hardcoded**, so users can select periods that do not exist on disk.
3. **Setup flow fails too early** when a missing period is selected instead of guiding users.
4. **Operational defaults still reference non-existent periods** in some scripts/tests.

The implementation below is a full, staged migration designed to keep the game playable throughout.

---

## Guiding Principles

- **Single source of truth:** available settings/periods come from backend content discovery only.
- **No dead-end UX:** invalid selection should produce actionable user feedback (never a raw 500).
- **Backward compatibility first:** preserve existing `/v2/era/*` routes while introducing `/v2/content/*`.
- **Playability over purity:** default configs/scripts always point to a known playable period.
- **Feature-flagged migration:** ship in slices with rollback switches.

---

## Phase 0 — Baseline Hardening (Week 1)

### Objectives

- Ensure one guaranteed playable path in all environments.
- Stop false failures caused by stale defaults.

### Tasks

1. Set runtime/testing defaults to `rebellion` where period defaults are currently missing or stale.
2. Update smoke and diagnostic scripts to use discovered/default playable period instead of hardcoded `LOTF`.
3. Add preflight check that prints discovered periods and selected default period.

### Acceptance Criteria

- `scripts/smoke_test.py` passes on clean repo + temp DB without manual period override.
- Any CLI/start script reports exactly which setting/period it will use.

---

## Phase 1 — Content Discovery API (Week 1–2)

### Objectives

- Introduce canonical API surface for dynamic settings/periods.

### New Endpoints

1. `GET /v2/content/catalog`
   - Returns settings + periods discovered from configured pack roots.
   - Includes:
     - `setting_id`, `setting_display_name`
     - `period_id`, `period_display_name`
     - `source` (`setting_pack` | `legacy_era_pack`)
     - minimal metadata (description, tags, playability flags)

2. `GET /v2/content/default`
   - Returns the server-selected default setting/period.
   - Logic: env override -> configured default -> first discovered playable period.

3. `GET /v2/content/{setting_id}/{period_id}/summary`
   - Returns lightweight content summary for creation screen (location count, backgrounds, companions preview count).

### Compatibility

- Keep `/v2/era/{era_id}/...` alive, implemented as adapters over content catalog resolution.

### Acceptance Criteria

- Frontend can populate timeline selector entirely from API.
- Catalog endpoint works whether content comes from `setting_packs/*` or legacy `era_packs/*`.

---

## Phase 2 — Setup & Turn API Robustness (Week 2–3)

### Objectives

- Eliminate setup hard crashes from invalid period selections.

### Tasks

1. Add normalized request schema for setup:
   - Preferred: `setting_id`, `period_id`
   - Legacy accepted: `time_period` (mapped internally)
2. In setup route:
   - Validate selection against catalog first.
   - Return structured 4xx (`error_code`, `message`, `details.suggestions`) for unknown periods.
3. Add fallback policy when no period supplied:
   - Use `content/default` resolver.
4. Apply same validation to all period-dependent endpoints.

### Acceptance Criteria

- Selecting unavailable period no longer raises unhandled exceptions.
- API returns clear correction options (e.g., available periods list).

---

## Phase 3 — Frontend Dynamic Timeline Migration (Week 3–4)

### Objectives

- Remove hardcoded era/timeline options and bind UI to content catalog.

### Tasks

1. Add frontend data layer:
   - `getContentCatalog()`, `getContentDefault()`, `getContentSummary()`
2. Replace hardcoded `ERA_LABELS` selector source with catalog response.
3. Keep visual labels from server metadata (display_name), not local constants.
4. Update creation state:
   - store selected `{settingId, periodId}`
   - legacy `charEra` remains temporary adapter until full cutover
5. On startup, auto-select server default content when user has no prior preference.

### Acceptance Criteria

- Adding/removing period folders changes UI choices without frontend code edits.
- Creation flow succeeds with dynamic selections and fails gracefully otherwise.

---

## Phase 4 — Content Model Convergence (Week 4–6)

### Objectives

- Complete migration from era-first semantics to setting/period-first internals.

### Tasks

1. Introduce canonical internal key object for all content fetches:
   - `ContentRef { setting_id, period_id }`
2. Convert major services to consume `ContentRef` directly:
   - setup, companions, encounter manager, quest tracker, lore retrieval filters
3. Restrict legacy `era_id` handling to explicit adapter boundary.
4. Add migration report command:
   - shows which code paths still rely on era aliases.

### Acceptance Criteria

- Main game loop no longer depends on legacy `era_id` internally.
- Legacy routes still function for existing clients.

---

## Phase 5 — Data Quality & Playability Gates (Week 5–7)

### Objectives

- Prevent “selectable but unplayable” periods.

### Tasks

1. Add playability validator score per period:
   - required minima for locations, NPC templates, backgrounds, quests, rumors
2. Catalog exposes `playable: true/false` + reason list.
3. Frontend creation screen:
   - hides non-playable periods by default
   - optional “show experimental” toggle for dev mode
4. CI gate for content packs:
   - new/updated periods must meet threshold or be flagged experimental.

### Acceptance Criteria

- User cannot accidentally start campaign in content-incomplete period unless they explicitly opt in.

---

## Phase 6 — Documentation & Operations Cleanup (Week 6–8)

### Objectives

- Align docs and runbooks with new dynamic architecture.

### Tasks

1. Update docs to describe content catalog API as authoritative discovery mechanism.
2. Replace examples using deprecated hardcoded periods.
3. Add operator guide:
   - how to add new period folder
   - how it appears in API/UI
   - how to validate playability
4. Add troubleshooting matrix for common migration failures.

### Acceptance Criteria

- New contributor can add a period folder and see it in UI without touching frontend constants.

---

## Technical Work Breakdown (Cross-Cutting)

### Backend

- API additions under `backend/app/api/v2_campaigns.py` or a dedicated `v2_content.py` router.
- Extend repository service for catalog/build metadata output.
- Centralize period resolution and validation utility.

### Frontend

- Add content-catalog API client module.
- Update creation store and creation route to dynamic options.
- Keep temporary adapter for legacy fields until setup payload migration is complete.

### Tests

- Unit tests for catalog discovery and legacy mapping fallback.
- API tests for invalid period handling (4xx + suggestions).
- Frontend store tests for dynamic timeline selection.
- End-to-end smoke test with:
  - only legacy era packs,
  - only setting packs,
  - mixed roots.

---

## Migration Safety Strategy

- Feature flag: `ENABLE_DYNAMIC_CONTENT_CATALOG=1`
  - Allows staged rollout.
- Dual-write/dual-read period in setup payload:
  - accept both `time_period` and `setting_id/period_id`.
- Compatibility window:
  - keep era endpoints and mapping for at least one release cycle.
- Telemetry:
  - log usage split between legacy and canonical routes.

---

## Risks & Mitigations

1. **Risk:** Mixed pack structures cause ambiguous resolution.
   - **Mitigation:** deterministic precedence order + explicit catalog source metadata.

2. **Risk:** Frontend and backend drift during migration.
   - **Mitigation:** backend-driven defaults and strict API contract tests.

3. **Risk:** Existing campaigns store legacy period IDs.
   - **Mitigation:** migration mapper at campaign load; store canonical IDs forward.

4. **Risk:** Catalog exposes non-playable periods.
   - **Mitigation:** built-in playability score and UI filtering.

---

## Milestone Definition of Done

The long-term migration is complete when all of the following are true:

- Timeline/period options are discovered dynamically from backend content catalog.
- Setup and gameplay APIs operate on canonical `setting_id/period_id` inputs.
- Legacy era API remains available as compatibility adapter, not core path.
- Unknown periods return friendly 4xx errors with correction hints.
- New content folders become selectable in UI automatically.
- Default smoke tests pass without manual period/environment surgery.

