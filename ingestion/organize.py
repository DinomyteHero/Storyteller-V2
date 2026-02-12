"""Organize messy source folders into ingestion-ready layout.

This module is intentionally lightweight and deterministic-first. It reuses
`classify_document()` which is heuristic-first and may invoke LLM fallback
when confidence is low and providers are configured.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from ingestion.classify_document import classify_document

SUPPORTED_EXTS = {".txt", ".epub", ".pdf", ".md"}


@dataclass
class OrganizedFile:
    source: Path
    destination: Path
    era: str
    doc_type: str
    confidence: float
    used_llm_fallback: bool


def _safe_slug(text: str) -> str:
    out = "".join(ch.lower() if ch.isalnum() else "_" for ch in (text or "unknown"))
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_") or "unknown"


def _read_sample(path: Path, max_chars: int = 2500) -> str | None:
    if path.suffix.lower() not in {".txt", ".md"}:
        return None
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    except OSError:
        return None


def discover_documents(input_dir: Path) -> list[Path]:
    return sorted(
        p for p in input_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    )


def organize_documents(
    *,
    input_dir: Path,
    output_dir: Path,
    default_era: str | None = None,
    copy_mode: bool = True,
    dry_run: bool = False,
) -> list[OrganizedFile]:
    """Classify and place docs into <output>/<era>/<doc_type>/... layout."""
    files = discover_documents(input_dir)
    results: list[OrganizedFile] = []

    for src in files:
        sample = _read_sample(src)
        meta = classify_document(src, sample, default_era)
        era = str(meta.get("era") or "unknown")
        doc_type = str(meta.get("doc_type") or "unknown")

        rel_name = src.name
        dest = output_dir / _safe_slug(era) / _safe_slug(doc_type) / rel_name
        used_llm = "llm_fallback" in (meta.get("signals_used") or [])
        results.append(
            OrganizedFile(
                source=src,
                destination=dest,
                era=era,
                doc_type=doc_type,
                confidence=float(meta.get("confidence", 0.0) or 0.0),
                used_llm_fallback=used_llm,
            )
        )

        if dry_run:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        if copy_mode:
            shutil.copy2(src, dest)
        else:
            shutil.move(src, dest)

    return results


def write_manifest(results: list[OrganizedFile], path: Path) -> None:
    payload = [
        {
            "source": str(r.source),
            "destination": str(r.destination),
            "era": r.era,
            "doc_type": r.doc_type,
            "confidence": r.confidence,
            "used_llm_fallback": r.used_llm_fallback,
        }
        for r in results
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
