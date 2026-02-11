"""``storyteller query`` — search the vector store from the command line."""
from __future__ import annotations

import sys
from pathlib import Path


def register(subparsers) -> None:
    p = subparsers.add_parser("query", help="Search the vector store")
    p.add_argument("text", nargs="?", help="Search query text")
    p.add_argument("--query", type=str, help="Search query (alternative to positional)")
    p.add_argument("--k", type=int, default=5, help="Number of results (default: 5)")
    p.add_argument("--era", type=str, help="Filter by era (e.g. LOTF)")
    p.add_argument("--source-type", type=str, help="Filter by source type")
    p.add_argument("--db", type=str, default="./data/lancedb", help="LanceDB path")
    p.set_defaults(func=run)


def run(args) -> int:
    query_text = args.text or args.query
    if not query_text:
        print("  ERROR: No query text provided")
        print("  Usage: storyteller query \"your search text\"")
        print("     or: storyteller query --query \"your search text\"")
        return 1

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"  ERROR: LanceDB not found at {db_path}")
        print(f"         Run ingestion first: storyteller ingest --input ./data/lore")
        return 1

    # Dispatch to existing query module
    old_argv = sys.argv
    sys.argv = [
        "query",
        "--query", query_text,
        "--k", str(args.k),
        "--db", str(args.db),
    ]
    if args.era:
        sys.argv.extend(["--era", args.era])
    if args.source_type:
        sys.argv.extend(["--source_type", args.source_type])

    try:
        from ingestion.query import main as query_main
        return query_main()
    finally:
        sys.argv = old_argv
