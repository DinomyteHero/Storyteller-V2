"""Write per-run ingest manifests for tooling."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


def _resolve_manifests_dir(root: Path | None = None) -> Path:
    if root is None:
        root = Path(__file__).resolve().parents[1]
    env = os.environ.get("MANIFESTS_DIR", "").strip()
    if env:
        p = Path(env)
        if not p.is_absolute():
            p = root / p
        return p
    try:
        from shared.config import MANIFESTS_DIR
        p = Path(MANIFESTS_DIR)
        if not p.is_absolute():
            p = root / p
        return p
    except Exception as e:
        logger.debug("Failed to resolve MANIFESTS_DIR from shared config: %s", e)
        return root / "data" / "manifests"


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def input_file_hashes(paths: list[Path]) -> tuple[list[dict[str, str]], int]:
    out: list[dict[str, str]] = []
    failed = 0
    for p in paths:
        try:
            digest = _hash_file(p)
            out.append({"path": str(p), "sha256": digest})
        except Exception as e:
            logger.debug("Failed to hash input file %s: %s", p, e)
            failed += 1
            out.append({"path": str(p), "sha256": ""})
    return out, failed


def write_run_manifest(
    *,
    run_type: str,
    input_files: list[dict[str, str]],
    chunking: dict[str, Any],
    embedding_model: str,
    embedding_dim: int,
    tagger_enabled: bool,
    tagger_model: str,
    output_table: str,
    vectordb_path: str,
    counts: dict[str, int],
    chunk_id_scheme: str = "",
    root: Path | None = None,
    run_id: str | None = None,
) -> Path:
    if root is None:
        root = Path(__file__).resolve().parents[1]
    manifests_dir = _resolve_manifests_dir(root)
    manifests_dir.mkdir(parents=True, exist_ok=True)
    rid = run_id or str(uuid4())
    out_path = manifests_dir / f"{rid}.manifest.json"
    payload: dict[str, Any] = {
        "run_id": rid,
        "run_type": run_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input_files": input_files,
        "chunking": chunking,
        "embedding": {"model": embedding_model, "dimension": embedding_dim},
        "tagger": {"enabled": bool(tagger_enabled), "model": tagger_model or ""},
        "output": {"table_name": output_table, "vectordb_path": vectordb_path},
        "counts": counts,
        "chunk_id_scheme": chunk_id_scheme,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_last_ingest(
        db_path=vectordb_path,
        manifest_path=out_path,
        tagger_enabled=tagger_enabled,
        tagger_model=tagger_model,
        root=root,
    )
    return out_path


def check_chunk_id_scheme(current_scheme: str, root: Path | None = None) -> str | None:
    """Return a warning message if the last manifest used a different chunk_id_scheme.

    Returns None when there is no mismatch (or no previous manifest).
    """
    if root is None:
        root = Path(__file__).resolve().parents[1]
    last_path = root / "data" / "last_ingest.json"
    if not last_path.exists():
        return None
    try:
        meta = json.loads(last_path.read_text(encoding="utf-8"))
        manifest_path = meta.get("manifest_path", "")
        if not manifest_path or not Path(manifest_path).exists():
            return None
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        prev_scheme = manifest.get("chunk_id_scheme", "")
        if not prev_scheme:
            # Pre-hardening manifest (v1 era) — always warn
            prev_scheme = "v1"
        if prev_scheme != current_scheme:
            return (
                f"chunk_id_scheme MISMATCH: table was built with '{prev_scheme}', "
                f"current code uses '{current_scheme}'.  IDs will differ and dedup "
                f"will not recognise old rows — you will get duplicates.  "
                f"Run with --rebuild to recreate the table cleanly."
            )
    except Exception as e:
        logger.debug("Failed to read last ingest manifest: %s", e)
    return None


def _write_last_ingest(
    *,
    db_path: str,
    manifest_path: Path,
    tagger_enabled: bool,
    tagger_model: str,
    root: Path | None = None,
) -> Path:
    if root is None:
        root = Path(__file__).resolve().parents[1]
    out_path = root / "data" / "last_ingest.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "vectordb_path": db_path,
        "manifest_path": str(manifest_path),
        "tagger_enabled": bool(tagger_enabled),
        "tagger_model": tagger_model or "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path
