"""CLI for ingesting documents into the vector store.

DEPRECATED: This module is the legacy ingestion path. Use ingestion.ingest_lore instead.
This file will be removed in V3.0. See ingestion/ingest_lore.py for the current pipeline.

Usage (legacy):
  python -m ingestion.ingest --input_dir <dir> --era LOTF --source_type novel --out_db ./data/lancedb

Supported: TXT (book_title from filename), EPUB (metadata + spine/nav chapters). PDF is TODO.
"""
import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional

from ingestion.chunking import chunk_text_smart
from ingestion.classify_document import classify_document
from ingestion.era_aliases import load_era_aliases
from ingestion.era_normalization import apply_era_mode, resolve_era_mode, infer_era_from_input_root
from ingestion.epub_reader import read_epub
from ingestion.manifest import input_file_hashes, write_run_manifest, check_chunk_id_scheme
from ingestion.npc_tagging import apply_npc_tags_to_chunks
from ingestion.store import LanceStore, stable_chunk_id, file_doc_id, CHUNK_ID_SCHEME
from ingestion.tagger import apply_tagger_to_chunks
from shared.lore_metadata import (
    DOC_TYPE_NOVEL,
    DOC_TYPE_UNKNOWN,
    default_characters,
    default_doc_type,
    default_section_kind,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from shared.config import EMBEDDING_DIMENSION, EMBEDDING_MODEL
from backend.app.content.repository import CONTENT_REPOSITORY


def read_txt(path: Path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# PDF: optional, left as TODO
# def read_pdf(path: Path) -> str: ...


def _metadata(
    era: str,
    source_type: str,
    book_title: str,
    chapter_title: Optional[str],
    chapter_index: Optional[int],
    chunk_id: str,
    chunk_index: int,
    collection: str = "novels",
    doc_type: str = "",
    section_kind: str = "",
    characters: Optional[List[str]] = None,
) -> dict:
    """Build metadata for canonical chunk format. Unified schema defaults for novels."""
    return {
        "era": era,
        "time_period": era,  # canonical: store both for backward compat
        "source_type": source_type,
        "book_title": book_title,
        "chapter_title": chapter_title,
        "chapter_index": chapter_index,
        "chunk_id": chunk_id,
        "chunk_index": chunk_index,
        "collection": collection,
        "level": "",
        "parent_id": "",
        "source": book_title,  # novels: source = book_title or filename
        "chapter": chapter_title or "",
        "doc_type": doc_type or default_doc_type(),
        "section_kind": section_kind or default_section_kind(),
        "characters": characters if characters is not None else default_characters(),
        "related_npcs": [],
    }


def ingest_txt(file_path: Path, era: str, source_type: str, collection: str = "novels", doc_type: str = "", section_kind: str = "", input_dir: Path | None = None) -> List[dict]:
    """Ingest TXT: book_title derived from filename. Single logical chapter."""
    book_title = file_path.stem
    doc_id = file_doc_id(file_path, input_dir=input_dir)
    logger.info("Ingesting TXT: %s (title from filename: %s, doc_id: %s)", file_path.name, book_title, doc_id)
    text = read_txt(file_path)
    text_chunks = chunk_text_smart(text, target_tokens=600, overlap_percent=0.1)
    # Auto-classify if not provided; fall back to source_type when classifier returns unknown
    if not doc_type or not section_kind:
        classification = classify_document(file_path, text[:2000] if text else None, era)
        cls_dt = classification.get("doc_type", "")
        dt = doc_type or (cls_dt if cls_dt and cls_dt != DOC_TYPE_UNKNOWN else "") or _doc_type_from_source_type(source_type)
        sk = section_kind or classification.get("section_kind_guess", "") or default_section_kind()
    else:
        dt = doc_type
        sk = section_kind
    out = []
    for i, t in enumerate(text_chunks):
        cid = stable_chunk_id(t, source=book_title, chunk_index=i, doc_id=doc_id)
        characters = default_characters()
        out.append({
            "text": t,
            "metadata": _metadata(
                era, source_type, book_title,
                chapter_title=None, chapter_index=0,
                chunk_id=cid, chunk_index=i,
                collection=collection,
                doc_type=dt,
                section_kind=sk,
                characters=characters,
            ),
        })
    logger.info("Created %d chunks from %s", len(out), file_path.name)
    return out


def _doc_type_from_source_type(source_type: str) -> str:
    """Map legacy source_type to doc_type when not explicitly set."""
    if source_type == "novel":
        return DOC_TYPE_NOVEL
    return default_doc_type()


def ingest_epub(
    file_path: Path,
    era: str,
    source_type: str,
    book_title_override: Optional[str] = None,
    collection: str = "novels",
    doc_type: str = "",
    section_kind: str = "",
    input_dir: Path | None = None,
) -> List[dict]:
    """Ingest EPUB: book_title from metadata if possible, else filename; chapters via spine/nav."""
    logger.info("Ingesting EPUB: %s", file_path.name)
    epub_title, author, _full_text, chapters = read_epub(file_path)
    book_title = book_title_override or epub_title or file_path.stem
    doc_id = file_doc_id(file_path, input_dir=input_dir)
    if author:
        logger.info("Book: %s by %s", book_title, author)
    else:
        logger.info("Book: %s", book_title)
    logger.info("Chapters: %d", len(chapters))
    # Auto-classify if not provided; fall back to source_type when classifier returns unknown
    if not doc_type or not section_kind:
        sample = _full_text[:2000] if _full_text else (chapters[0][1][:2000] if chapters else None)
        classification = classify_document(file_path, sample, era)
        cls_dt = classification.get("doc_type", "")
        dt = doc_type or (cls_dt if cls_dt and cls_dt != DOC_TYPE_UNKNOWN else "") or _doc_type_from_source_type(source_type)
        sk = section_kind or classification.get("section_kind_guess", "") or default_section_kind()
    else:
        dt = doc_type
        sk = section_kind
    out = []
    for ch_idx, (ch_title, ch_text) in enumerate(chapters):
        ch_chunks = chunk_text_smart(ch_text, target_tokens=600, overlap_percent=0.1)
        for i, t in enumerate(ch_chunks):
            cid = stable_chunk_id(t, source=f"{book_title}:{ch_title or ch_idx}", chunk_index=i, doc_id=doc_id)
            characters = default_characters()
            out.append({
                "text": t,
                "metadata": _metadata(
                    era, source_type, book_title,
                    chapter_title=ch_title, chapter_index=ch_idx,
                    chunk_id=cid, chunk_index=i,
                    collection=collection,
                    doc_type=dt,
                    section_kind=sk,
                    characters=characters,
                ),
            })
    logger.info("Created %d chunks from EPUB", len(out))
    return out


def ingest_file(
    file_path: Path,
    era: str,
    source_type: str,
    book_title_override: Optional[str] = None,
    collection: str = "novels",
    doc_type: str = "",
    section_kind: str = "",
    input_dir: Path | None = None,
) -> List[dict]:
    suf = file_path.suffix.lower()
    if suf == ".txt":
        return ingest_txt(file_path, era, source_type, collection, doc_type, section_kind, input_dir=input_dir)
    if suf == ".epub":
        return ingest_epub(file_path, era, source_type, book_title_override, collection, doc_type, section_kind, input_dir=input_dir)
    if suf == ".pdf":
        # PDF: optional, left as TODO
        logger.warning("PDF support is TODO; skipping %s", file_path.name)
        return []
    raise ValueError("Unsupported format: %s (supported: .txt, .epub)" % suf)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Ingest TXT/EPUB into LanceDB (PDF is TODO)."
    )
    ap.add_argument("--input_dir", type=str, required=True, help="Directory with .txt / .epub files")
    ap.add_argument("--era", type=str, default="LOTF", help="Era tag (use 'auto' to infer from path)")
    ap.add_argument("--source_type", type=str, default="novel", help="Source type")
    ap.add_argument("--collection", type=str, default="novels", help="Collection name (default: novels)")
    ap.add_argument("--out_db", type=str, default="./data/lancedb", help="LanceDB path")
    ap.add_argument("--book_title", type=str, help="Override book title (EPUB only; TXT uses filename)")
    ap.add_argument("--recursive", action="store_true", help="Recurse into subfolders")
    ap.add_argument("--era-aliases", type=str, help="JSON file mapping folder names to eras")
    ap.add_argument("--era-mode", choices=["legacy", "ui", "folder"], default=None, help="Era output mode: legacy (default), ui (canonical era keys), or folder (use top-level folder names)")
    ap.add_argument("--rebuild", action="store_true", help="Drop and recreate the LanceDB table (use after chunk_id_scheme change)")
    ap.add_argument("--era-pack", type=str, default="", help="Era pack id for NPC tagging (defaults to --era)")
    ap.add_argument("--tag-npcs", dest="tag_npcs", action="store_true", help="Enable deterministic NPC tagging via era pack")
    ap.add_argument("--no-tag-npcs", dest="tag_npcs", action="store_false", help="Disable NPC tagging")
    ap.set_defaults(tag_npcs=None)
    ap.add_argument("--npc-tagging-mode", choices=["strict", "lenient"], default="strict", help="NPC tagging mode (strict or lenient)")
    args = ap.parse_args()

    era_mode = resolve_era_mode(args.era_mode)

    # Scheme mismatch check
    if not args.rebuild:
        warning = check_chunk_id_scheme(CHUNK_ID_SCHEME)
        if warning:
            logger.warning("*** %s ***", warning)

    base = Path(args.input_dir)
    if not base.is_dir():
        logger.error("Not a directory: %s", base)
        return 1

    globber = base.rglob if args.recursive else base.glob
    txt_files = list(globber("*.txt"))
    epub_files = list(globber("*.epub"))
    # PDF left as TODO
    paths = txt_files + epub_files
    if not paths:
        logger.warning("No .txt or .epub files in %s", base)
        return 1
    input_hashes, hash_failures = input_file_hashes(paths)

    era_aliases = load_era_aliases(args.era_aliases)
    store = LanceStore(args.out_db, allow_overwrite=args.rebuild)
    all_chunks = []
    file_failures = 0
    for idx, p in enumerate(paths, 1):
        logger.info("[%d/%d] Processing: %s", idx, len(paths), p.name)
        try:
            era = args.era
            if not era or era.lower() in ("auto", "infer"):
                if era_mode == "folder":
                    inferred = infer_era_from_input_root(p, base)
                else:
                    inferred = None
                if not inferred:
                    inferred = classify_document(p, None, None, era_aliases).get("era")
                era = inferred or "default"
            era = apply_era_mode(era, era_mode) or era
            chunks = ingest_file(
                p,
                era=era,
                source_type=args.source_type,
                book_title_override=args.book_title,
                collection=args.collection,
                input_dir=base,
            )
            all_chunks.extend(chunks)
        except Exception as e:
            logger.exception("Ingest failed for %s: %s", p, e)
            file_failures += 1
            # Continue with remaining files instead of aborting
            continue

    if not all_chunks:
        logger.error("No chunks produced (%d file failures)", file_failures)
        return 1
    era_pack_id = (args.era_pack or args.era or "").strip()
    era_pack = None
    if era_pack_id:
        try:
            era_pack = CONTENT_REPOSITORY.get_pack(era_pack_id)
        except Exception as exc:
            logger.error("Failed to load era pack '%s': %s", era_pack_id, exc, exc_info=True)
    tag_npcs_enabled = args.tag_npcs if args.tag_npcs is not None else bool(era_pack)
    all_chunks, npc_tag_stats = apply_npc_tags_to_chunks(
        all_chunks,
        era_pack=era_pack,
        enabled=tag_npcs_enabled,
        mode=args.npc_tagging_mode,
    )
    if npc_tag_stats.get("collision_report_path"):
        logger.info("NPC collision report written: %s", npc_tag_stats["collision_report_path"])
    all_chunks, tagger_stats = apply_tagger_to_chunks(all_chunks)
    logger.info("Writing %d chunks to LanceDB (with dedup)...", len(all_chunks))
    store_result = store.add_chunks(all_chunks)
    added = store_result.get("added", 0) if isinstance(store_result, dict) else len(all_chunks)
    skipped = store_result.get("skipped", 0) if isinstance(store_result, dict) else 0
    write_run_manifest(
        run_type="lore",
        input_files=input_hashes,
        chunking={"strategy": "smart_paragraph", "target_tokens": 600, "overlap_percent": 0.1},
        embedding_model=EMBEDDING_MODEL,
        embedding_dim=EMBEDDING_DIMENSION,
        tagger_enabled=tagger_stats.get("enabled", False),
        tagger_model=tagger_stats.get("model", ""),
        output_table="lore_chunks",
        vectordb_path=str(args.out_db),
        chunk_id_scheme=CHUNK_ID_SCHEME,
        counts={
            "chunks": len(all_chunks),
            "added": added,
            "skipped_dedup": skipped,
            "failed": int(hash_failures) + int(file_failures) + int(tagger_stats.get("failed", 0)),
        },
    )
    logger.info(
        "Ingestion complete: %d chunks total, %d added, %d skipped (dedup), %d file failures → %s",
        len(all_chunks), added, skipped, file_failures, args.out_db,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
