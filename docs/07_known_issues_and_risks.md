# 07 — Known Issues & Risks

This is a **living** list of code-evidenced issues and risks in the current repo state.

Last updated: V5.0 architecture revision.

---

## Resolved in V5.0

| Issue | Status | Resolution |
| ------- | -------- | ----------- |
| SuggestionRefiner had deterministic fallback that could produce low-quality, context-free choices | ✅ Resolved | Replaced by authoritative `ChoiceCrafterAgent` (LLM-driven, no fallback) |
| Agents hardcoded "Star Wars" universe references in prompts | ✅ Resolved | All agents now use `get_setting_rules(state)` / `SettingRules` |
| No scripted narrative moment system | ✅ Resolved | `EraMoments` system added (V5.0) — `moments_node` in pipeline |
| No quest state machine | ✅ Resolved | `QuestTracker` deterministic quest state machine added (V5.0) |
| Companion data in multiple inconsistent locations | ✅ Resolved | `PartyState` canonical model in `world_state_json["party_state"]` (V5.0) |
| No hub/downtime mode | ✅ Resolved | `hub_system.py` added; Director gets hub context injection (V5.0) |
| Content loading not thread-safe | ✅ Resolved | `ContentRepository` singleton with `threading.RLock` (V5.0) |
| Truth Ledger tables (truth_facts, truth_events) missing from migrations | Resolved | Tables exist in `backend/app/db/migrations/0019_turn_contract_passages.sql` |

---

## Active Issues

### 1. ChoiceCrafterNode: No graceful degradation on authoritative failure

**Severity:** Medium

**Evidence:** `backend/app/core/nodes/choice_crafter_node.py`

When `ChoiceCrafterAgent` fails after retry, `AgentFailureError` is raised and caught by `run_turn()`. The turn returns `final_text` with an error message and **empty `suggested_actions`**. The player sees a `[SYSTEM]` error and cannot continue without retrying the turn.

**Risk:** If the ChoiceCrafter LLM endpoint is unavailable (Ollama down), every turn fails — even if the Narrator succeeded.

**Workaround:** None at runtime. Fix: Add a minimal deterministic fallback (4 generic action stubs) when `AgentFailureError` is caught, rather than returning empty choices.

---

### 2. apply_projection() is O(N) over full event history

**Severity:** Medium (performance)

**Evidence:** `backend/app/core/state_reducer.py` — replays ALL events from the beginning of the campaign on every turn.

**Risk:** For long campaigns (1000+ turns), projection time grows linearly. This blocks the turn response.

**Workaround:** The system works correctly for campaigns up to ~200 turns. For longer campaigns, a snapshot-based projection (periodic checkpoint + replay from checkpoint) would be needed.

---

### 3. world_state_json is a single large JSON blob

**Severity:** Low-Medium

**Evidence:** `backend/app/db/migrations/0001_init.sql` — `world_state_json TEXT`

**Risk:** Concurrent writes to `world_state_json` are not safe in multi-threaded scenarios (though FastAPI/uvicorn workers serialize requests per campaign). Any partial failure during Commit that writes JSON but doesn't commit the transaction could leave the column out of sync. SQLite's WAL mode mitigates data loss risk.

**Mitigation:** Single transaction boundary in Commit node prevents partial writes. Foreign key constraints and WAL mode enabled.

---

### 4. Encounter throttling state is persisted in world_state_json, not in a dedicated table

**Severity:** Low

**Evidence:** Encounter throttle events (`NPC_INTRODUCTION_RECORDED`, `LAST_LOCATION_UPDATED`) are replayed through `apply_projection()`.

**Risk:** If throttling state is reset (e.g., via migration or manual DB edit), NPCs may be re-introduced on the next turn, potentially causing duplicate NPC spawns.

**Workaround:** Avoid resetting world_state_json manually. Migration-safe.

---

### 5. KG extraction is offline-only, not integrated into the live pipeline

**Severity:** Low

**Evidence:** `storyteller extract-knowledge` command — runs offline, not during turns.

**Risk:** The KG in the database may be stale relative to the current narrative (events not yet extracted). `kg_retriever.py` retrieves from a static snapshot.

**Workaround:** Run `storyteller extract-knowledge` periodically on long campaigns.

---

### 6. Era pack `moments` field: not all era packs define moments

**Severity:** Low

**Evidence:** `backend/app/core/nodes/moments.py` — `moments = getattr(era_pack, "moments", []) or []`

**Risk:** Era packs that don't define `moments` get no scripted moment triggers. This is expected behavior, but it means some settings will have no EraMoments system benefits until packs are updated.

**Workaround:** Moments node is non-fatal; packs without moments silently skip the system.

---

### 7. PartyState backward compatibility: legacy fields written but may drift

**Severity:** Low

**Evidence:** `backend/app/core/party_state.py:save_party_state()` writes both `party_state` and legacy fields (`party`, `party_affinity`, etc.).

**Risk:** Any code that modifies legacy fields directly (bypassing `PartyState`) will cause drift between `party_state` and legacy fields. The next `load_party_state()` call will prefer `party_state` (which won't reflect the manual change).

**Mitigation:** Only modify companion data via `add_companion_to_party()`, `remove_companion_from_party()`, and `apply_influence_delta()`.

---

### 8. LanceDB vector tables may not exist on fresh install

**Severity:** Medium (setup)

**Evidence:** `backend/app/rag/lore_retriever.py` — `db.open_table(LORE_TABLE_NAME)` raises if table doesn't exist.

**Risk:** If LanceDB hasn't been populated via the ingestion pipeline, RAG retrieval raises exceptions. The Director and Narrator nodes have fallback handling for retrieval failures, but this produces generic (non-grounded) narration.

**Workaround:** Run ingestion pipeline before first use. The health check endpoint (`/health/detail`) reports LanceDB table status. `storyteller doctor` also reports this.

---

### 9. No streaming support for MetaNode responses

**Severity:** Low

**Evidence:** `backend/app/core/nodes/router.py:meta_node` — returns synchronously with no streaming.

**Risk:** Meta responses (help, status) are returned in full synchronously. Consistent with the rest of the pipeline for META intent, but SSE stream consumers may expect at least one chunk.

**Workaround:** Frontend handles META responses as full-text (no streaming needed for meta).

---

## Risks

### R1. Ollama model availability

If the configured LLM model (e.g., `mistral-nemo:latest`) is not pulled in Ollama, all LLM calls will fail. Authoritative agents (Narrator, ChoiceCrafter) will trigger `AgentFailureError`. Non-authoritative agents (Director, WorldMind) will produce empty output.

**Mitigation:** `storyteller doctor` checks Ollama connectivity. `python run_app.py --check` runs preflight. Recommend pulling models before starting.

### R2. LLM JSON output reliability

Narrator and ChoiceCrafter use JSON-mode LLM calls. Malformed JSON from the LLM triggers repair attempts (up to 3 retries). If all retries fail:
- NarratorAgent: `AgentFailureError` → user-facing error
- ChoiceCrafterAgent: `AgentFailureError` → user-facing error

**Mitigation:** `json_reliability.py` + `json_repair.py` handle most common LLM JSON failures (trailing commas, unclosed brackets, embedded newlines).

### R3. World time consistency

`world_time_minutes` advances atomically in the Commit node. If Commit fails after advancing time but before writing events, the time counter will be ahead of the event log.

**Mitigation:** Single `conn.commit()` call ensures time + events are written atomically.

### R4. Setting-agnostic architecture: incomplete migration

Not all agents have been fully migrated to use `get_setting_rules(state)`. Some prompt templates may still contain Star Wars-specific references.

**Mitigation:** V5.0 makes this the default; future agents must use `SettingRules`. Existing agents are progressively being updated.

