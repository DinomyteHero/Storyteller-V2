# Production Readiness Review

## Scope

- Date: 2026-02-12
- Project: Storyteller V2.20
- Perspective: Engineer, Game Developer, Writer, Prompt Engineer

## Executive Summary

Overall status: **Conditional GO** (staging or soft launch), not fully hardened
public production.

The core game loop and backend contracts are solid, and the frontend production
build succeeds. For strict public-production posture, key blockers were:

1. Runtime preflight failing on Python 3.10 while project requires 3.11+.
2. Frontend accessibility warnings in key routes and components.

A controlled launch is possible once production auth and CORS settings are
explicitly enforced.

## Engineer Review

### Architecture and Runtime

- FastAPI startup enforces production safety when
  `STORYTELLER_DEV_MODE=0`.
- Wildcard CORS is rejected.
- API token is required.
- Startup applies DB schema and runs environment diagnostics.
- Health endpoints include `/health` and `/health/detail`.
- A per-IP in-memory limiter exists for turn endpoints
  (10 turn requests per minute).

### Reliability and Test Health

- Targeted backend matrix in `make check` passes (`43/43`).
- Covered areas include prompt registry, retrieval filters, vector store,
  health diagnostics, and v2 campaigns API.

### Operational Gaps

- Python runtime mismatch (3.10 vs required 3.11+) in this environment.
- In-memory rate limiting is single-instance only.
- Frontend accessibility linting was not previously treated as a hard gate.

### Engineering Recommendations

- Treat Python 3.11+ as a hard deployment and CI requirement.
- Use Redis or gateway rate limiting for multi-instance deployments.
- Fail CI on high-severity accessibility violations.

## Game Developer Review

### Core Loop and Determinism

- System is structured around deterministic mechanics plus narrative generation.
- Era-pack content is catalog-driven and deterministic.
- Campaign setup supports canonical IDs (`setting_id`, `period_id`) with
  compatibility behavior.

### Content Readiness

- Era-pack contract is documented and enforceable.
- Runtime diagnostics verify pack presence and basic contract health.

### Gameplay Risk Notes

- Long-session pacing still needs balancing validation.
- No concurrent-user stress evidence captured in this review pass.

### Game Design Recommendations

- Run `backend/scripts/tick_pacing_sim.py` in staging.
- Add early-turn telemetry for latency, retries, and choice quality.

## Writer Review

### Narrative Structure

- Suggestion generation enforces concise first-person player choices.
- Tone diversity and strict JSON output constraints are present.
- Era-pack scaffolding supports lore consistency.

### Narrative Risks

- Prompt inventory appears minimal in visible registry surface.
- Style-governance artifacts for all roles are not equally visible.

### Writing Recommendations

- Version and track prompts for all major narrative roles.
- Maintain golden transcript sets for tone regression before releases.

## Prompt Engineering Review

### Strengths

- Prompt registry supports hashing and compact version IDs.
- Suggestion prompt has strict schema and bounded output constraints.

### Risks

- Registry snapshot visibility appears narrow across active roles.
- Malformed-output fallback behavior should be tested more explicitly.

### Prompt Recommendations

- Expand snapshot/version observability for all active role prompts.
- Add tests for malformed or non-JSON completion handling.

## Launch Checklist

### Blockers

- [ ] Enforce Python 3.11+ in deployment environment and CI.
- [x] Resolve Svelte accessibility warnings in key routes/components.
- [x] Confirm `STORYTELLER_DEV_MODE=0`, explicit
  `STORYTELLER_CORS_ALLOW_ORIGINS`, and non-empty
  `STORYTELLER_API_TOKEN` in production preflight.

### High Priority

- [ ] Validate `/health/detail` against real Ollama, vector DB, and era packs.
- [ ] Run a staging soak and turn-throughput test.
- [ ] Add production-grade distributed rate limiting if multi-instance.

### Medium Priority

- [ ] Expand prompt/version observability across all narrative roles.
- [ ] Add frontend accessibility checks to CI.
- [ ] Create golden narrative regression transcripts.

## Commands Executed During Review

```bash
make check
python scripts/preflight.py
npm run build   # in frontend/
```

## Validation Snapshot

- `make check`: pass (`43` targeted tests passed).
- `python scripts/preflight.py`: fail in this environment
  (Python 3.10 vs required 3.11+).
- `npm run build`: pass with remaining non-a11y warning
  (`.svelte-kit/tsconfig.json` base config warning).
