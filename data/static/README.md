# Era Packs (Bible)

Era Packs are deterministic world state: factions, locations, and NPC casts. They are the canonical source of truth for who exists in an era. RAG is a referenced library for flavor only.

Location:
- `data/static/era_packs/{era}.yaml`
- Override directory with `ERA_PACK_DIR`

This repo currently includes:
- `data/static/era_packs/lotf.yaml`
- `data/static/era_packs/rebellion.yaml`

## Required Top-Level Keys

- `era_id` (string, e.g., `LOTF`)
- `factions` (list)
- `locations` (list)
- `npcs` (object with `anchors`, `rotating`, `templates`)

Optional:
- `namebanks` (map of namebank_id -> list of names)
- `style_ref` (path to style doc, e.g. `data/style/lotf_style.md`)

## Factions

Each faction:
- `id` (string)
- `name` (string)
- `tags` (list of strings)
- `home_locations` (list of location ids)
- `goals` (list of strings)
- `hostility_matrix` (optional map, for tooling)

## Locations

Each location:
- `id` (string)
- `name` (string)
- `tags` (list of strings)
- `region` (optional string)
- `controlling_factions` (list of faction ids)

## NPCs

### Anchors / Rotating (Tier A/B)

Each NPC entry:
- `id` (string, stable)
- `name` (string, canonical)
- `aliases` (list of strings)
- `banned_aliases` (list of strings)
- `match_rules` (object):
  - `min_tokens` (int, default 1)
  - `require_surname` (bool, default false)
  - `case_sensitive` (bool, default false)
  - `allow_single_token` (bool, default false)
- `tags` (list)
- `faction_id` (optional)
- `default_location_id` (optional)
- `home_locations` (optional list)
- `role` (optional)
- `archetype` (optional)
- `traits` (optional list)
- `motivation` (optional)
- `secret` (optional)
- `voice_tags` (optional list)

NPC tagging uses these aliases to annotate lore chunks with `related_npcs`. In `strict` mode, single-token aliases are ignored unless `allow_single_token=true`.

### Templates (Tier C)

Each template:
- `id` (string)
- `role` (string)
- `archetype` (optional)
- `traits` (list)
- `motivations` (list)
- `secrets` (list)
- `voice_tags` (list)
- `species` (list)
- `tags` (list)
- `namebank` (string key in `namebanks`)

Templates are used by the deterministic NPC generator.
