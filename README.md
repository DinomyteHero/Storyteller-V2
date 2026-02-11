# Storyteller AI

Storyteller AI is a local-first narrative RPG engine with a FastAPI backend, a SvelteKit frontend, and deterministic world content loaded from YAML packs.

This repository now supports a **world-agnostic content model** based on:

- `setting_id` (which world/universe)
- `period_id` (which time slice/campaign period in that setting)
- stackable pack roots via `SETTING_PACK_PATHS`
- `ContentRepository` and typed resolvers (`NpcResolver`, `LocationResolver`, `MissionResolver`)

Legacy `era_*` naming is still supported by a compatibility layer, but new content should use **Setting Packs**.

---

## Project Overview

At runtime, the backend serves story generation/gameplay APIs while content is loaded deterministically from pack files. The content layer supports:

- composed pack roots (`core`, `addons`, `overrides`)
- deterministic merges (`id`-based list merges + deep dict merges)
- resolver APIs that provide location lookup, NPC casting/procedural generation, and mission offers

The default backend entrypoint is `backend.main:app`.

---

## Key Concepts

### Setting vs Period

- **Setting (`setting_id`)**: normalized key for the world/domain (for example, `star_wars_legends`, `lotr`, `got`)
- **Period (`period_id`)**: normalized key for a playable slice inside a setting (for example, `rebellion`, `third_age`, `war_of_five_kings`)

Internally, content is cached and addressed as `(setting_id, period_id)` in `ContentRepository`.

### Setting Packs (core/addons/overrides)

Pack roots are discovered from `SETTING_PACK_PATHS` (semicolon-delimited). For each `(setting_id, period_id)`, the loader reads roots in order and merges matching period directories.

Default roots when `SETTING_PACK_PATHS` is not set:

- `./data/static/setting_packs/core`
- `./data/static/setting_packs/addons`
- `./data/static/setting_packs/overrides`

### ContentRepository + Resolvers

- `ContentRepository.get_content(setting_id, period_id)` loads merged content and validates it into `EraPack`
- `ContentRepository.get_indices(...)` builds query indices for locations/NPCs/quests/templates
- `NpcResolver` provides scene cast selection and deterministic procedural NPC generation
- `LocationResolver` provides location lookup/filtering/pathing helpers
- `MissionResolver` exposes available authored/procedural mission offers

### Determinism (seeded generation)

`NpcResolver` derives a deterministic RNG from a SHA-256 hash of the provided seed. This makes procedural NPC generation reproducible for identical inputs.

---

## Quickstart

### Prerequisites

- Python 3.11+
- Node.js + npm (for the SvelteKit UI)
- Ollama (if running local LLM-backed flows)

### Install / setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

Optional helper:

```bash
python -m storyteller setup --skip-deps
```

> Note: `storyteller setup` attempts to copy `.env.example` if present. This repository may not include one, so configure env vars directly in your shell.

### Configure environment variables

Minimal content-system variables:

```bash
export SETTING_PACK_PATHS="./data/static/setting_packs/core;./data/static/setting_packs/addons;./data/static/setting_packs/overrides"
export DEFAULT_SETTING_ID="star_wars_legends"
```

Optional legacy compatibility variables:

```bash
export ERA_PACK_DIR="./data/static/era_packs"
# optional mapping YAML for legacy era_id -> (setting_id, period_id)
export ERA_TO_SETTING_PERIOD_MAP="./data/static/era_to_setting_period_map.yaml"
```

### Run API + UI

Run both via unified CLI:

```bash
python -m storyteller dev
```

Or run components separately:

```bash
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

```bash
cd frontend
npm install
npm run dev -- --port 5173
```

---

## Content Authoring (short guide)

For detailed authoring guidance, see:

- [`docs/CONTENT_SYSTEM.md`](docs/CONTENT_SYSTEM.md)
- [`docs/PACK_AUTHORING.md`](docs/PACK_AUTHORING.md)

### Directory layout (example)

```text
data/static/setting_packs/
  core/
    star_wars_legends/
      periods/
        rebellion/
          era.yaml
          locations.yaml
          npcs.yaml
          quests.yaml
  addons/
    star_wars_legends/
      periods/
        rebellion/
          locations/
            outer_rim.yaml
  overrides/
    star_wars_legends/
      periods/
        rebellion/
          npcs.yaml
```

### Merge / override behavior

- Dicts are deep-merged.
- Lists of objects with `id` are merged by `id`.
- `disabled: true` removes the matching `id` from the merged result.
- `extends` is supported for:
  - `npcs.templates`
  - `missions.templates`

---

## Validation + Testing

Validate packs after stacking/merge:

```bash
python scripts/validate_setting_packs.py
```

Override roots for a validation run:

```bash
python scripts/validate_setting_packs.py --paths "./data/static/setting_packs/core;./data/static/setting_packs/overrides"
```

Run backend tests:

```bash
python -m pytest backend/tests -q
```

---

## Troubleshooting

- **`No setting pack found for setting='...' period='...'`**
  - Confirm `SETTING_PACK_PATHS` is set correctly and each root exists.
  - Confirm folder names normalize to expected keys.

- **Validation errors from `validate_setting_packs.py`**
  - Check missing `extends` bases, cyclic `extends`, bad IDs, or malformed YAML.

- **Legacy content loads unexpectedly**
  - If setting pack roots are empty/missing and `setting_id == DEFAULT_SETTING_ID`, loader falls back to `ERA_PACK_DIR`.

- **UI cannot start from `storyteller dev`**
  - Ensure Node/npm are installed and `frontend/` exists.

See [`docs/RUNBOOK.md`](docs/RUNBOOK.md) for operational details.

---

## Glossary

- **setting_id**: normalized identifier for a world/domain.
- **period_id**: normalized identifier for a time slice within a setting.
- **pack root**: one root directory in `SETTING_PACK_PATHS` (for example `core`, `addons`, `overrides`).
- **Setting Pack**: content files under `.../{setting_id}/periods/{period_id}/`.
- **ContentRepository**: app-lifetime cache/loader for merged content and indices.
- **resolver**: query/generation helper over repository data (`NpcResolver`, `LocationResolver`, `MissionResolver`).
- **legacy era adapter**: compatibility path that maps `era_id` to `(setting_id, period_id)`.

---

## Contributing

- Prefer world-agnostic naming in new docs/code (`setting_id`/`period_id`).
- Validate content changes with `scripts/validate_setting_packs.py` before opening a PR.
- Keep long-form process guidance in `docs/` and link from README.
