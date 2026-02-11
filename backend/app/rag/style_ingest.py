"""Style ingestion: plaintext .txt/.md from a directory into LanceDB style table."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import List

import lancedb
import pyarrow as pa

from backend.app.config import EMBEDDING_DIMENSION, EMBEDDING_MODEL, STYLE_TABLE_NAME, resolve_vectordb_path
from ingestion.manifest import input_file_hashes, write_run_manifest

logger = logging.getLogger(__name__)

# ~512 tokens ≈ ~384 words (approx 1.3 words per token)
TARGET_WORDS_PER_CHUNK = 384


def _get_encoder():
    """Lazy-load embedding model from config."""
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(EMBEDDING_MODEL)
    except ImportError as e:
        raise RuntimeError(
            "sentence-transformers required for style ingestion. pip install sentence-transformers"
        ) from e


def _chunk_by_paragraphs(text: str, target_words: int = TARGET_WORDS_PER_CHUNK) -> List[str]:
    """Split text into paragraphs, then merge until ~target_words per chunk."""
    paragraphs = re.split(r"\n\s*\n", text.strip())
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    if not paragraphs:
        return [text] if text.strip() else []

    chunks: List[str] = []
    current: List[str] = []
    current_words = 0

    for para in paragraphs:
        word_count = len(para.split())
        if current_words + word_count > target_words and current:
            chunks.append("\n\n".join(current))
            current = []
            current_words = 0
        current.append(para)
        current_words += word_count

    if current:
        chunks.append("\n\n".join(current))
    return chunks


# Tone and pacing keyword lists for style tag extraction
_TONE_KEYWORDS = frozenset({
    "dark", "gritty", "cinematic", "literary", "pulpy", "epic", "intimate",
    "atmospheric", "tense", "reflective", "humorous", "somber", "mythic",
    "visceral", "lyrical",
})
_PACING_KEYWORDS = frozenset({
    "fast-paced", "slow-burn", "action-heavy", "dialogue-driven",
    "contemplative", "suspenseful",
})


def _extract_tags(text: str) -> list[str]:
    """Extract tone/pacing tags from text via keyword matching. Returns sorted deduped list."""
    if not text:
        return []
    lower = text.lower()
    tags: list[str] = []
    for kw in _TONE_KEYWORDS:
        if kw in lower:
            tags.append(kw)
    for kw in _PACING_KEYWORDS:
        if kw in lower:
            tags.append(kw)
    return sorted(set(tags))


def _infer_source_type(path: Path) -> str:
    """Return 'book'|'article'|'notes' from file path."""
    ext = path.suffix.lower()
    if ext == ".md":
        return "notes"
    if ext == ".txt":
        return "article"
    return "article"


_SKIP_STEMS = frozenset({"PROMPT_TEMPLATE", "README"})


def _collect_files(data_dir: Path) -> List[Path]:
    """Collect .txt and .md files under data_dir (recursive into subdirectories)."""
    out: List[Path] = []
    if not data_dir.exists():
        return out
    for p in data_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".txt", ".md") and p.stem not in _SKIP_STEMS:
            out.append(p)
    return sorted(out)


def _ensure_style_table(db: lancedb.DBConnection, table_name: str) -> None:
    """Create style table if it does not exist."""
    try:
        db.open_table(table_name)
        logger.info("Opened existing table %s", table_name)
    except Exception as e:
        logger.debug("Style table %s missing or unreadable, recreating: %s", table_name, e)
        schema = pa.schema([
            pa.field("id", pa.string()),
            pa.field("text", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), EMBEDDING_DIMENSION)),
            pa.field("source_title", pa.string()),
            pa.field("source_type", pa.string()),
            pa.field("tags_json", pa.string()),
            pa.field("chunk_index", pa.int32()),
        ])
        db.create_table(table_name, schema=schema, mode="overwrite")
        logger.info("Created table %s", table_name)


def ingest_style_dir(
    data_dir: str | Path,
    db_path: str | Path | None = None,
    table_name: str | None = None,
) -> int:
    """
    Ingest .txt and .md files from data_dir into LanceDB style table.

    Chunks by paragraphs, merging until ~512 tokens (approx by word count).
    Uses same embedding model as lore. Upserts by adding rows (ids are unique per run).

    Args:
        data_dir: Directory containing .txt and .md files.
        db_path: LanceDB path (default: VECTORDB_PATH env or 'lancedb').
        table_name: Style table name (default: STYLE_TABLE_NAME from config).

    Returns:
        Number of chunks written.
    """
    data_dir = Path(data_dir)
    db_path = resolve_vectordb_path(db_path)
    db_path.mkdir(parents=True, exist_ok=True)
    table_name = table_name or STYLE_TABLE_NAME

    files = _collect_files(data_dir)
    if not files:
        logger.warning("No .txt or .md files in %s", data_dir)
        return 0
    input_hashes, hash_failures = input_file_hashes(files)

    encoder = _get_encoder()
    db = lancedb.connect(str(db_path))
    _ensure_style_table(db, table_name)
    table = db.open_table(table_name)

    total_chunks = 0
    failed_files = 0
    for fp in files:
        try:
            raw = fp.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.warning("Skip %s: %s", fp, e)
            failed_files += 1
            continue

        source_title = fp.stem
        source_type = _infer_source_type(fp)
        chunks = _chunk_by_paragraphs(raw)
        if not chunks:
            continue

        texts = [c for c in chunks]
        embeddings = encoder.encode(texts, show_progress_bar=False).tolist()

        # Upsert: remove existing chunks for this source, then add
        safe_title = source_title.replace("'", "''")
        try:
            table.delete(f"source_title = '{safe_title}'")
        except Exception as e:
            logger.debug("Failed to delete existing style rows for %s: %s", safe_title, e)
        rows = []
        for i, (text, embedding) in enumerate(zip(texts, embeddings)):
            chunk_id = f"{source_title}_{i}"
            rows.append({
                "id": chunk_id,
                "text": text,
                "vector": embedding,
                "source_title": source_title,
                "source_type": source_type,
                "tags_json": json.dumps(_extract_tags(text)),
                "chunk_index": i,
            })
        table.add(rows)
        total_chunks += len(rows)
        logger.info("Ingested %s: %d chunks", fp.name, len(rows))

    logger.info("Style ingestion complete: %d total chunks", total_chunks)
    write_run_manifest(
        run_type="style",
        input_files=input_hashes,
        chunking={"strategy": "paragraph_merge", "target_words": TARGET_WORDS_PER_CHUNK},
        embedding_model=EMBEDDING_MODEL,
        embedding_dim=EMBEDDING_DIMENSION,
        tagger_enabled=False,
        tagger_model="",
        output_table=table_name,
        vectordb_path=str(db_path),
        counts={
            "chunks": total_chunks,
            "failed": int(hash_failures) + int(failed_files),
        },
    )
    return total_chunks
