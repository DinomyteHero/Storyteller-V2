# Refactor Notes (Phase 1)

## Summary
- Extracted shared agent utilities into `backend/app/core/agent_utils.py` and wired Director/Narrator/context budget to use them.
- Centralized tuning constants in `backend/app/constants.py` (ledger limits, token estimation factors, retry counts, stop-words).
- Unified JSON retry logic in `backend/app/core/json_reliability.py` with `raw_json_mode` in `AgentLLM.complete()`.
- Decoupled ingestion config via `shared/config.py`, with backend config re-exporting shared constants.
- Split `backend/app/core/graph.py` into node modules under `backend/app/core/nodes/` and made graph a thin topology file.
- Extracted Director schemas and validation/context helpers into `backend/app/models/director_schemas.py` and `backend/app/core/director_validation.py`.
- Removed duplicate Streamlit entry (`ui/streamlit_app.py`); root `streamlit_app.py` is canonical.
- Normalized exception logging across ingestion/backend/test paths to meet logging requirements.
- Consolidated caches into `shared/cache.py` and updated rag/ingestion/companions caches with reset helpers.

## Decisions
- Canonical Streamlit entry point is `streamlit_app.py` at repo root; `ui/streamlit_app.py` removed.
- Node implementations now live in `backend/app/core/nodes/`; `graph.py` only defines topology and run helpers.
- JSON reliability is the single retry path; Director validation is a `validator_fn` inside `call_with_json_reliability()`.
- Cache registry is centralized in `shared/cache.py` with per-module keys and explicit clear helpers.

## Follow-up TODOs
- Run full test suite (`python -m pytest -q`) and targeted gates (deterministic harness + director suggestions).
- Verify `python -c "from backend.app.core.graph import run_turn"` and `python -c "from ingestion.ingest import main"` still import cleanly.
- Consider adding a small README section documenting cache reset helpers for tests.
