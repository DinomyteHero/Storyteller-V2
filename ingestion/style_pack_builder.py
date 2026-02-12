"""Build style pack documents from raw/organized lore corpora.

Hybrid pipeline (Option A): deterministic extraction + optional LLM polishing.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ingestion.classify_document import _era_from_path

SUPPORTED_EXTS = {".txt", ".md", ".epub", ".pdf"}
GENRES = {
    "political_thriller": {"senate", "politics", "diplomat", "council", "chancellor"},
    "military_tactical": {"fleet", "squad", "battle", "strategy", "command"},
    "noir_detective": {"investigate", "clue", "informant", "shadow", "alley"},
    "space_western": {"outpost", "frontier", "cantina", "bounty", "dust"},
    "mythic_quest": {"prophecy", "destiny", "artifact", "pilgrimage", "trial"},
}


@dataclass
class StyleDoc:
    category: str
    stem: str
    path: Path
    generated_with_llm: bool


def _read_sample(path: Path, max_chars: int = 3000) -> str:
    if path.suffix.lower() not in {".txt", ".md"}:
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    except OSError:
        return ""


def discover_documents(input_dir: Path) -> list[Path]:
    return sorted(p for p in input_dir.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS)


def _slug(text: str) -> str:
    v = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return v or "unknown"


def _genre_scores(samples: Iterable[str]) -> dict[str, int]:
    scores = {g: 0 for g in GENRES}
    for s in samples:
        words = set(re.findall(r"[a-z]+", s.lower()))
        for g, keys in GENRES.items():
            scores[g] += len(words & keys)
    return scores


def _deterministic_style_doc(title: str, samples: list[str], notes: list[str]) -> str:
    joined = "\n\n".join(s for s in samples if s)[:5000]
    return (
        f"# {title}\n\n"
        "## Voice and Tone\n"
        "- Keep prose cinematic and concrete.\n"
        "- Prioritize clear scene geography and emotional intent.\n\n"
        "## Pacing\n"
        "- Alternate tension and release every 2-3 beats.\n"
        "- End scenes on an actionable dramatic hook.\n\n"
        "## Grounding Signals\n"
        + "\n".join(f"- {n}" for n in notes[:8])
        + "\n\n## Corpus Excerpts (for alignment)\n"
        + (joined[:2500] if joined else "- (no excerpts available)")
    )


def _llm_polish(draft: str, *, role: str = "ingestion_tagger") -> tuple[str, bool]:
    try:
        from backend.app.core.agents.base import AgentLLM
        llm = AgentLLM(role)
        sys_prompt = (
            "You are an expert RPG style-guide editor. Rewrite into a concise production style guide. "
            "Keep markdown headings. Keep constraints actionable. Do not add fictional facts beyond source hints."
        )
        out = llm.complete(sys_prompt, draft, json_mode=False)
        text = str(out or "").strip()
        if text:
            return text, True
    except Exception:
        pass
    return draft, False


def build_style_pack(
    *,
    input_dir: Path,
    output_dir: Path,
    default_era: str | None = None,
    use_llm: bool = False,
    llm_role: str = "ingestion_tagger",
    dry_run: bool = False,
) -> list[StyleDoc]:
    files = discover_documents(input_dir)
    if not files:
        return []

    era_samples: dict[str, list[str]] = {}
    all_samples: list[str] = []

    for p in files:
        sample = _read_sample(p)
        all_samples.append(sample)
        era = str(_era_from_path(p) or default_era or "unknown")
        era_samples.setdefault(era, []).append(sample)

    genre_scores = _genre_scores(all_samples)
    top_genres = [g for g, score in sorted(genre_scores.items(), key=lambda x: -x[1]) if score > 0][:3]

    docs: list[StyleDoc] = []
    notes = [f"source documents: {len(files)}", f"detected eras: {', '.join(sorted(era_samples))}"]

    entries: list[tuple[str, str, list[str], list[str]]] = []
    entries.append(("base", "auto_base_style", all_samples, notes))
    for era, samples in sorted(era_samples.items()):
        entries.append(("era", f"{_slug(era)}_style", samples, [f"era: {era}", f"documents: {len(samples)}"]))
    for g in top_genres:
        entries.append(("genre", f"{g}_style", all_samples, [f"genre keyword score: {genre_scores[g]}"]))

    for category, stem, samples, local_notes in entries:
        rel = Path(category) / f"{stem}.md"
        out_path = output_dir / rel
        draft = _deterministic_style_doc(stem.replace("_", " ").title(), samples, local_notes)
        used_llm = False
        final = draft
        if use_llm:
            final, used_llm = _llm_polish(draft, role=llm_role)

        docs.append(StyleDoc(category=category, stem=stem, path=out_path, generated_with_llm=used_llm))
        if not dry_run:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(final, encoding="utf-8")

    if not dry_run:
        manifest = output_dir / "_style_pack_manifest.json"
        payload = [
            {
                "category": d.category,
                "stem": d.stem,
                "path": str(d.path),
                "generated_with_llm": d.generated_with_llm,
            }
            for d in docs
        ]
        manifest.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return docs
