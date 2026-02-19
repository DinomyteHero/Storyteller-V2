# Era Packs (Bible)

Era Packs are deterministic world-state content: factions, locations, NPCs, quests, rumors, and supporting metadata.

Location:

- `data/static/era_packs/{era_id}/`
- Override root with `ERA_PACK_DIR`

This repo currently includes:

- `data/static/era_packs/_template/` — Reference structure (skeleton)
- `data/static/era_packs/rebellion/` — Starter pack (`era.yaml`, `backgrounds.yaml`, `species.yaml`, `canon_events.json`)
- `data/static/era_packs/dark_times/` — Skeleton (`era.yaml`, `backgrounds.yaml`, `species.yaml`)
- `data/static/era_packs/new_republic/` — Skeleton (`era.yaml`, `backgrounds.yaml`, `species.yaml`, `canon_events.json`)
- `data/static/era_packs/new_jedi_order/` — Skeleton (`era.yaml`, `backgrounds.yaml`, `species.yaml`)
- `data/static/era_packs/forgotten_realms/` — Setting-agnostic proof (`era.yaml`, `backgrounds.yaml`, `species.yaml`)

> **Note:** Most packs are currently skeleton stubs. Companion definitions are centralized in `data/companions.yaml` (108 entries).

## Required files per era pack

Each era pack directory must include at minimum:

- `era.yaml` (required)
- `backgrounds.yaml` (required)
- `species.yaml` (required)

## Optional files (full schema)

- `companions.yaml`
- `quests.yaml`
- `npcs.yaml`
- `locations.yaml`
- `factions.yaml`
- `namebanks.yaml`
- `meters.yaml`
- `events.yaml`
- `rumors.yaml`
- `facts.yaml`
- `moments.yaml`
- `canon_events.json`

Systems that depend on missing optional files will gracefully degrade (empty NPC pools, no quest triggers, no moments, etc.).

## Notes

- `style_ref` in `era.yaml` can point to a style guide markdown file (for example `data/style/era/rebellion_style.md`).
- Era pack data powers deterministic world systems; lore retrieval is a separate RAG layer.
- For authoring new packs, use `_template/` as a starting point and run `python scripts/validate_era_packs.py` to validate.
