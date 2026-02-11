#!/usr/bin/env python3
"""Verify the unified LanceDB lore_chunks table after ingestion.

Prints row counts grouped by collection, source_type, and level,
then runs sample searches to sanity-check that both novels and
essential reference ingested correctly.

Usage:
  python scripts/verify_lore_store.py [--db ./data/lancedb] [--query "Tatooine"]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Verify unified lore_chunks table: counts and sample search."
    )
    ap.add_argument("--db", type=str, default=None, help="LanceDB path (default: VECTORDB_PATH or ./data/lancedb)")
    ap.add_argument("--query", type=str, default="Tatooine", help="Sample search query string")
    args = ap.parse_args()

    db_path = Path(args.db or os.environ.get("VECTORDB_PATH", "./data/lancedb"))
    table_name = "lore_chunks"

    if not db_path.exists():
        print(f"ERROR: DB path does not exist: {db_path}")
        return 1

    import lancedb
    db = lancedb.connect(str(db_path))
    try:
        table = db.open_table(table_name)
    except Exception as e:
        print(f"ERROR: Could not open table {table_name}: {e}")
        return 1

    # Row counts grouped by collection, source_type, level (no pandas required)
    tbl = table.to_arrow()
    total = tbl.num_rows
    print(f"\n=== lore_chunks: {total} total rows ===\n")

    schema_cols = {f.name for f in table.schema}
    d = tbl.to_pydict()

    def _counts(col: str) -> dict:
        if col not in schema_cols or col not in d:
            return {}
        arr = d[col]
        counts: dict[str, int] = {}
        for v in arr:
            label = v if (v is not None and str(v).strip()) else "(empty)"
            counts[label] = counts.get(label, 0) + 1
        return counts

    if "collection" in schema_cols:
        print("By collection:")
        for val, cnt in sorted(_counts("collection").items(), key=lambda x: -x[1]):
            print(f"  {val}: {cnt}")
        print()
    else:
        print("(collection column not present)\n")

    if "source_type" in schema_cols:
        print("By source_type:")
        for val, cnt in sorted(_counts("source_type").items(), key=lambda x: -x[1]):
            print(f"  {val}: {cnt}")
        print()
    else:
        print("(source_type column not present)\n")

    if "level" in schema_cols:
        print("By level (parent/child/empty):")
        for val, cnt in sorted(_counts("level").items(), key=lambda x: -x[1]):
            print(f"  {val}: {cnt}")
        print()
    else:
        print("(level column not present)\n")

    # Sample search
    from ingestion.embedding import encode as embed_texts
    query_vec = embed_texts([args.query])[0]
    try:
        results = table.search(query_vec).limit(3).to_arrow()
    except Exception as e:
        print(f"Search failed: {e}")
        return 1

    print(f"=== Sample search: \"{args.query}\" (top 3) ===\n")
    rd = results.to_pydict()
    for i in range(min(3, results.num_rows)):
        def _v(col: str) -> str:
            arr = rd.get(col)
            if arr is None or i >= len(arr):
                return ""
            v = arr[i]
            return str(v).strip() if v is not None and str(v) != "nan" else ""

        book = _v("book_title") or _v("source")
        coll = _v("collection")
        ch = _v("chapter_title") or _v("chapter")
        sec = _v("section_kind")
        text_preview = (_v("text"))[:120]
        if len(text_preview) >= 120:
            text_preview += "..."
        print(f"  [{i+1}] book_title: {book} | collection: {coll}")
        print(f"      chapter: {ch} | section_kind: {sec}")
        print(f"      text: {text_preview}")
        print()

    print("Verification complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
