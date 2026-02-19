# Operations Runbook

Operational guide for production incidents and routine maintenance.

## Service Components

- FastAPI backend (`backend/main.py`)
- SQLite database (`STORYTELLER_DB_PATH`)
- LanceDB vector store (`VECTORDB_PATH`)
- Ollama model service (or configured LLM providers)
- Static frontend build (`frontend/build`)

## Day-1 Startup

1. Configure production env:
   - `STORYTELLER_DEV_MODE=0`
   - `STORYTELLER_API_TOKEN=<secret>`
   - `STORYTELLER_CORS_ALLOW_ORIGINS=<comma-separated origins>`
   - model/provider variables per role
2. Start API service.
3. Validate:
   - `GET /health` returns healthy.
   - `GET /health/detail` returns checks and not hard-failing on missing dependencies.

## Health Interpretation

- `status=healthy`: core checks and required vector/model dependencies are available.
- `status=degraded`: API still runs, but one or more dependencies are unavailable (models, vectors, migrations, DB mode).

Primary checks to inspect:
- `checks.ollama`
- `checks.db_mode`
- `checks.migrations`
- `checks.lancedb_tables`
- `checks.era_packs`

## Common Incident Playbooks

### 1. Turn failures (`5xx` or agent-failure bursts)

- Confirm Ollama/provider availability.
- Inspect logs for `request_id` and `campaign_id`.
- Verify model names in config match loaded models.
- If model outage: inform clients to retry (idempotency key support prevents duplicate commits).

### 2. Elevated p95 latency

- Inspect `agent_timings`/log timings for commit segments.
- Check maintenance-heavy turns (continuity/memory/progression cadence).
- If needed, lower maintenance cadence via constants/config and redeploy.

### 3. DB lock or write contention

- Confirm only one instance is writing the same SQLite file.
- Check for high parallel turn traffic on same campaign.
- Concurrency guard should reject overlapping turns with `409`; if not, inspect turn lock/idempotency logs.

### 4. Missing resume campaigns

- Verify `/v2/campaigns` response from backend.
- Confirm frontend is not in cache-only fallback mode.
- Check DB integrity and `campaigns` rows.

### 5. Deferred agent patches not applying

- Check `pending_world_state_patches` table for stale rows.
- Verify `state_loader.py` `apply_pending_patches()` is running on campaign load.
- If patches are accumulating, check deferred agent logs for LLM failures.

### 6. Rewind fails or produces inconsistent state

- Check `turn_snapshots` table has entries for target turn.
- If snapshot is missing, rewind is not available to that turn (only turns after V7.0 deployment have snapshots).
- Verify `rewind_campaign_to_turn()` transaction completed (check for partial cleanup).

### 7. Canon events not triggering (Historical mode)

- Verify era pack JSON exists in `data/static/era_packs/{era_id}/canon_events.json`.
- Check `canon_events` table for `triggered = 1` rows — may already have fired.
- Ensure campaign mode is `Historical` (canon scheduler skips Sandbox mode).

## Manual Recovery

### Re-run failed request safely

- Reissue same request with same `Idempotency-Key` for deterministic replay.
- If request payload differs, use a new key.

### Campaign rewind

- Use `POST /v2/campaigns/{id}/rewind?to_turn=N` to restore to a known-good state.
- This restores world_state from snapshot and deletes all turn data after turn N.
- The operation is atomic — if it fails, no data is modified.

### Database restore

1. Stop service.
2. Replace DB with latest backup.
3. Start service and re-run migration startup.
4. Execute smoke flow before reopening traffic.

## V7.0 New Tables Reference

| Table | Migration | Purpose |
|-------|-----------|---------|
| `pending_world_state_patches` | 0029 | Deferred maintenance agent output |
| `canon_events` | 0030 | Historical timeline event triggers |
| `turn_snapshots` | 0031 | World state snapshots for rewind |
| `npc_states` | 0032 | Normalized NPC state (extracted from JSON blob) |
| `quest_entries` | 0033 | Normalized quest entries (extracted from JSON blob) |

## On-Call Triage Template

- Time window:
- Symptoms:
- Impacted endpoints:
- First failing `request_id`:
- Root cause:
- Mitigation:
- Follow-up action items:

