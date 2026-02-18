"""Ingest a rule system .md document into LanceDB as section_kind=rules chunks.

Each top-level '## SECTION' header in the rule system document becomes a parent chunk.
Long sections are further sub-chunked into children (~256 tokens) for precise RAG retrieval.

This enables the ResolutionAgent (and other agents) to do targeted RAG queries like:
    retrieve_lore(
        query="how to resolve ATTACK actions",
        section_kind="rules",
        rule_system_id="storyteller_core",
        top_k=3,
    )
instead of loading the entire rule system document into the system prompt — which is
essential for long rule systems (full FFG rulebook, D&D 5e SRD, etc.).

Usage:
  python -m ingestion.ingest_rules \\
    --input data/static/rule_systems/storyteller_core.md \\
    --rule-system storyteller_core \\
    --setting-id star_wars \\
    --db ./data/lancedb

  python -m ingestion.ingest_rules \\
    --input data/static/rule_systems/lotr_core.md \\
    --rule-system lotr_core \\
    --setting-id lotr \\
    --db ./data/lancedb

  # Ingest all rule systems listed in catalog.yaml:
  python -m ingestion.ingest_rules --from-catalog --db ./data/lancedb
"""
from __future__ import annotations

import argparse
import hashlib
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

from ingestion.chunking import chunk_text_by_tokens  # noqa: E402
from ingestion.manifest import write_run_manifest  # noqa: E402
from ingestion.store import LanceStore, CHUNK_ID_SCHEME  # noqa: E402
from shared.config import EMBEDDING_DIMENSION, EMBEDDING_MODEL  # noqa: E402
from shared.lore_metadata import RULE_SYSTEM_ID_DEFAULT  # noqa: E402

CHILD_TOKENS = 256
CHILD_OVERLAP = 0.1
# Rule system sections smaller than this token count are kept as a single parent chunk
# without being further sub-chunked (avoids over-fragmentation of short sections).
MIN_SECTION_TOKENS_FOR_CHILDREN = 64


def _section_chunk_id(rule_system_id: str, section_title: str, index: int, text: str) -> str:
    """Stable, portable chunk ID for a rule section."""
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    payload = f"rules|{rule_system_id}|{section_title}|{index}|{content_hash}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _split_by_headers(md_text: str) -> list[tuple[str, str]]:
    """Split markdown into (section_title, section_body) pairs at '## ' boundaries.

    Returns one tuple per top-level (##) section. Text before the first ## header
    is collected under the title '_preamble'. Section title is the header text
    (without the ## prefix).
    """
    sections: list[tuple[str, str]] = []
    current_title = "_preamble"
    current_lines: list[str] = []

    for line in md_text.splitlines():
        # Match ## level-2 headers only (not # or ###)
        m = re.match(r"^## (.+)$", line)
        if m:
            # Save the previous section
            body = "\n".join(current_lines).strip()
            if body:
                sections.append((current_title, body))
            current_title = m.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)

    # Tail section
    body = "\n".join(current_lines).strip()
    if body:
        sections.append((current_title, body))

    return sections


def _build_chunks(
    md_text: str,
    rule_system_id: str,
    setting_id: str,
    source_filename: str,
) -> list[dict[str, Any]]:
    """Parse a rule system .md document into parent + child chunks.

    Each '## SECTION' becomes a parent. Long parent sections are sub-chunked
    into children (256 tokens). Each chunk includes metadata for LanceDB storage.
    """
    sections = _split_by_headers(md_text)
    if not sections:
        logger.warning("No sections found in rule document — is it missing '## ' headers?")
        return []

    chunks: list[dict[str, Any]] = []
    parent_index = 0

    for section_title, section_body in sections:
        # Skip empty / comment-only sections (e.g. the author instructions preamble)
        stripped = section_body.strip()
        if not stripped or stripped.startswith("#"):
            continue

        pid = _section_chunk_id(rule_system_id, section_title, parent_index, section_body)
        base_meta = {
            "rule_system_id": rule_system_id,
            "setting_id": setting_id,
            "section_kind": "rules",
            "doc_type": "reference",
            "collection": "rules",
            "source_type": "reference",
            "source": source_filename,
            "book_title": rule_system_id,
            "chapter": section_title,
            "era": "",
            "time_period": "",
            "period_id": "",
            "planet": "",
            "faction": "",
            "characters": [],
            "related_npcs": [],
            "universe": "",
        }

        # Store parent with its section header prepended for full context
        parent_text = f"## {section_title}\n\n{section_body}"
        chunks.append({
            "text": parent_text,
            "metadata": {
                **base_meta,
                "chunk_id": pid,
                "level": "parent",
                "parent_id": "",
                "chunk_index": parent_index,
            },
        })

        # Sub-chunk long sections into children
        child_texts = chunk_text_by_tokens(
            section_body,
            target_tokens=CHILD_TOKENS,
            overlap_percent=CHILD_OVERLAP,
        )
        if len(child_texts) > 1:
            for c_idx, child_text in enumerate(child_texts):
                child_stored = f"[Rule System: {rule_system_id}, Section: {section_title}] {child_text}"
                cid = _section_chunk_id(rule_system_id, section_title, parent_index * 1000 + c_idx, child_text)
                chunks.append({
                    "text": child_stored,
                    "metadata": {
                        **base_meta,
                        "chunk_id": cid,
                        "level": "child",
                        "parent_id": pid,
                        "chunk_index": c_idx,
                    },
                })

        parent_index += 1

    return chunks


def ingest_rule_doc(
    input_path: Path,
    rule_system_id: str,
    setting_id: str,
    db_path: str,
    allow_overwrite: bool = False,
) -> dict[str, Any]:
    """Ingest a single rule system .md file into LanceDB.

    Returns a stats dict: {chunks, added, skipped, sections}.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Rule system document not found: {input_path}")

    md_text = input_path.read_text(encoding="utf-8", errors="replace")
    if not md_text.strip():
        raise ValueError(f"Rule system document is empty: {input_path}")

    chunks = _build_chunks(
        md_text,
        rule_system_id=rule_system_id,
        setting_id=setting_id,
        source_filename=input_path.name,
    )
    if not chunks:
        logger.warning("No chunks produced from %s — check ## header formatting.", input_path)
        return {"chunks": 0, "added": 0, "skipped": 0, "sections": 0}

    parent_count = sum(1 for c in chunks if c["metadata"].get("level") == "parent")
    logger.info(
        "Parsed %d sections → %d chunks (parents=%d, children=%d) from %s",
        parent_count, len(chunks), parent_count, len(chunks) - parent_count, input_path.name,
    )

    store = LanceStore(db_path, allow_overwrite=allow_overwrite)
    result = store.add_chunks(chunks)
    added = result.get("added", 0)
    skipped = result.get("skipped", 0)
    logger.info(
        "Rule ingestion complete: %d added, %d skipped (dedup) for rule_system_id='%s'",
        added, skipped, rule_system_id,
    )
    return {"chunks": len(chunks), "added": added, "skipped": skipped, "sections": parent_count}


def _load_catalog(catalog_path: Path) -> list[dict[str, Any]]:
    """Load rule_systems catalog.yaml. Returns list of rule system dicts."""
    try:
        import yaml
        data = yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}
        return data.get("rule_systems", [])
    except Exception as e:
        logger.error("Failed to load catalog %s: %s", catalog_path, e)
        return []


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Ingest a rule system .md document into LanceDB as section_kind=rules chunks. "
            "Enables RAG retrieval of specific rule sections by the ResolutionAgent."
        )
    )
    ap.add_argument(
        "--input", "-i",
        type=str,
        default="",
        help="Path to the rule system .md file (e.g. data/static/rule_systems/storyteller_core.md)",
    )
    ap.add_argument(
        "--rule-system",
        type=str,
        default="",
        help=(
            "Rule system ID (e.g. 'storyteller_core', 'lotr_core'). "
            "Defaults to the stem of the --input filename."
        ),
    )
    ap.add_argument(
        "--setting-id",
        type=str,
        default="",
        help="Setting ID to tag these rule chunks (e.g. 'star_wars', 'lotr'). Optional.",
    )
    ap.add_argument(
        "--db",
        type=str,
        default="./data/lancedb",
        help="LanceDB path (default: ./data/lancedb)",
    )
    ap.add_argument(
        "--rebuild",
        action="store_true",
        help="Drop and recreate the LanceDB table before ingesting.",
    )
    ap.add_argument(
        "--from-catalog",
        action="store_true",
        help=(
            "Ingest all rule systems listed in data/static/rule_systems/catalog.yaml. "
            "Ignores --input, --rule-system, and --setting-id."
        ),
    )
    ap.add_argument(
        "--catalog",
        type=str,
        default="",
        help="Path to catalog.yaml (default: data/static/rule_systems/catalog.yaml)",
    )
    args = ap.parse_args()

    if args.from_catalog:
        catalog_path = Path(args.catalog) if args.catalog else (
            _root / "data" / "static" / "rule_systems" / "catalog.yaml"
        )
        entries = _load_catalog(catalog_path)
        if not entries:
            logger.error("No rule systems found in catalog: %s", catalog_path)
            return 1
        total_added = 0
        total_skipped = 0
        for entry in entries:
            rs_id = entry.get("id", "")
            doc_file = entry.get("doc_file", f"{rs_id}.md")
            doc_path = catalog_path.parent / doc_file
            settings = entry.get("settings_using") or [""]
            setting_id = settings[0] if settings else ""
            if not rs_id:
                logger.warning("Skipping catalog entry with no id: %s", entry)
                continue
            if not doc_path.exists():
                logger.warning("Rule doc not found for '%s': %s", rs_id, doc_path)
                continue
            logger.info("Ingesting rule system: %s (%s)", rs_id, doc_path)
            try:
                stats = ingest_rule_doc(doc_path, rs_id, setting_id, args.db, args.rebuild)
                total_added += stats.get("added", 0)
                total_skipped += stats.get("skipped", 0)
            except Exception as e:
                logger.error("Failed to ingest '%s': %s", rs_id, e)
        logger.info("Catalog ingestion complete: %d added, %d skipped", total_added, total_skipped)
        return 0

    # Single-file mode
    if not args.input:
        ap.error("--input is required (or use --from-catalog)")
    input_path = Path(args.input)
    rule_system_id = (args.rule_system or input_path.stem).strip()
    setting_id = (args.setting_id or "").strip()

    if not rule_system_id:
        ap.error("--rule-system is required (or provide --input with a descriptive filename)")

    try:
        stats = ingest_rule_doc(
            input_path=input_path,
            rule_system_id=rule_system_id,
            setting_id=setting_id,
            db_path=args.db,
            allow_overwrite=args.rebuild,
        )
    except (FileNotFoundError, ValueError) as e:
        logger.error("%s", e)
        return 1

    write_run_manifest(
        run_type="rules",
        input_files={str(input_path): ""},
        chunking={
            "child_tokens": CHILD_TOKENS,
            "child_overlap": CHILD_OVERLAP,
            "strategy": "markdown_h2_sections",
        },
        embedding_model=EMBEDDING_MODEL,
        embedding_dim=EMBEDDING_DIMENSION,
        tagger_enabled=False,
        tagger_model="",
        output_table="lore_chunks",
        vectordb_path=args.db,
        chunk_id_scheme=CHUNK_ID_SCHEME,
        counts={
            "chunks": stats["chunks"],
            "added": stats["added"],
            "skipped_dedup": stats["skipped"],
            "failed": 0,
        },
        context={
            "rule_system_id": rule_system_id,
            "setting_id": setting_id,
            "sections": stats["sections"],
            "collection": "rules",
            "section_kind": "rules",
        },
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
