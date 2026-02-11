"""Read parent chunks from LanceDB for KG extraction.

Groups chunks by book_title -> chapter -> sorted list, providing the
source data for the extraction pipeline.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

import lancedb

from backend.app.config import resolve_vectordb_path, LORE_TABLE_NAME

logger = logging.getLogger(__name__)


def read_parent_chunks_by_book(
    db_path: str | Path | None = None,
    era: str = "rebellion",
    table_name: str | None = None,
) -> dict[str, dict[str, list[dict]]]:
    """Read all parent-level chunks from LanceDB, grouped by book -> chapter.

    Returns:
        {book_title: {chapter_title: [chunk_dicts sorted by chunk_index]}}

    Filters: level='parent', era matches the given era (case-insensitive).
    """
    db_path = resolve_vectordb_path(db_path)
    table_name = table_name or LORE_TABLE_NAME

    try:
        db = lancedb.connect(str(db_path))
        table = db.open_table(table_name)
    except Exception:
        logger.exception("Failed to open LanceDB table %s at %s", table_name, db_path)
        return {}

    try:
        # Read parent chunks filtered by era
        # LanceDB where clause is SQL-like
        era_lower = era.lower()
        df = table.search().where(
            f"level = 'parent' AND (LOWER(era) = '{era_lower}' OR LOWER(time_period) = '{era_lower}')",
            prefilter=True,
        ).limit(100_000).to_pandas()
    except Exception:
        logger.exception("Failed to query parent chunks for era=%s", era)
        return {}

    if df.empty:
        logger.warning("No parent chunks found for era=%s in %s", era, table_name)
        return {}

    # Group by book_title -> chapter_title
    result: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for _, row in df.iterrows():
        book = str(row.get("book_title", "") or row.get("source", "") or "Unknown")
        chapter = str(row.get("chapter_title", "") or row.get("chapter", "") or "Unknown")
        chunk = {
            "text": str(row.get("text", "")),
            "chunk_id": str(row.get("chunk_id", "") or row.get("id", "")),
            "chunk_index": int(row.get("chunk_index", 0) or 0),
            "book_title": book,
            "chapter_title": chapter,
            "era": str(row.get("era", era)),
            "source": str(row.get("source", "")),
            "doc_type": str(row.get("doc_type", "")),
            "section_kind": str(row.get("section_kind", "")),
            "characters_json": str(row.get("characters_json", "[]")),
        }
        result[book][chapter].append(chunk)

    # Sort chunks within each chapter by chunk_index
    for book_chapters in result.values():
        for chapter_key in book_chapters:
            book_chapters[chapter_key].sort(key=lambda c: c["chunk_index"])

    total_chunks = sum(
        len(chunks)
        for chapters in result.values()
        for chunks in chapters.values()
    )
    logger.info(
        "Loaded %d parent chunks across %d books for era=%s",
        total_chunks, len(result), era,
    )
    return dict(result)


def estimate_extraction_calls(
    chunks_by_book: dict[str, dict[str, list[dict]]],
    chunks_per_call: int = 3,
) -> dict:
    """Estimate total LLM calls needed for extraction.

    Returns:
        {total_chunks, total_chapters, total_books, estimated_calls, estimated_minutes_at_50s}
    """
    total_chunks = 0
    total_chapters = 0
    total_books = len(chunks_by_book)
    for book, chapters in chunks_by_book.items():
        total_chapters += len(chapters)
        for chapter, chunks in chapters.items():
            total_chunks += len(chunks)

    # Each call processes chunks_per_call parent chunks
    import math
    estimated_calls = sum(
        math.ceil(len(chunks) / chunks_per_call)
        for chapters in chunks_by_book.values()
        for chunks in chapters.values()
    )
    # Plus book-level summary calls
    estimated_calls += total_books

    return {
        "total_chunks": total_chunks,
        "total_chapters": total_chapters,
        "total_books": total_books,
        "estimated_calls": estimated_calls,
        "estimated_minutes_at_50s": round(estimated_calls * 50 / 60, 1),
    }
