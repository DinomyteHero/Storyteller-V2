"""CLI to ingest style documents into the style LanceDB table."""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Ensure project root is on path when run as __main__
if __name__ == "__main__":
    _root = Path(__file__).resolve().parents[3]
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

from backend.app.config import STYLE_DATA_DIR
from backend.app.rag.style_ingest import ingest_style_dir

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest .txt and .md style documents into LanceDB style table."
    )
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        default=None,
        help="Directory containing .txt and .md files (alias for --dir)",
    )
    parser.add_argument(
        "--dir",
        "-d",
        type=str,
        default=os.environ.get("STYLE_DATA_DIR", STYLE_DATA_DIR),
        help="Directory containing .txt and .md files (default: ./data/style)",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="LanceDB path (default: VECTORDB_PATH, else ./data/lancedb)",
    )
    args = parser.parse_args()
    data_dir = Path(args.input or args.dir)
    if not data_dir.exists():
        logger.error("Directory does not exist: %s", data_dir)
        return 1
    n = ingest_style_dir(data_dir, db_path=args.db)
    logger.info("Ingested %d style chunks.", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
