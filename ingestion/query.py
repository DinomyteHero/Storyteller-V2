"""CLI for querying the ingestion vector store.

Usage:
  python -m ingestion.query --query "..." --k 5 --era LOTF --source_type novel --db ./data/lancedb
"""
import argparse
import logging
import sys
from pathlib import Path

from ingestion.store import LanceStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> int:
    ap = argparse.ArgumentParser(description="Query LanceDB (ingestion store).")
    ap.add_argument("--query", type=str, required=True, help="Search query")
    ap.add_argument("--k", type=int, default=5, help="Number of results")
    ap.add_argument("--era", type=str, help="Filter by era (e.g. LOTF)")
    ap.add_argument("--source_type", type=str, help="Filter by source type")
    ap.add_argument("--db", type=str, default="./data/lancedb", help="LanceDB path")
    args = ap.parse_args()

    store = LanceStore(args.db)
    results = store.search(
        query=args.query,
        k=args.k,
        era=args.era,
        source_type=args.source_type,
    )

    if not results:
        logger.warning("No results")
        return 1

    print("\nFound %d result(s):\n" % len(results))
    print("=" * 80)
    for i, r in enumerate(results, 1):
        m = r.get("metadata") or {}
        score = r.get("score", 0.0)
        text = (r.get("text") or "")[:500]
        print("\nResult %d (score: %.4f)" % (i, score))
        print("Book: %s" % m.get("book_title", ""))
        ct = m.get("chapter_title")
        ci = m.get("chapter_index")
        if ct is not None:
            print("Chapter: %s (index: %s)" % (ct, ci))
        print("Chunk: %s (ID: %s...)" % (m.get("chunk_index", ""), (m.get("chunk_id") or "")[:8]))
        print("\nText:\n%s..." % text)
        print("-" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())
