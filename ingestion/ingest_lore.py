"""Enriched RAG lore ingestion: PDF/EPUB/TXT with parent-child chunking and context prefixes.

- PDF: pymupdf4llm.to_markdown() for layout-preserving extraction (headers, tables).
- Parents ~1024 tokens; children ~256 tokens with overlap.
- Child text stored in LanceDB is prefixed: "[Source: {filename}, Section: {parent_header}] {child_text}".
- Metadata: time_period, planet, faction from CLI (or heuristic) on every chunk.
- Writes via LanceStore to unified lore_chunks table (never overwrites).

Usage:
  python -m ingestion.ingest_lore --input ./data/lore [--time-period LOTF] [--planet Tatooine] [--faction Empire]
  python -m ingestion.ingest_lore --input ./data/lore --source-type reference --collection lore --book-title "My Sourcebook"
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Ensure project root on path
_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from ingestion.character_aliases import extract_characters
from ingestion.chunking import chunk_text_by_tokens, count_tokens
from ingestion.classify_document import classify_document
from ingestion.era_aliases import load_era_aliases
from ingestion.manifest import input_file_hashes, write_run_manifest, check_chunk_id_scheme
from ingestion.npc_tagging import apply_npc_tags_to_chunks
from ingestion.store import LanceStore, stable_chunk_id, file_doc_id, CHUNK_ID_SCHEME
from ingestion.tagger import apply_tagger_to_chunks
from ingestion.era_normalization import apply_era_mode, resolve_era_mode, infer_era_from_input_root
from shared.lore_metadata import default_doc_type, default_section_kind, default_characters
from shared.config import EMBEDDING_DIMENSION, EMBEDDING_MODEL, ENABLE_CHARACTER_FACETS
from backend.app.world.era_pack_loader import get_era_pack

PARENT_TOKENS = 1024
CHILD_TOKENS = 256
CHILD_OVERLAP = 0.1
PARENT_OVERLAP = 0.1
SECTION_FALLBACK = "Section"
MAX_SECTION_LEN = 120


def _read_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _read_epub(path: Path) -> tuple[str, str | None, list[tuple[str, str]]]:
    from ingestion.epub_reader import read_epub as _read_epub_impl
    title, _author, _full, chapters = _read_epub_impl(path)
    return "\n\n".join(ch_text for _ch_title, ch_text in chapters), title, chapters


def _read_pdf(path: Path) -> str:
    """Extract PDF to Markdown with layout preservation (tables, headers) via pymupdf4llm."""
    try:
        import pymupdf4llm
        return pymupdf4llm.to_markdown(str(path)) or ""
    except Exception as e:
        logger.warning("PDF read failed %s: %s", path, e)
        return ""


def _parent_section_label(parent_text: str) -> str:
    """Extract a section label from parent chunk: first markdown header (# ## ###) or first line."""
    if not parent_text or not parent_text.strip():
        return SECTION_FALLBACK
    for line in parent_text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Markdown ATX header: # Header, ## Header, ### Header
        m = re.match(r"^#{1,6}\s+(.+)$", line)
        if m:
            label = m.group(1).strip()
            if len(label) > MAX_SECTION_LEN:
                label = label[: MAX_SECTION_LEN - 3] + "..."
            return label or SECTION_FALLBACK
        # Use first non-empty line as section (e.g. plain text doc)
        if len(line) > MAX_SECTION_LEN:
            line = line[: MAX_SECTION_LEN - 3] + "..."
        return line
    return SECTION_FALLBACK


def _metadata_heuristic(file_path: Path, text_sample: str) -> dict[str, str]:
    """Extract time_period, planet, faction from path and text. Heuristic."""
    time_period = ""
    planet = ""
    faction = ""
    name = file_path.stem.lower()
    if "lotf" in name or "legacy" in name:
        time_period = "LOTF"
    if "tatooine" in name or "tatooine" in text_sample[:2000].lower():
        planet = "Tatooine"
    if "empire" in name or "empire" in text_sample[:2000].lower():
        faction = "Empire"
    if "rebel" in name or "rebel" in text_sample[:2000].lower():
        faction = "Rebel"
    return {"time_period": time_period, "planet": planet, "faction": faction}


def _chunk_meta(meta: dict[str, str], text: str) -> dict[str, Any]:
    """Build standard metadata for a chunk; characters extracted from text via alias file."""
    time_period = meta.get("time_period", "")
    era = meta.get("era", time_period)  # canonical: store both for backward compat
    characters = extract_characters(text) if ENABLE_CHARACTER_FACETS else default_characters()
    return {
        "source": meta.get("source", ""),
        "chapter": meta.get("chapter", ""),
        "time_period": time_period,
        "era": era,
        "planet": meta.get("planet", ""),
        "faction": meta.get("faction", ""),
        "doc_type": meta.get("doc_type", default_doc_type()),
        "section_kind": meta.get("section_kind", default_section_kind()),
        "characters": characters,
        "related_npcs": [],
        "collection": meta.get("collection", "lore"),
        "source_type": meta.get("source_type", "reference"),
        "book_title": meta.get("book_title", ""),
    }


def _hierarchical_chunks(
    text: str,
    source: str,
    chapter: str,
    meta: dict[str, str],
    filename: str,
    doc_id: str = "",
) -> list[dict[str, Any]]:
    """Produce parent (~1024 tokens) and child (~256 tokens) chunks. Child text stored with prefix."""
    meta = dict(meta)
    meta.setdefault("source", source)
    meta.setdefault("chapter", chapter)
    parent_chunks = chunk_text_by_tokens(text, target_tokens=PARENT_TOKENS, overlap_percent=PARENT_OVERLAP)
    out: list[dict[str, Any]] = []
    for p_idx, parent_text in enumerate(parent_chunks):
        pid = stable_chunk_id(parent_text, source=f"{source}:{chapter}", chunk_index=p_idx, doc_id=doc_id)
        parent_header = _parent_section_label(parent_text)
        parent_meta = _chunk_meta(meta, parent_text)
        out.append({
            "id": pid,
            "text": parent_text,
            "level": "parent",
            "parent_id": "",
            **parent_meta,
        })
        child_chunks = chunk_text_by_tokens(parent_text, target_tokens=CHILD_TOKENS, overlap_percent=CHILD_OVERLAP)
        for c_idx, child_text in enumerate(child_chunks):
            cid = stable_chunk_id(child_text, source=f"{source}:{chapter}:{p_idx}", chunk_index=c_idx, doc_id=doc_id)
            # Enriched RAG: child text in LanceDB prefixed with source and section context
            stored_child_text = f"[Source: {filename}, Section: {parent_header}] {child_text}"
            child_meta = _chunk_meta(meta, child_text)
            out.append({
                "id": cid,
                "text": stored_child_text,
                "level": "child",
                "parent_id": pid,
                **child_meta,
            })
    return out


def ingest_file(
    path: Path,
    meta: dict[str, str],
    book_title_override: str | None = None,
    source_type: str = "reference",
    collection: str = "lore",
    era_aliases: dict[str, str] | None = None,
    input_dir: Path | None = None,
    era_mode: str = "legacy",
) -> list[dict[str, Any]]:
    """Ingest one file; return list of hierarchical chunk dicts. meta has time_period, planet, faction."""
    suf = path.suffix.lower()
    text = ""
    source = path.stem
    chapter = ""
    if suf == ".txt":
        text = _read_txt(path)
    elif suf == ".epub":
        full_text, title, chapters = _read_epub(path)
        text = full_text
        source = title or source
        if chapters:
            chapter = chapters[0][0] if chapters else ""
    elif suf == ".pdf":
        text = _read_pdf(path)
    else:
        return []
    if not text.strip():
        return []
    book_title = book_title_override or meta.get("book_title") or source
    meta = dict(meta)
    meta["source"] = source
    meta["chapter"] = chapter
    meta["book_title"] = book_title
    meta["source_type"] = source_type
    meta["collection"] = collection
    # CLI meta overrides heuristic for time_period/planet/faction; fill missing from heuristic
    heuristic = _metadata_heuristic(path, text)
    classification = classify_document(path, text[:2000], meta.get("time_period") or heuristic.get("time_period"), era_aliases)
    heuristic["doc_type"] = classification.get("doc_type", "")
    heuristic["section_kind"] = classification.get("section_kind_guess", "")
    inferred_era = classification.get("era") or heuristic.get("time_period") or "default"
    if era_mode == "folder" and not meta.get("time_period") and input_dir is not None:
        folder_era = infer_era_from_input_root(path, input_dir)
        inferred_era = folder_era or inferred_era
    final_time_period = meta.get("time_period") or inferred_era
    final_time_period = apply_era_mode(final_time_period, era_mode) or final_time_period
    final_meta = {
        "time_period": final_time_period,
        "era": final_time_period,
        "planet": meta.get("planet") or heuristic.get("planet", ""),
        "faction": meta.get("faction") or heuristic.get("faction", ""),
        "doc_type": meta.get("doc_type") or heuristic.get("doc_type", ""),
        "section_kind": meta.get("section_kind") or heuristic.get("section_kind", ""),
        "source": source,
        "chapter": chapter,
        "book_title": book_title,
        "source_type": source_type,
        "collection": collection,
    }
    return _hierarchical_chunks(text, source, chapter, final_meta, filename=path.name, doc_id=file_doc_id(path, input_dir=input_dir))


def _to_canonical_chunks(hierarchical: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert hierarchical chunk dicts to canonical {text, metadata} format for LanceStore."""
    canonical: list[dict[str, Any]] = []
    for c in hierarchical:
        chars = c.get("characters", default_characters())
        if not isinstance(chars, list):
            chars = list(chars) if chars else []
        related_npcs = c.get("related_npcs") or []
        if not isinstance(related_npcs, list):
            related_npcs = list(related_npcs) if related_npcs else []
        metadata = {
            "chunk_id": c.get("id", ""),
            "level": c.get("level", ""),
            "parent_id": str(c.get("parent_id", "") or ""),
            "source": c.get("source", ""),
            "chapter": c.get("chapter", ""),
            "time_period": c.get("time_period", ""),
            "era": c.get("era", c.get("time_period", "")),
            "planet": c.get("planet", ""),
            "faction": c.get("faction", ""),
            "doc_type": c.get("doc_type", default_doc_type()),
            "section_kind": c.get("section_kind", default_section_kind()),
            "characters": chars,
            "related_npcs": related_npcs,
            "collection": c.get("collection", "lore"),
            "source_type": c.get("source_type", "reference"),
            "book_title": c.get("book_title", ""),
        }
        canonical.append({"text": c["text"], "metadata": metadata})
    return canonical


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Enriched RAG: Ingest lore (PDF/EPUB/TXT) with parent-child chunking and context prefixes."
    )
    ap.add_argument("--input", "-i", type=str, default="./data/lore", help="Directory with .pdf/.epub/.txt")
    ap.add_argument("--db", type=str, default="./data/lancedb", help="LanceDB path")
    ap.add_argument("--time-period", type=str, default="", help="Override/set time_period for all chunks (e.g. LOTF)")
    ap.add_argument("--planet", type=str, default="", help="Override/set planet for all chunks (e.g. Tatooine)")
    ap.add_argument("--faction", type=str, default="", help="Override/set faction for all chunks (e.g. Empire)")
    ap.add_argument("--source-type", type=str, default="reference", help="Source type (reference, novel, etc.)")
    ap.add_argument("--collection", type=str, default="lore", help="Collection name for metadata")
    ap.add_argument("--book-title", type=str, help="Override book title (e.g. for PDFs without metadata)")
    ap.add_argument("--recursive", action="store_true", help="Recurse into subfolders")
    ap.add_argument("--era-aliases", type=str, help="JSON file mapping folder names to eras")
    ap.add_argument("--era-mode", choices=["legacy", "ui", "folder"], default=None, help="Era output mode: legacy (default), ui (canonical era keys), or folder (use top-level folder names)")
    ap.add_argument("--rebuild", action="store_true", help="Drop and recreate the LanceDB table (use after chunk_id_scheme change)")
    ap.add_argument("--era-pack", type=str, default="", help="Era pack id for NPC tagging (defaults to time_period)")
    ap.add_argument("--tag-npcs", dest="tag_npcs", action="store_true", help="Enable deterministic NPC tagging via era pack")
    ap.add_argument("--no-tag-npcs", dest="tag_npcs", action="store_false", help="Disable NPC tagging")
    ap.set_defaults(tag_npcs=None)
    ap.add_argument("--npc-tagging-mode", choices=["strict", "lenient"], default="strict", help="NPC tagging mode (strict or lenient)")
    ap.add_argument(
        "--delete-by",
        type=str,
        default="",
        help="Delete chunks by filter instead of ingesting. Format: era=REBELLION,source=mybook.epub,doc_type=novel,collection=lore",
    )
    args = ap.parse_args()

    # V2.5: Bulk delete mode (early exit)
    if args.delete_by:
        filters: dict[str, str] = {}
        for part in args.delete_by.split(","):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                filters[k.strip()] = v.strip()
        if not filters:
            logger.error("Invalid --delete-by format. Use: era=REBELLION,source=mybook.epub")
            return 1
        store = LanceStore(args.db)
        deleted = store.delete_by_filter(**filters)
        logger.info("Deleted %d chunks matching: %s", deleted, filters)
        return 0

    era_mode = resolve_era_mode(args.era_mode)

    # Scheme mismatch check: upgraded to hard error (V2.5)
    if not args.rebuild:
        warning = check_chunk_id_scheme(CHUNK_ID_SCHEME)
        if warning:
            logger.error("*** CHUNK ID SCHEME MISMATCH ***")
            logger.error(warning)
            logger.error("Re-run with --rebuild to recreate the table cleanly, or abort.")
            return 1

    data_dir = Path(args.input)
    if not data_dir.exists():
        logger.error("Directory does not exist: %s", data_dir)
        return 1
    globber = data_dir.rglob if args.recursive else data_dir.glob
    paths = list(globber("*.txt")) + list(globber("*.epub")) + list(globber("*.pdf"))
    if not paths:
        logger.warning("No .txt/.epub/.pdf in %s", data_dir)
        return 0
    input_hashes, hash_failures = input_file_hashes(paths)
    meta = {
        "time_period": (args.time_period or "").strip(),
        "planet": args.planet.strip(),
        "faction": args.faction.strip(),
    }
    era_aliases = load_era_aliases(args.era_aliases)
    all_chunks: list[dict] = []
    file_failures = 0
    for idx, p in enumerate(paths, 1):
        logger.info("[%d/%d] Processing: %s", idx, len(paths), p.name)
        try:
            all_chunks.extend(ingest_file(
                p,
                meta=meta,
                book_title_override=args.book_title,
                source_type=args.source_type,
                collection=args.collection,
                era_aliases=era_aliases,
                input_dir=data_dir,
                era_mode=era_mode,
            ))
        except Exception as e:
            logger.exception("Ingest failed %s: %s", p, e)
            file_failures += 1
    if not all_chunks:
        logger.error("No chunks produced (%d file failures)", file_failures)
        return 1
    canonical = _to_canonical_chunks(all_chunks)
    era_pack_id = (args.era_pack or args.time_period or "").strip()
    era_pack = get_era_pack(era_pack_id) if era_pack_id else None
    tag_npcs_enabled = args.tag_npcs if args.tag_npcs is not None else bool(era_pack)
    canonical, npc_tag_stats = apply_npc_tags_to_chunks(
        canonical,
        era_pack=era_pack,
        enabled=tag_npcs_enabled,
        mode=args.npc_tagging_mode,
    )
    if npc_tag_stats.get("collision_report_path"):
        logger.info("NPC collision report written: %s", npc_tag_stats["collision_report_path"])
    canonical, tagger_stats = apply_tagger_to_chunks(canonical)
    store = LanceStore(args.db, allow_overwrite=args.rebuild)
    logger.info("Writing %d chunks to LanceDB (with dedup)...", len(canonical))
    store_result = store.add_chunks(canonical)
    added = store_result.get("added", 0) if isinstance(store_result, dict) else len(canonical)
    skipped = store_result.get("skipped", 0) if isinstance(store_result, dict) else 0
    write_run_manifest(
        run_type="lore",
        input_files=input_hashes,
        chunking={
            "parent_tokens": PARENT_TOKENS,
            "parent_overlap": PARENT_OVERLAP,
            "child_tokens": CHILD_TOKENS,
            "child_overlap": CHILD_OVERLAP,
        },
        embedding_model=EMBEDDING_MODEL,
        embedding_dim=EMBEDDING_DIMENSION,
        tagger_enabled=tagger_stats.get("enabled", False),
        tagger_model=tagger_stats.get("model", ""),
        output_table="lore_chunks",
        vectordb_path=str(args.db),
        chunk_id_scheme=CHUNK_ID_SCHEME,
        counts={
            "chunks": len(canonical),
            "added": added,
            "skipped_dedup": skipped,
            "failed": int(hash_failures) + int(file_failures) + int(tagger_stats.get("failed", 0)),
        },
    )
    # V2.5: Validate era values for retrieval compatibility
    from ingestion.era_normalization import validate_era_for_retrieval
    era_values_seen: set[str] = set()
    for c in canonical:
        era_val = c.get("era") or c.get("time_period") or ""
        if era_val:
            era_values_seen.add(era_val)
    for ev in era_values_seen:
        valid, warn_msg = validate_era_for_retrieval(ev, era_mode)
        if not valid:
            logger.warning("Era validation: %s", warn_msg)

    logger.info(
        "Lore ingestion complete: %d chunks total, %d added, %d skipped (dedup), %d file failures",
        len(canonical), added, skipped, file_failures,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
