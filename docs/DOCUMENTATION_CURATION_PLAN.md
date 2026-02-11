# Documentation Curation Plan

## 1) Purpose

This plan defines a full documentation curation workflow for Storyteller V2 so docs stay accurate, discoverable, and maintainable as the backend, frontend, and content pipelines evolve.

## 2) Outcomes

- A single, versioned source of truth for architecture, APIs, content authoring, and operations.
- Reduced duplication across overlapping docs.
- Faster onboarding for contributors and operators.
- Document quality gates integrated into normal development.

## 3) Scope

### In scope

- Top-level docs (`README.md`, `QUICKSTART.md`, `API_REFERENCE.md`, model guides).
- `/docs` architecture + implementation guides.
- Data/content docs (era pack schema, authoring references).
- Runbooks and operator-facing procedures.

### Out of scope (for initial pass)

- Rewriting product UX copy or in-app help text.
- Deep content authoring for every era pack instance.
- Localization.

## 4) Documentation Architecture (target state)

Organize documentation into six clear domains:

1. **Getting Started**
   - install, setup, quick run, first successful turn
2. **Concepts**
   - system model, turn lifecycle, event sourcing, RAG lanes
3. **How-to Guides**
   - run API/UI, create campaign, author era pack, ingest lore
4. **Reference**
   - API endpoints, schemas, env vars, model matrix
5. **Operations / Runbooks**
   - troubleshooting, failure modes, recovery steps
6. **Contributor Docs**
   - coding conventions, testing strategy, architecture map

## 5) Curation Workstreams

### Workstream A — Inventory & Classification

- Build a full inventory of all Markdown docs.
- Classify each file into one of: tutorial / concept / how-to / reference / runbook / contributor.
- Record status tags:
  - `authoritative`
  - `needs-update`
  - `duplicate`
  - `archive-candidate`

**Deliverable:** `docs/_curation/inventory.csv` with owner + status columns.

### Workstream B — Freshness & Accuracy Audit

- Validate commands and scripts in docs against current repo entry points.
- Verify route names, feature flags, env vars, and examples.
- Identify stale version references and migrated features.

**Deliverable:** `docs/_curation/audit_findings.md` with prioritized fix list (P0/P1/P2).

### Workstream C — Information Architecture Cleanup

- Remove or merge duplicate guides.
- Add canonical links from older docs to the new source of truth.
- Normalize section templates:
  - "Who is this for?"
  - "Prerequisites"
  - "Steps"
  - "Validation"
  - "Related docs"

**Deliverable:** curated doc map + merged/redirected files.

### Workstream D — Standardization

Create reusable templates for:

- how-to guide
- API reference page
- runbook
- architecture decision / design note

Define standards:

- heading hierarchy
- code block language tags
- command formatting
- warnings vs notes style
- consistent terminology (Campaign, Era Pack, Director, Narrator, etc.)

**Deliverable:** `docs/_curation/style_guide.md` and `docs/_curation/templates/`.

### Workstream E — Ownership & Lifecycle

- Assign a documentation owner per domain.
- Add review cadence (monthly light audit, quarterly deep audit).
- Define update triggers:
  - new endpoint
  - changed env var
  - altered run script
  - schema change

**Deliverable:** `docs/_curation/ownership_matrix.md`.

### Workstream F — Tooling & Automation

Automate checks in CI:

- Markdown linting.
- Link checking (internal links must resolve).
- Optional "command smoke checks" for critical setup paths.

Add PR checklist items:

- "Docs impact reviewed"
- "API/reference updated (if behavior changed)"
- "Runbook updated (if ops behavior changed)"

**Deliverable:** CI doc checks + updated PR template.

## 6) Execution Plan (Phased)

### Phase 0 — Kickoff (Day 1)

- Approve taxonomy and ownership model.
- Create curation workspace under `docs/_curation/`.

### Phase 1 — Baseline Audit (Week 1)

- Complete full inventory + classification.
- Produce prioritized findings list.

### Phase 2 — High-Impact Fixes (Week 2)

- Fix P0/P1 inaccuracies in setup, API, and runbook docs.
- Merge duplicates and add canonical cross-links.

### Phase 3 — Structural Improvements (Week 3)

- Apply templates and standard section structure.
- Align naming, terminology, and navigation patterns.

### Phase 4 — Automation & Governance (Week 4)

- Enable CI checks and PR checklist gates.
- Publish ownership matrix + recurring review calendar.

## 7) Priority Matrix

Use this ordering for curation decisions:

1. **Broken setup/run instructions** (highest)
2. **Incorrect API/reference details**
3. **Operational/runbook inaccuracies**
4. **Confusing architecture/concept drift**
5. **Formatting/style inconsistencies** (lowest)

## 8) Definition of Done

Curation is complete when:

- 100% of docs are inventoried and status-tagged.
- No P0 findings remain.
- Core user journeys are validated end-to-end from docs:
  - local setup
  - run backend + UI
  - create campaign
  - execute at least one turn
- Every domain has an explicit owner.
- CI enforces baseline doc quality checks.

## 9) Suggested Starter Task Breakdown

1. Create `docs/_curation/inventory.csv` and populate all current Markdown files.
2. Audit `README.md`, `QUICKSTART.md`, `API_REFERENCE.md`, `docs/RUNBOOK.md` first.
3. Resolve contradictory setup/run commands.
4. Create style guide + templates.
5. Add automation checks and PR template gates.
6. Schedule first monthly and quarterly documentation reviews.

## 10) Risks & Mitigations

- **Risk:** Curation stalls because no owner is accountable.
  - **Mitigation:** require owner assignment before merging curation kickoff PR.
- **Risk:** Docs become stale again after cleanup.
  - **Mitigation:** CI checks + PR docs-impact checklist + periodic audits.
- **Risk:** Over-normalization removes useful context.
  - **Mitigation:** keep advanced implementation details in deep reference pages; simplify only entry docs.

## 11) Recommended Cadence After Initial Curation

- **Per PR:** docs impact check.
- **Monthly (30 min):** freshness sweep of top entry docs.
- **Quarterly (2–3 hrs):** deep architecture/reference/runbook audit.
- **Per release:** confirm version references and migration notes.
