#!/usr/bin/env python3
"""
Quick script to ingest style guides into LanceDB.

Usage:
    python scripts/ingest_style.py
    python scripts/ingest_style.py --input ./data/style --db ./data/lancedb_4eras
"""
import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.app.rag.style_ingest import ingest_style_dir

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Ingest style guides into LanceDB")
    parser.add_argument(
        "--input",
        type=str,
        default="./data/style",
        help="Directory containing style .txt/.md files (default: ./data/style)"
    )
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="LanceDB path (default: from VECTORDB_PATH env or ./data/lancedb)"
    )
    parser.add_argument(
        "--table",
        type=str,
        default=None,
        help="Table name (default: from STYLE_TABLE_NAME env or style_chunks)"
    )
    args = parser.parse_args()

    input_dir = Path(args.input)
    if not input_dir.exists():
        logger.error(f"Input directory not found: {input_dir}")
        logger.error(f"Create it and add style guides, or specify --input <path>")
        return 1

    logger.info("=" * 60)
    logger.info("Style Ingestion")
    logger.info("=" * 60)
    logger.info(f"Input directory: {input_dir}")
    logger.info(f"LanceDB path: {args.db or 'from config (VECTORDB_PATH)'}")
    logger.info(f"Table name: {args.table or 'from config (STYLE_TABLE_NAME)'}")
    logger.info("")

    try:
        num_chunks = ingest_style_dir(
            data_dir=input_dir,
            db_path=args.db,
            table_name=args.table
        )
        
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"✅ Style ingestion complete!")
        logger.info(f"   Total chunks: {num_chunks}")
        logger.info("=" * 60)
        return 0
        
    except Exception as e:
        logger.exception(f"Style ingestion failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
