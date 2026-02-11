# Storyteller V2 - Consolidation & Cleanup Plan

## Objectives
1. Remove all legacy code, backup files, and obsolete scripts
2. Streamline era packs to template + one canonical pack
3. Consolidate documentation
4. Create clean campaign initialization templates
5. Focus repo on current V2.20+ architecture

---

## Files/Directories to DELETE

### 1. Documentation Archive
- `/docs/archive/` - **ENTIRE DIRECTORY**
  - Contains obsolete refactor notes and 2025 review
  - No longer relevant to current architecture

### 2. Backup Files
- `/data/static/era_packs/rebellion/locations.yaml.bak` - **DELETE**
  - Leftover backup file

### 3. Legacy Migration Tools
- `/tools/` - **ENTIRE DIRECTORY**
  - `migrate_rebellion_pack_v2.py` - one-time migration script
  - `README_ERA_MIGRATION.md` - obsolete migration guide
  - `REBELLION_V2_MIGRATION_REPORT.md` - obsolete migration report
  - These were used for v1 → v2 migration and are no longer needed

### 4. Legacy Scripts (13 files)
All in `/scripts/` directory:
- `enrich_era_pack_v2.py` - **DELETE** (superseded by v3, now obsolete)
- `enrich_era_packs_v3.py` - **DELETE** (one-time enrichment, already applied)
- `fix_legacy_access_points.py` - **DELETE** (one-time fix)
- `fix_legacy_companions.py` - **DELETE** (one-time fix)
- `fix_legacy_facts.py` - **DELETE** (one-time fix)
- `fix_legacy_quests.py` - **DELETE** (one-time fix)
- `fix_legacy_rumors.py` - **DELETE** (one-time fix)
- `fix_njo_facts.py` - **DELETE** (one-time fix, NJO pack being removed)
- `fix_njo_rumors.py` - **DELETE** (one-time fix, NJO pack being removed)
- `fix_rebellion_yaml_anchors.py` - **DELETE** (one-time fix)
- `merge_npc_batch.py` - **DELETE** (one-time merge)
- `merge_npc_final_batch.py` - **DELETE** (one-time merge)
- `merge_npc_templates.py` - **DELETE** (one-time merge)

### 5. Era Packs (5 packs to remove)
User directive: "Delete era packs if it doesn't make sense - we can regenerate later"

**KEEP:**
- `/data/static/era_packs/_template/` - Reference structure for new packs
- `/data/static/era_packs/rebellion/` - Most complete, canonical Galactic Civil War era

**DELETE:**
- `/data/static/era_packs/dark_times/` - **ENTIRE DIRECTORY**
- `/data/static/era_packs/kotor/` - **ENTIRE DIRECTORY**
- `/data/static/era_packs/legacy/` - **ENTIRE DIRECTORY**
- `/data/static/era_packs/new_jedi_order/` - **ENTIRE DIRECTORY**
- `/data/static/era_packs/new_republic/` - **ENTIRE DIRECTORY**

**Rationale:** Keeping only the template + one well-formed canonical pack. Others can be regenerated using the template when needed.

---

## Files/Directories to KEEP

### Core Documentation (KEEP)
- `/docs/00_overview.md` through `/docs/09_call_graph.md` - Sequential learning path
- `/docs/architecture.md` - Deep architecture guide (Living Loop, agents, RAG)
- `/docs/user_guide.md` - Player-facing documentation
- `/docs/lore_pipeline_guide.md` - Canonical ingestion reference
- `/docs/era_pack_template.md` - Template for creating new packs
- `/docs/era_pack_schema_reference.md` - Schema documentation
- `/docs/era_pack_generation_prompt.md` - LLM prompt for generation
- `/docs/PACK_AUTHORING.md` - Pack creation guide
- `/docs/IMPLEMENTATION_PLAN.md` - Implementation roadmap
- `/docs/CONTENT_SYSTEM.md` - Content loading system
- `/docs/RUNBOOK.md` - Operations runbook
- `/docs/ui_improvements_v2.9.md` - UI improvements
- `README.md`, `CLAUDE.md`, `QUICKSTART.md`, `API_REFERENCE.md` - Root docs

### Essential Scripts (KEEP)
- `validate_era_packs.py`, `validate_era_pack.py`, `validate_setting_packs.py`
- `smoke_test.py`, `smoke_hybrid.py`, `run_deterministic_tests.py`, `preflight.py`
- `extract_sw5e_data.py`, `rebuild_lancedb.py`, `verify_lore_store.py`, `ingest_style.py`
- `audit_era_packs.py`, `split_era_pack.py`

### Core Code (KEEP ALL)
- `/backend/` - All application code
- `/frontend/` - All SvelteKit UI code
- `/ingestion/` - All ingestion pipeline code
- `/shared/` - Shared utilities
- `/storyteller/` - CLI interface
- `/data/style/` - All style guides
- `/data/static/starships.yaml`, `/data/static/ERA_PACK_PROMPT_TEMPLATE.md`, etc.
- `/static/passages/` - Passage content

---

## New Templates to CREATE

### 1. Campaign Initialization Template
**File:** `/docs/templates/CAMPAIGN_INIT_TEMPLATE.md`
- Document the campaign creation flow
- Provide template JSON for campaign world_state_json initialization
- Document required fields for SetupAutoRequest
- Include example campaign configurations

### 2. Database Seed Template
**File:** `/docs/templates/DB_SEED_TEMPLATE.md`
- Minimal viable campaign seed data
- Example SQL for creating a test campaign
- Reference all 21 migrations and their purposes

### 3. Era Pack Quick Reference
**File:** `/docs/ERA_PACK_QUICK_REFERENCE.md`
- Consolidate era pack documentation into one quick reference
- Link to detailed schema reference
- Include regeneration instructions

---

## Documentation Consolidation

### Files to Update
1. `README.md` - Update to reflect streamlined structure
2. `docs/01_repo_map.md` - Remove references to deleted directories
3. `docs/architecture.md` - Ensure current with V2.20 state

### Files to Remove References
- Any docs referencing `/tools/` migration
- Any docs referencing deleted era packs (update to say "can be regenerated")

---

## Summary

**Deletions:**
- 1 directory: `/docs/archive/`
- 1 directory: `/tools/`
- 5 era pack directories
- 13 legacy scripts
- 1 backup file

**Kept:**
- `_template` + `rebellion` era packs
- All core documentation (22 files)
- All essential validation/test scripts (14 files)
- All production code (backend, frontend, ingestion)

**New Templates:**
- 3 new template documentation files

**Result:** Clean, focused repository ready for V3.0 development with clear templates for regenerating content as needed.
