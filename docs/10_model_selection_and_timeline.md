# 10 — Model Selection, Overrides, and Timeline Planning

This is the **single operations reference** for:
- choosing local vs cloud models per role,
- understanding env-var override precedence,
- planning timeline pacing for canonical-era campaigns.

## 1) Is model selection hard-coded?

Short answer: **defaults are in code, effective config is env-overridable per role**.

- Default role mappings live in `backend/app/config.py` (`_model_config()` base map).
- At startup, each role applies env overrides via `_role_env()`.
- `AgentLLM(role)` always reads `MODEL_CONFIG[role]` (resolved config), not hardcoded constants inside agents.

So you can switch Narrator from local Ollama (`qwen3`, `mistral-nemo`, etc.) to cloud (`openai`, `anthropic`, openai-compatible) **without editing agent code**.

## 2) Override precedence (what is used)

For each role (example: `narrator`):

1. Base default in `backend/app/config.py` (`_model_config()` map)
2. `STORYTELLER_<ROLE>_PROVIDER` (or fallback `<ROLE>_PROVIDER`)
3. `STORYTELLER_<ROLE>_MODEL` (or fallback `<ROLE>_MODEL`)
4. `STORYTELLER_<ROLE>_BASE_URL` (or fallback `<ROLE>_BASE_URL`)
5. `STORYTELLER_<ROLE>_API_KEY` (or fallback `<ROLE>_API_KEY`)
6. Optional fallback chain:
   - `STORYTELLER_<ROLE>_FALLBACK_PROVIDER`
   - `STORYTELLER_<ROLE>_FALLBACK_MODEL`

## 3) Practical examples

### Local narrator (Ollama)

```bash
export STORYTELLER_NARRATOR_PROVIDER=ollama
export STORYTELLER_NARRATOR_MODEL=qwen3:8b
# optional:
export STORYTELLER_NARRATOR_BASE_URL=http://localhost:11434
```

### Cloud narrator (GPT-5.2 mini style setup)

```bash
export STORYTELLER_NARRATOR_PROVIDER=openai
export STORYTELLER_NARRATOR_MODEL=gpt-5.2-mini
export STORYTELLER_NARRATOR_API_KEY=...
```

### Hybrid narrator with local fallback

```bash
export STORYTELLER_NARRATOR_PROVIDER=openai
export STORYTELLER_NARRATOR_MODEL=gpt-5.2-mini
export STORYTELLER_NARRATOR_API_KEY=...

export STORYTELLER_NARRATOR_FALLBACK_PROVIDER=ollama
export STORYTELLER_NARRATOR_FALLBACK_MODEL=mistral-nemo:latest
```

## 4) Inspect effective model config

Use:

```bash
storyteller models
```

This prints the resolved per-role provider/model (including fallback chain if set).

## 5) Timeline coherence for canon years

Your concern is valid: if action-time accumulation is unconstrained, campaigns can drift too far in-world.

Current safeguards:
- deterministic action costs (minutes) in `backend/app/time_economy.py`
- deterministic arc stages with min/max-turn guards in `backend/app/constants.py` + `arc_planner.py`
- world tick cadence from `WORLD_TICK_INTERVAL_HOURS` (default 4h)

### Recommended canonical guardrails

For a fixed historical window (example: 19 BBY):
1. Define a **campaign calendar budget** at campaign start (e.g., 90 in-world days max).
2. Track `world_time_minutes` progression per turn.
3. Trigger warnings when crossing thresholds (75%, 90%, 100% of budget).
4. Shift pacing toward resolution (higher COMMIT weight, fewer long travel hops) once >90% budget.

## 6) Estimated in-world duration by campaign size

Using current action-time defaults (`TALK=8`, `INVESTIGATE=25`, `PERSUADE=20`, `TRAVEL=45`, `ATTACK=35` minutes),
a practical blended average for mixed play is ~22–30 minutes/turn.

Arc min-turn baseline today:
- SETUP 3
- RISING 5
- CLIMAX 5
- RESOLUTION 3
- **Minimum full arc: ~16 turns**

### Planning estimates

| Size | Turn range (practical) | In-world elapsed (22–30 min/turn) |
|---|---:|---:|
| Short | 16–30 turns | ~6–15 hours |
| Medium | 31–70 turns | ~11–35 hours (~0.5–1.5 days) |
| Large | 71–140 turns | ~26–70 hours (~1–3 days) |
| Epic | 141–300 turns | ~52–150 hours (~2–6 days) |

If your table style includes frequent hyperspace/travel-heavy turns, elapsed time can expand quickly.
In that case, reduce travel frequency or lower travel costs for that campaign profile.

## 7) Cost planning formula (cloud usage)

Per role:

`monthly_role_cost ~= calls_per_month * avg_tokens_per_call * price_per_1k_tokens / 1000`

Total is the sum across roles plus ingestion jobs. Use this to compare all-cloud vs hybrid vs local.


## 8) Option A automation pipeline (recommended)

To reduce manual style authoring, use the hybrid generator:

```bash
storyteller build-style-pack --input <corpus_root> --output <style_root>
# optional cloud/local polish step:
storyteller build-style-pack --input <corpus_root> --output <style_root> --use-llm --llm-role ingestion_tagger
python scripts/ingest_style.py --input <style_root>
```

This follows Option A: deterministic extraction first, optional LLM polish second, then ingest.
