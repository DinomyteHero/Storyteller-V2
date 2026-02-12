# Documentation Audit Findings

Audit date: 2026-02-11  
Scope reviewed first: `README.md`, `QUICKSTART.md`, `API_REFERENCE.md`, `docs/RUNBOOK.md`, `data/static/README.md`.

## P0 (Fix immediately)

None currently open.

## P1 (High impact)

1. **Era Pack path examples in `data/static/README.md` are in legacy single-file format.**
   - Current repo uses directory packs under `data/static/era_packs/{era_id}/` with 12 YAML files.
   - Action: update this doc to the modular pack layout and current examples (`_template`, `rebellion`).

2. **`API_REFERENCE.md` requires endpoint verification against actual routers.**
   - The doc should be mechanically checked against runtime routes to avoid drift.
   - Action: add API parity check to quarterly review and when route files change.

## P2 (Medium/low impact)

1. **Multiple docs still describe future/legacy setting-pack migration states.**
   - Affected families: `docs/PACK_AUTHORING.md`, `docs/MIGRATION_FROM_ERA_PACKS.md`, portions of `docs/CONTENT_SYSTEM.md`.
   - Action: keep as historical reference but add clear status banner at top of each file.

2. **Character facets guidance appears in several docs and may cause confusion.**
   - Some docs correctly warn this feature is disabled by default; others should cross-link a single authoritative status section.
   - Action: consolidate into one authoritative note in `docs/lore_pipeline_guide.md`, cross-link elsewhere.

## Completed in this implementation pass

- Corrected `QUICKSTART.md` path examples for rebellion era pack and style file.
- Updated style ingestion command in `QUICKSTART.md` to a currently available script invocation.
- Rewrote `docs/RUNBOOK.md` to align with current launch and era-pack validation flows.

## Validation commands executed

- `python - <<'PY' ...` (path/module existence checks for referenced commands and files)
- `rg -n "setting_pack | rebellion.yaml | build_character_facets | data/style/rebellion_style\.md"`
