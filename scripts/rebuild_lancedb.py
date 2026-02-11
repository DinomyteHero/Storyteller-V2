#!/usr/bin/env python3
"""Rebuild LanceDB from source docs using existing ingestion patterns.

Reads lore dir (PDF/EPUB/TXT), style dir (.txt/.md), generates embeddings via config
(EMBEDDING_MODEL, EMBEDDING_DIMENSION), and writes fresh tables. Use after changing
embedding model (e.g. bge-m3 or nomic-embed-text:v1.5).

Usage:
  python scripts/rebuild_lancedb.py [--lore-dir ./data/lore] [--style-dir ./data/style] [--db ./data/lancedb]
  EMBEDDING_MODEL=BAAI/bge-m3 EMBEDDING_DIMENSION=1024 python scripts/rebuild_lancedb.py --db ./data/lancedb

Requires: EMBEDDING_MODEL and EMBEDDING_DIMENSION env vars to match your chosen model.
See docs/05_rag_and_ingestion.md for bge-m3 and nomic-embed-text switching instructions.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Project root on path
_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _drop_table_if_exists(db, table_name: str) -> None:
    """Drop table if it exists. Silently no-op if not."""
    try:
        db.drop_table(table_name)
        logger.info("Dropped existing table %s", table_name)
    except Exception:
        pass


def rebuild_lore(
    lore_dir: Path,
    db_path: Path,
    table_name: str | None,
    time_period: str = "default",
    planet: str = "",
    faction: str = "",
) -> int:
    """Rebuild lore_chunks from PDF/EPUB/TXT files using LanceStore."""
    import lancedb
    from backend.app.config import LORE_TABLE_NAME
    from ingestion.ingest_lore import ingest_file, _to_canonical_chunks
    from ingestion.tagger import apply_tagger_to_chunks
    from ingestion.store import LanceStore

    paths = list(lore_dir.glob("*.txt")) + list(lore_dir.glob("*.epub")) + list(lore_dir.glob("*.pdf"))
    if not paths:
        logger.warning("No .txt/.epub/.pdf in %s", lore_dir)
        return 0

    meta = {
        "time_period": time_period.strip() or "default",
        "planet": planet.strip(),
        "faction": faction.strip(),
    }
    all_chunks: list = []
    for p in paths:
        try:
            chunks = ingest_file(p, meta=meta, source_type="reference", collection="lore")
            all_chunks.extend(chunks)
        except Exception as e:
            logger.warning("Skip %s: %s", p, e)
    if not all_chunks:
        logger.warning("No lore chunks produced")
        return 0

    canonical = _to_canonical_chunks(all_chunks)
    canonical, _tagger_stats = apply_tagger_to_chunks(canonical)
    tbl = table_name or LORE_TABLE_NAME
    db_path.mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(str(db_path))
    _drop_table_if_exists(db, tbl)
    store = LanceStore(str(db_path), allow_overwrite=False)
    store.add_chunks(canonical)
    logger.info("Rebuilt lore: %d chunks", len(canonical))
    return len(canonical)


def rebuild_style(style_dir: Path, db_path: Path, table_name: str | None) -> int:
    """Rebuild style_chunks from .txt/.md files."""
    import lancedb
    from backend.app.config import STYLE_TABLE_NAME
    from backend.app.rag.style_ingest import ingest_style_dir

    db = lancedb.connect(str(db_path))
    _drop_table_if_exists(db, table_name or STYLE_TABLE_NAME)
    n = ingest_style_dir(style_dir, db_path=db_path, table_name=table_name or STYLE_TABLE_NAME)
    logger.info("Rebuilt style: %d chunks", n)
    return n


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Rebuild LanceDB from source docs. Uses EMBEDDING_MODEL and EMBEDDING_DIMENSION from config/env."
    )
    ap.add_argument("--lore-dir", type=str, default=None, help="Lore input dir (PDF/EPUB/TXT). Default: LORE_DATA_DIR or ./data/lore")
    ap.add_argument("--style-dir", type=str, default=None, help="Style input dir (.txt/.md). Default: STYLE_DATA_DIR or ./data/style")
    ap.add_argument("--db", type=str, default=None, help="LanceDB path. Default: VECTORDB_PATH or ./data/lancedb")
    ap.add_argument("--time-period", type=str, default="default", help="Lore time_period meta (e.g. LOTF)")
    ap.add_argument("--planet", type=str, default="", help="Lore planet meta")
    ap.add_argument("--faction", type=str, default="", help="Lore faction meta")
    ap.add_argument("--skip-lore", action="store_true", help="Skip lore rebuild")
    ap.add_argument("--skip-style", action="store_true", help="Skip style rebuild")
    args = ap.parse_args()

    db_path = Path(args.db or os.environ.get("VECTORDB_PATH", "./data/lancedb"))
    lore_dir = Path(args.lore_dir or os.environ.get("LORE_DATA_DIR", "./data/lore"))
    style_dir = Path(args.style_dir or os.environ.get("STYLE_DATA_DIR", "./data/style"))

    from backend.app.config import EMBEDDING_MODEL, EMBEDDING_DIMENSION
    logger.info("Using EMBEDDING_MODEL=%s EMBEDDING_DIMENSION=%s", EMBEDDING_MODEL, EMBEDDING_DIMENSION)

    total = 0
    if not args.skip_lore and lore_dir.exists():
        total += rebuild_lore(
            lore_dir, db_path,
            table_name=None,
            time_period=args.time_period,
            planet=args.planet,
            faction=args.faction,
        )
    elif not args.skip_lore:
        logger.warning("Lore dir %s does not exist; skipping", lore_dir)

    if not args.skip_style and style_dir.exists():
        total += rebuild_style(style_dir, db_path, table_name=None)
    elif not args.skip_style:
        logger.warning("Style dir %s does not exist; skipping", style_dir)

    logger.info("Rebuild complete. Total chunks: %d", total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
