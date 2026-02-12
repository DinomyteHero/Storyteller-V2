# Ingestion Module

Ingest TXT, EPUB, and PDF documents into a LanceDB vector store. Two pipelines are available:

- **Flat ingestion** (`ingest.py`): TXT/EPUB → ~600-token chunks with ~10% overlap
- **Hierarchical ingestion** (`ingest_lore.py`): PDF/EPUB/TXT → parent (~1024 tokens) + child (~256 tokens) chunks with parent-child relationships

## Supported Formats

| Format | Flat (`ingest.py`) | Hierarchical (`ingest_lore.py`) | Notes |
| ------ | ------------------ | -------------------------------- | ----- |
| **TXT** | ✅ | ✅ | Book title from filename |
| **EPUB** | ✅ | ✅ | Title from metadata; chapters from spine/nav |
| **PDF** | ❌ (skipped with warning) | ✅ | Uses `pymupdf4llm` for layout-preserving extraction |

## Where to Put Data

Put source files in any directory (e.g., `./data/lore/`, `./data/books/`, `sample_data/`). Use that path as `--input_dir` (flat) or `--input` (hierarchical) when ingesting.

See `docs/lore_pipeline_guide.md` for recommended folder structure organized by era and doc_type.

## Commands

### Recommended Wrapper (Storyteller CLI)

```powershell
python -m storyteller ingest --input ./data/lore --pipeline lore
```

The wrapper adds guardrails (input validation, embedding-model preflight, PDF warning when `--pipeline simple`) and then dispatches to `ingestion.ingest` or `ingestion.ingest_lore`.

### Flat Lore Ingestion

```powershell
python -m ingestion.ingest --input_dir <directory> --era LOTF --source_type novel --out_db ./data/lancedb
```

- `--input_dir`: Directory containing .txt and .epub files (required)
- `--era`: Era tag (default: LOTF)
- `--source_type`: Source type (default: novel)
- `--out_db`: LanceDB output path (default: ./data/lancedb)
- `--book_title`: Override book title for EPUB only; TXT always uses filename
- `--recursive`: Recurse into subfolders
- `--era-aliases`: JSON file mapping folder names to eras (e.g., `{"Legacy Era":"LOTF"}`)
- `--era-mode`: `legacy` (default), `ui` (canonicalize to standard era keys), or `folder` (use top-level folder names as eras)
- `--era auto`: Infer era from folder names (uses aliases + path segments)
- `--era-pack`: Era pack id for deterministic NPC tagging (defaults to `--era`)
- `--tag-npcs` / `--no-tag-npcs`: Enable or disable NPC tagging
- `--npc-tagging-mode`: `strict` (default) or `lenient`

### Hierarchical Lore Ingestion

```powershell
python -m ingestion.ingest_lore --input ./data/lore --db ./data/lancedb
```

- `--input`, `-i`: Directory with .pdf/.epub/.txt files (default: ./data/lore)
- `--db`: LanceDB path (default: ./data/lancedb)
- `--time-period`: Override time_period metadata (e.g., LOTF)
- `--planet`: Override planet metadata
- `--faction`: Override faction metadata
- `--source-type`: Source type (default: reference)
- `--collection`: Collection name (default: lore)
- `--book-title`: Override book title
- `--recursive`: Recurse into subfolders
- `--era-aliases`: JSON file mapping folder names to eras
- `--era-mode`: `legacy` (default), `ui` (canonicalize to standard era keys), or `folder` (use top-level folder names as eras)
- `--era-pack`: Era pack id for deterministic NPC tagging (defaults to `--time-period`)
- `--tag-npcs` / `--no-tag-npcs`: Enable or disable NPC tagging
- `--npc-tagging-mode`: `strict` (default) or `lenient`
- `--delete-by`: Bulk delete mode (skip ingest) using metadata filters, e.g. `--delete-by "era=REBELLION,doc_type=adventure"`

You can also set `STORYTELLER_ERA_MODE=ui` (or `folder`) to make that mode the default when the flag is not provided.

### Rebellion MVP (starter pack)

This repo includes a ready-to-ingest Rebellion starter pack under:

- `data/lore/rebellion/sourcebooks/` (Narrator grounding)
- `data/lore/rebellion/adventures/` (Director hook grounding)

Recommended ingestion command (UI-era keys so runtime filters match the frontend):

```powershell
python -m ingestion.ingest_lore --input ./data/lore/rebellion --db ./data/lancedb --time-period REBELLION --era-mode ui --recursive
```

Notes:

- Director retrieval expects `doc_type=adventure` + `section_kind=hook` (use filenames containing `adventure` and start the text with `Adventure Summary:` / `Act I` / `Encounter:`).
- Narrator retrieval expects `doc_type in {novel, sourcebook}` + `section_kind in {lore, location, faction}` (use filenames containing `sourcebook` and start the text with `Chapter` / `Faction:` / `Planet:` / `Location:`).

### Character Voice Facets (Not Functional - Do Not Use)

```powershell
# DO NOT RUN - produces unusable output

The implementation is incomplete - it uses deterministic heuristics (modal verb counts, sentence length) instead of LLM-based character voice analysis. The system works fine without character facets.

### Query

```powershell
python -m ingestion.query --query "..." --k 5 --era LOTF --source_type novel --db ./data/lancedb
```

Example (Rebellion):

```powershell
python -m ingestion.query --query "ISB tactics" --k 5 --era REBELLION --db ./data/lancedb
```

## Chunking and Metadata

### Flat Pipeline

- ~600-token chunks with ~10% overlap; chunks do not cross chapter boundaries
- Per-chunk metadata: `era`, `source_type`, `book_title`, `chapter_title`, `chapter_index`, `chunk_id`, `chunk_index`
- Optional: `related_npcs` (from Era Pack tagging)

### Hierarchical Pipeline

- Parent chunks: ~1024 tokens; child chunks: ~256 tokens
- Child text prefixed: `[Source: {filename}, Section: {parent_header}] {child_text}`
- Parent-child relationship via `parent_id` UUID and `level` field (`"parent"` or `"child"`)
- Per-chunk metadata: `source`, `chapter`, `time_period`, `planet`, `faction`, `doc_type`, `section_kind`, `characters_json`, `level`, `parent_id`
- Optional: `related_npcs` (from Era Pack tagging)

### Embeddings

- Default: `sentence-transformers/all-MiniLM-L6-v2` (384-dim)
- Override via `EMBEDDING_MODEL` and `EMBEDDING_DIMENSION` env vars
- If you change embedding model, rebuild LanceDB: `python scripts/rebuild_lancedb.py --db ./data/lancedb`

## Optional LLM Tagger

When `INGESTION_TAGGER_ENABLED=1`, chunks are sent to a local LLM (default `qwen3:8b`) for metadata enrichment. The tagger outputs: `doc_type`, `section_kind`, `entities` (characters, factions, planets, items), `timeline` (era, start, end, confidence), `summary_1s`, and `injection_risk`.

On failure, the tagger logs a warning and falls back to empty/default values. See `ingestion/tagger.py` for the full schema.

## Tests

```powershell
# Run all ingestion tests
python -m pytest ingestion/ -q

# Individual test modules
python -m pytest ingestion/test_chunking.py
python -m pytest ingestion/test_epub.py
python -m pytest ingestion/test_character_aliases.py
python -m pytest ingestion/test_classify_document.py
python -m pytest ingestion/test_manifest.py
python -m pytest ingestion/test_tagger.py
python -m pytest ingestion/test_tagger_pipeline.py

- `docs/lore_pipeline_guide.md` — recommended folder structure, classification, multi-era characters
- `docs/05_rag_and_ingestion.md` — full RAG architecture and retrieval details
- `docs/user_guide.md` §7–8 — character aliases and voice facets user guide
