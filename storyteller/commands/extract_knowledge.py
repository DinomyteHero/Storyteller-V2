"""``storyteller extract-knowledge`` — extract knowledge graph from ingested lore chunks.

Reads parent chunks from LanceDB, extracts entities/relationships/summaries
via local LLM, and stores results in the SQLite knowledge graph tables.
Supports resume via checkpoints.
"""
from __future__ import annotations

import logging
import math
import sys

logger = logging.getLogger(__name__)


def register(subparsers) -> None:
    p = subparsers.add_parser(
        "extract-knowledge",
        help="Extract knowledge graph from ingested lore chunks",
    )
    p.add_argument(
        "--era", type=str, default="rebellion",
        help="Era to extract (default: rebellion)",
    )
    p.add_argument(
        "--resume", action="store_true",
        help="Resume from last checkpoint (skip completed chapters)",
    )
    p.add_argument(
        "--batch-size", type=int, default=3,
        help="Parent chunks per LLM call (default: 3)",
    )
    p.add_argument(
        "--db", type=str, default="./data/storyteller.db",
        help="SQLite DB path for knowledge graph storage",
    )
    p.add_argument(
        "--vectordb", type=str, default=None,
        help="LanceDB path (source for chunks; default: auto-detect)",
    )
    p.add_argument(
        "--skip-synthesis", action="store_true",
        help="Skip cross-book synthesis step",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Estimate calls without running extraction",
    )
    p.set_defaults(func=run)


def run(args) -> int:
    """Main extraction loop."""
    from backend.app.kg.chunk_reader import read_parent_chunks_by_book, estimate_extraction_calls
    from backend.app.kg.store import KGStore
    from backend.app.kg.entity_resolution import build_alias_lookup
    from backend.app.kg.extractor import extract_from_chunks, store_extraction_result

    era = args.era
    print(f"\n  Knowledge Graph Extraction")
    print(f"  Era: {era}")
    print(f"  Batch size: {args.batch_size}")
    print()

    # Load chunks from LanceDB
    print("  Loading parent chunks from LanceDB...")
    chunks_by_book = read_parent_chunks_by_book(db_path=args.vectordb, era=era)
    if not chunks_by_book:
        print("  ERROR: No parent chunks found. Run ingestion first.")
        return 1

    estimates = estimate_extraction_calls(chunks_by_book, chunks_per_call=args.batch_size)
    print(f"  Found {estimates['total_chunks']} parent chunks across {estimates['total_books']} books")
    print(f"  Estimated LLM calls: {estimates['estimated_calls']}")
    print(f"  Estimated time: ~{estimates['estimated_minutes_at_50s']} minutes")
    print()

    if args.dry_run:
        print("  [DRY RUN] No extraction performed.")
        # Print book list
        for book in sorted(chunks_by_book.keys()):
            chapters = chunks_by_book[book]
            total = sum(len(c) for c in chapters.values())
            print(f"    {book}: {len(chapters)} chapters, {total} chunks")
        return 0

    # Initialize stores and lookups
    print("  Initializing knowledge graph store...")
    kg_store = KGStore(args.db)
    alias_lookup = build_alias_lookup()
    known_characters = _build_known_characters_list(alias_lookup)

    print(f"  Loaded {len(alias_lookup)} character aliases")
    print()

    # Initialize LLM
    try:
        from backend.app.core.agents.base import AgentLLM
        llm = AgentLLM("kg_extractor")
        print("  LLM initialized for kg_extractor role")
    except Exception as e:
        print(f"  ERROR: Failed to initialize LLM: {e}")
        print("  Make sure Ollama is running and the model is available.")
        return 1

    # Phase 1: Per-chapter extraction
    print("\n  === Phase 1: Per-chapter extraction ===\n")
    total_entities = 0
    total_triples = 0
    total_summaries = 0
    books_processed = 0
    chapters_processed = 0
    chapters_skipped = 0

    try:
        from tqdm import tqdm
        has_tqdm = True
    except ImportError:
        has_tqdm = False

    sorted_books = sorted(chunks_by_book.keys())
    book_iter = tqdm(sorted_books, desc="Books", unit="book") if has_tqdm else sorted_books

    for book_title in book_iter:
        chapters = chunks_by_book[book_title]
        sorted_chapters = sorted(chapters.keys())

        for chapter_idx, chapter_title in enumerate(sorted_chapters):
            # Check checkpoint
            if args.resume:
                status = kg_store.get_checkpoint_status(book_title, chapter_title)
                if status == "completed":
                    chapters_skipped += 1
                    continue

            chunks = chapters[chapter_title]
            if not chunks:
                continue

            kg_store.set_checkpoint(book_title, "in_progress", chapter_title=chapter_title)

            # Process in batches
            for batch_start in range(0, len(chunks), args.batch_size):
                batch = chunks[batch_start:batch_start + args.batch_size]
                try:
                    result = extract_from_chunks(
                        batch, book_title, chapter_title, era,
                        llm, alias_lookup, known_characters,
                    )
                    store_extraction_result(
                        result, kg_store, book_title, chapter_title, era,
                        chapter_index=chapter_idx,
                        source_chunk_ids=[c.get("chunk_id", "") for c in batch],
                    )
                    total_entities += len(result.entities)
                    total_triples += len(result.triples)
                    if result.chapter_summary:
                        total_summaries += 1
                    for w in result.warnings:
                        logger.warning("[%s/%s] %s", book_title[:30], chapter_title[:20], w)
                except Exception:
                    logger.exception("Extraction failed for %s / %s", book_title, chapter_title)
                    kg_store.set_checkpoint(
                        book_title, "failed", chapter_title=chapter_title,
                        error="extraction exception",
                    )
                    continue

            kg_store.set_checkpoint(book_title, "completed", chapter_title=chapter_title)
            chapters_processed += 1

        books_processed += 1

    print(f"\n  Phase 1 complete:")
    print(f"    Books processed: {books_processed}")
    print(f"    Chapters processed: {chapters_processed}")
    if chapters_skipped:
        print(f"    Chapters skipped (resumed): {chapters_skipped}")
    print(f"    Entities extracted: {total_entities}")
    print(f"    Triples extracted: {total_triples}")
    print(f"    Chapter summaries: {total_summaries}")
    print(f"    Total KG entities: {kg_store.entity_count()}")
    print(f"    Total KG triples: {kg_store.triple_count()}")

    # Phase 2: Cross-book synthesis
    if not args.skip_synthesis:
        print("\n  === Phase 2: Cross-book synthesis ===\n")
        try:
            from backend.app.kg.synthesis import (
                synthesize_character_profiles,
                synthesize_location_dossiers,
                detect_contradictions,
            )
            synth_status = kg_store.get_checkpoint_status("__synthesis__", phase="synthesis")
            if args.resume and synth_status == "completed":
                print("  Synthesis already completed (skipping)")
            else:
                kg_store.set_checkpoint("__synthesis__", "in_progress", phase="synthesis")

                print("  Synthesizing character profiles...")
                char_count = synthesize_character_profiles(kg_store, llm, era)
                print(f"    Generated {char_count} character arc summaries")

                print("  Synthesizing location dossiers...")
                loc_count = synthesize_location_dossiers(kg_store, llm, era)
                print(f"    Generated {loc_count} location dossiers")

                print("  Detecting contradictions...")
                contradictions = detect_contradictions(kg_store, era)
                if contradictions:
                    print(f"    Found {len(contradictions)} contradictions (logged as warnings)")
                    for c in contradictions[:10]:
                        logger.warning("Contradiction: %s", c)
                else:
                    print("    No contradictions detected")

                kg_store.set_checkpoint("__synthesis__", "completed", phase="synthesis")
        except Exception:
            logger.exception("Synthesis phase failed")
            kg_store.set_checkpoint("__synthesis__", "failed", phase="synthesis", error="synthesis exception")
            print("  WARNING: Synthesis failed, but extraction data is preserved.")

    print("\n  Knowledge Graph extraction complete!")
    print(f"  Database: {args.db}")
    print(f"  Entities: {kg_store.entity_count()}")
    print(f"  Triples: {kg_store.triple_count()}")
    kg_store.close()
    return 0


def _build_known_characters_list(alias_lookup: dict[str, str]) -> list[str]:
    """Build a list of known character display names from the alias lookup."""
    # Get unique canonical IDs, then pick the longest alias for each as display name
    id_to_names: dict[str, list[str]] = {}
    for alias, canonical_id in alias_lookup.items():
        id_to_names.setdefault(canonical_id, []).append(alias)
    # Pick the longest name for each character (most complete name)
    display_names = []
    for canonical_id, names in id_to_names.items():
        best = max(names, key=len)
        display_names.append(best.title())
    return sorted(display_names)
