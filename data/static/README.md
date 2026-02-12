# Era Packs (Bible)

Era Packs are deterministic world-state content: factions, locations, NPCs, quests, rumors, and supporting metadata.

Location:

- `data/static/era_packs/{era_id}/`
- Override root with `ERA_PACK_DIR`

This repo currently includes:

- `data/static/era_packs/_template/`
- `data/static/era_packs/rebellion/`

## Required files per era pack

Each era pack directory must include these 12 YAML files:

- `era.yaml`
- `companions.yaml`
- `quests.yaml`
- `npcs.yaml`
- `locations.yaml`
- `factions.yaml`
- `backgrounds.yaml`
- `namebanks.yaml`
- `meters.yaml`
- `events.yaml`
- `rumors.yaml`
- `facts.yaml`

## Notes

- `style_ref` in `era.yaml` can point to a style guide markdown file (for example `data/style/era/rebellion_style.md`).
- Era pack data powers deterministic world systems; lore retrieval is a separate RAG layer.

For authoring details, see:

- `docs/ERA_PACK_QUICK_REFERENCE.md`
- `docs/era_pack_template.md`
- `docs/era_pack_schema_reference.md`
