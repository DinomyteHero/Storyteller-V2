# Lore Pipeline Guide

A practical guide to organizing, ingesting, and querying lore for the Storyteller AI RAG system.

---

## 1. Recommended folder structure

Organize lore by **era** and **type** so the classifier can infer metadata from paths:

```text
data/
├── lore/
│   ├── lotf/                    # Era: LOTF (Legacy of the Force)
│   │   ├── novels/              # → doc_type: novel
│   │   │   ├── betrayal.epub
│   │   │   └── tempest.txt
│   │   ├── sourcebooks/         # → doc_type: sourcebook (filename: *sourcebook*, *rulebook*, *supplement*)
│   │   │   └── legacy_campaign_guide.pdf
│   │   └── adventures/          # → doc_type: adventure (filename: *adventure*, *module*, *scenario*)
│   │       └── dawn_of_defiance.txt
│   ├── clone_wars/              # Era: Clone Wars
│   │   └── novels/
│   └── high_republic/           # Era: High Republic
└── style/
    └── *.txt                    # Style docs (tone, pacing) — separate pipeline
```text

### Rebellion starter pack example

If you’re building a Rebellion MVP content pack, a simple layout is:

```text
data/lore/rebellion/
  sourcebooks/
    rebel_alliance_faction_sourcebook.txt
    galactic_empire_faction_sourcebook.txt
    tatooine_location_sourcebook.txt
  adventures/
    rebellion_adventure_stolen_codes.txt
    rebellion_adventure_safehouse_burn.txt
```text

**Path heuristics** (from `ingestion/classify_document.py`):

- **doc_type**: Folder containing `novel`, `books`, or `legends` → novel. Filename containing `sourcebook`, `rulebook`, `supplement` → sourcebook. `adventure`, `module`, `scenario` → adventure. `map`, `atlas`, `sector` → map.
- **era**: Path segment `lotf`, `legacy` → LOTF; `clone_wars` → Clone Wars; `high_republic` → High Republic; `old_republic`, `new_republic`, `gaw` also supported.

---

## 2. Document classification

Classification is **heuristic-first**, with an **optional LLM fallback** only when confidence is low.

| Step | Logic |
|------|-------|
| **doc_type** | From path/filename (novel, sourcebook, adventure, map). |
| **section_kind** | From first ~2000 chars: headings like "Equipment:", "Act I", "Faction:", "Planet:", "Chapter 1" + narrative → gear, hook, faction, location, lore/dialogue. |
| **era** | From `--era` / `--time-period` CLI, else inferred from path. |
| **LLM fallback** | Only if heuristic confidence < 0.7 and biographer LLM is configured. Uses biographer role; invalid JSON → keep heuristic result. |

No LLM is required; heuristics alone work for well-structured folders.

---

## 3. Metadata fields

| Field | Meaning | Used by |
|-------|---------|---------|
| **doc_type** | `novel`, `sourcebook`, `adventure`, `map`, `unknown` | Narrator (novel, sourcebook); Director (adventure); Mechanic (sourcebook, future). |
| **era** / **time_period** | Canonical era (e.g. LOTF, Clone Wars). Stored as both for compatibility. | Lore retrieval filter; voice retrieval (era-scoped). |
| **section_kind** | Content type: `lore`, `dialogue`, `gear`, `faction`, `location`, `hook`, `rules`, `unknown`. | Narrator (lore, location, faction); Director (hook); Mechanic (rules, gear, future). |
| **characters[]** | Canonical character IDs (e.g. `luke_skywalker`) present in the chunk. Populated via alias file during ingestion. | Voice retrieval (character_voice_chunks); lore filter. |
| **planet**, **faction** | Optional filters. Set via `ingest_lore` CLI (`--planet`, `--faction`) or heuristic from path/text. | Lore retrieval filters. |

---

## 4. Multi-era characters: aliases (era facets not implemented)

Characters like Luke can appear in multiple eras with different voices and knowledge, but the facet generation is incomplete.

| Concept | Status |
|---------|--------|
| **Aliases** | ✅ Working. Map display names ("Luke", "Master Skywalker") → canonical ID (`luke_skywalker`). Ingestion tags chunks with `characters[]` using word-boundary matching. |

---

## 5. Ingest, build facets, run

### 5.1 Ingest lore

Both scripts process files in the given directory by default. Use `--recursive` if your books are nested in subfolders.

**Recommended wrapper command (guardrails + dispatch):**

```powershell
python -m storyteller ingest --pipeline lore --input ./data/lore
```text

This wrapper validates inputs and then dispatches to `ingestion.ingest_lore`.

**Flat chunks** (~600 tokens, `ingest`):

```powershell
python -m ingestion.ingest --input_dir sample_data --era LOTF --source_type novel --out_db ./data/lancedb
```text

**Hierarchical** (parent 1024 / child 256, PDF support, `ingest_lore`):

```powershell
python -m ingestion.ingest_lore --input ./data/lore --db ./data/lancedb --time-period LOTF
```text

**UI era keys (recommended if you use the frontend era dropdown):**

```powershell
python -m ingestion.ingest_lore --input ./data/lore --db ./data/lancedb --era-mode ui
```text

**Rebellion UI-key ingestion (recommended for Rebellion era packs):**

```powershell
python -m ingestion.ingest_lore --input ./data/lore/rebellion --db ./data/lancedb --time-period REBELLION --era-mode ui --recursive
```text

Notes:
- Director retrieval expects `doc_type=adventure` + `section_kind=hook` (start files with `Adventure Summary:` / `Act I` / `Encounter:` and include `adventure` in the filename).
- Narrator retrieval expects `doc_type in {novel, sourcebook}` + `section_kind in {lore, location, faction}` (use `Faction:` / `Planet:` / `Location:` headings early; include `sourcebook` in the filename).

**Folder eras (recommended if your folder names are your era taxonomy):**

This stores the *top-level folder name* under `data/lore/` as `era`/`time_period` (e.g. `New Jedi Order Era` stays distinct).

```powershell
python -m ingestion.ingest_lore --input ./data/lore --db ./data/lancedb --era-mode folder --recursive
```text

In the frontend UI, choose **Era → Custom...** and enter the same folder name string so retrieval filters match.

Use `--era-aliases <file.json>` to map folder names to eras when your folder labels vary.

Use the same `--db` / `--out_db` path for both; both write to `lore_chunks`. Create `./data/lore` and add .txt/.epub/.pdf files first. Set `VECTORDB_PATH` to this path when starting the backend.

### 5.2 Build character facets (NOT RECOMMENDED - incomplete implementation)

# DO NOT RUN - produces unusable output

### 5.3 Run backend

Model defaults (configured in `backend/app/config.py`):

| Role | Default Model | VRAM |
|------|---------------|------|
| Director, Narrator | `mistral-nemo:latest` | ~7 GB |
| Architect, Casting, Biographer, KG Extractor | `qwen3:4b` | ~2 GB |
| Mechanic, Ingestion Tagger | `qwen3:8b` | ~5 GB |
| Embedding | `nomic-embed-text` | minimal |

Only one model is loaded at a time (specialist swapping), so peak VRAM equals the largest model (~7 GB for mistral-nemo). Override per-role via `STORYTELLER_{ROLE}_MODEL` env vars.

```powershell
$env:VECTORDB_PATH = "./data/lancedb"
$env:PYTHONPATH = (Get-Location).Path
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```text

---

## 6. Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| **Empty lore retrieval** | `VECTORDB_PATH` not set or wrong; `lore_chunks` missing/empty; schema mismatch. | Set `VECTORDB_PATH` to the same path as `--out_db` / `--db`. Run ingestion first. Ensure `sentence-transformers` is installed. |
| **"Not a directory" or "No .txt/.epub files"** | Input path missing or empty. | Create the directory and add files, or use `sample_data` for a quick test. |
| **Wrong era results** | Era filter not applied; chunks have wrong `era` / `time_period`. | Pass `--era` / `--time-period` at ingest. Check chunk metadata: `python -m ingestion.query --query "test" --db ./data/lancedb` and inspect output. |
| **No voice snippets for NPCs** | Character facets feature is not implemented. Voice retrieval is disabled by default. | This is expected behavior. The system works without character voice snippets - the Narrator generates appropriate dialogue. |
| **Missing `lore_chunks` table** | No ingestion run. | Run `ingest` or `ingest_lore` first. Use `sample_data` if you have no files yet. |
| **Classifier returns unknown** | Path doesn't match heuristics; text has no recognizable headings. | Put files in `novels/`, `sourcebooks/`, etc. Or rely on `--source_type` / `--era` CLI overrides. Note: use `--recursive` for nested folders. |
| **PDF ingestion fails** | `pymupdf4llm` not installed. | `pip install pymupdf4llm`. PDF support is only in `ingest_lore`, not `ingest`. |

---

## See also

- **USER_GUIDE § 7–8**: Character aliases, era facets, pipeline order.
- **README.md**: Quick start, env vars, verification steps.
