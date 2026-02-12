# Production Readiness Review (Engineer + Game Dev + Writer + Prompt Engineer)

Date: 2026-02-12
Scope: Full-repo launch readiness walkthrough for Storyteller V2.20.

## Executive Summary

**Overall status: Conditional GO (staging/soft launch), NOT full hardening-complete production.**

The core game loop and backend contracts are in solid shape (targeted backend test suite passes), and frontend production build succeeds. However, there are two launch blockers for a strict production posture:

1. Runtime preflight fails on Python 3.10 (project requires 3.11+).
2. Frontend build emits accessibility warnings that should be addressed before broad launch.

If you are comfortable with a controlled release (trusted users, modest traffic), you can proceed after enforcing Python 3.11 and setting production env/auth controls. For wider public release, complete the remediation checklist below first.

---

## 1) Engineer Review

### Architecture & Runtime

- FastAPI startup enforces production safety when `STORYTELLER_DEV_MODE=0`:
  - wildcard CORS is rejected.
  - API token is required.
- Startup runs DB schema migration and environment validation diagnostics.
- Health endpoints include both simple `/health` and structured `/health/detail` diagnostics (LLM reachability, vector DB, era packs).
- A per-IP in-memory rate limiter exists for turn endpoints (10 turn requests/minute/IP).

**Assessment:** Good baseline safety controls for single-instance deployment.

### Reliability & Test Health

- Targeted backend test matrix in `make check` passes fully (43/43).
- Important areas validated by tests include:
  - prompt registry,
  - lore/style/voice retrieval,
  - vector store factory,
  - health detail,
  - v2 campaigns API.

**Assessment:** Solid regression confidence in critical backend paths.

### Operational Gaps

- Preflight fails in this environment due to Python 3.10; project explicitly requires Python 3.11+.
- In-memory rate limiting is not distributed (resets on restart; not multi-instance aware).
- No explicit CI gate shown for frontend accessibility warnings.

**Recommendation:**
- Treat Python 3.11 as hard requirement before deployment.
- If horizontally scaling, move rate limit to Redis or gateway.
- Add CI lint/a11y checks for frontend and fail builds on high-severity issues.

---

## 2) Game Developer Review

### Core Loop & Determinism

- API and model contracts are structured around deterministic + narrative split.
- Era-pack content system is deterministic and catalog-driven.
- Campaign setup supports canonical content coordinates (`setting_id`, `period_id`) with compatibility handling.

**Assessment:** Strong foundation for reproducible gameplay and content-driven expansion.

### Content System Readiness

- README defines stable era pack contract and currently supported packs.
- Runtime diagnostics validate era-pack presence and minimum file-count contract.

**Assessment:** Good deployment-time guardrails for content integrity.

### Gameplay Risk Notes

- Default location/NPC cast seed behavior is deterministic in structure but may still require balancing for long-session pacing.
- No explicit stress/load simulation evidence captured in this pass for concurrent users.

**Recommendation:**
- Run `backend/scripts/tick_pacing_sim.py` and turn throughput/load checks in staging.
- Add a short “first 10 turns” telemetry dashboard (latency, retries, hallucination/error rate, choice quality).

---

## 3) Writer / Narrative Review

### Voice & Narrative Structure

- Prompt-guided suggestion system demands concise first-person player options with tone diversity and strict JSON format.
- Era-pack model and companion/faction scaffolding support lore consistency and role clarity.

**Assessment:** Narrative scaffolding is coherent and production-viable for the current scope.

### Writing Risks

- Prompt inventory appears minimal (single versioned file surfaced in `prompts/v1`).
- Limited explicit style-governance artifacts for narrator/director prompt evolution found in this pass.

**Recommendation:**
- Add prompt versioning for all major narrative roles (Director/Narrator/Casting) if not already externalized.
- Maintain a “golden transcript set” for story-tone regression before each release.

---

## 4) Prompt Engineering Review

### Strengths

- Prompt registry supports deterministic hashing/version IDs for auditability.
- Suggestion prompt has strict output schema, bounded length, tone taxonomy, and safety against scene continuation.

### Risks

- Single visible prompt in registry snapshot suggests limited observability across all role prompts.
- No explicit automated schema-validation test shown for malformed LLM output recovery in this walkthrough.

**Recommendation:**
- Expand prompt registry snapshot coverage to all active role prompts.
- Add explicit tests for malformed/non-JSON LLM completions and fallback behavior.

---

## Launch Checklist (Prioritized)

### Blockers (fix before public production)

- [ ] Enforce Python 3.11+ runtime in deployed environment and CI.
- [ ] Resolve Svelte accessibility warnings in key routes/components.
- [ ] Confirm `STORYTELLER_DEV_MODE=0`, explicit `STORYTELLER_CORS_ALLOW_ORIGINS`, and non-empty `STORYTELLER_API_TOKEN` in production.

### High Priority

- [ ] Validate `/health/detail` on deployment target with real Ollama + vector DB + era packs.
- [ ] Run a staging soak/load test for turn endpoints.
- [ ] Add production-grade rate limiting (gateway/Redis) if multi-instance.

### Medium Priority

- [ ] Expand prompt/version observability for all narrative roles.
- [ ] Add frontend a11y checks to CI.
- [ ] Create golden narrative regression transcripts.

---

## Commands Executed During Review

```bash
make check
python scripts/preflight.py
npm run build   # in frontend/
```

## Validation Snapshot

- `make check`: PASS (targeted 43 tests passed).
- `python scripts/preflight.py`: FAIL in this environment (Python 3.10, requires 3.11+).
- `npm run build`: PASS with warnings (accessibility + tsconfig warning).

