# Release Checklist

Use this checklist for every production candidate.

## 1. Preflight

- Confirm branch/tag and changelog scope.
- Confirm environment variables are present (`STORYTELLER_API_TOKEN`, CORS allowlist, DB path, model config).
- Confirm `STORYTELLER_DEV_MODE=0` in production manifests.

## 2. Database + Migrations

- Backup the existing SQLite database file.
- Run app startup once in maintenance mode to apply migrations (`apply_schema` runs at startup).
- Verify key tables exist:
  - `campaigns`
  - `turn_events`
  - `truth_facts`
  - `truth_events`
  - `turn_idempotency`
  - `pending_world_state_patches` (V7.0 deferred agents)
  - `canon_events` (V7.0 historical timeline)
  - `turn_snapshots` (V7.0 rewind/undo)
  - `npc_states` (V7.0 schema extraction)
  - `quest_entries` (V7.0 schema extraction)
- Verify WAL mode: `PRAGMA journal_mode` returns `wal`.

## 3. Build + Test Gates

- Backend targeted tests:
  - `python -m pytest backend/tests/test_turn_stream_pre_pipeline_order.py -q`
  - `python -m pytest backend/tests/test_turn_idempotency.py -q`
  - `python -m pytest backend/tests/test_health_detail.py -q`
- Frontend unit tests:
  - `cd frontend && npm test -- --run`
- Smoke flow:
  - `python -m pytest backend/tests/test_e2e_smoke_flow.py -q`

## 4. Runtime Validation

- Check health:
  - `GET /health`
  - `GET /health/detail` (must report expected checks and status semantics).
- Verify auth:
  - Unauthenticated request to protected endpoint returns `401`.
- Verify rate/input guards:
  - Oversized `user_input` returns `413`.
  - Turn flood returns `429`.

## 5. Product Smoke

- Create campaign (`/v2/setup/auto`).
- Run one turn (`/v2/campaigns/{id}/turn`).
- Resume via `/v2/campaigns` + `/state`.
- Complete campaign (`/v2/campaigns/{id}/complete`).
- Validate streaming turn (`/turn_stream`) emits token + done.
- Validate rewind: `POST /campaigns/{id}/rewind?to_turn=1` after 3+ turns.
- Validate mechanic notes appear in turn response when action resolves.
- Verify save confidence indicator appears in HUD after first turn commit.
- Verify onboarding tutorial triggers on first campaign play.

## 6. Observability Checks

- Confirm `X-Request-ID` response header is present.
- Confirm turn logs include `request_id`, `campaign_id`, `turn_id`, latency.
- Confirm `agent_timings` payload appears when debug/context stats are enabled.

## 7. Rollout

- Deploy backend and static frontend artifacts.
- Monitor error rate + p95 turn latency for first hour.
- Verify no spike in `AUTH_HTTP_401`, `RATE_LIMIT`, or agent failure markers.

## 8. Rollback Trigger

Rollback immediately if any occur:
- Turn endpoints produce sustained `5xx`.
- Migration introduces data integrity regressions.
- p95 latency regresses materially with user-visible failures.

