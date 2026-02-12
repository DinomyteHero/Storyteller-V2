"""`storyteller build-style-pack` — auto-generate style docs from corpus."""
from __future__ import annotations

from pathlib import Path

from ingestion.style_pack_builder import build_style_pack
from shared.ingest_paths import ingest_root


def register(subparsers) -> None:
    p = subparsers.add_parser("build-style-pack", help="Generate style docs from lore corpus (deterministic + optional LLM polish)")
    p.add_argument("--input", type=str, required=True, help="Source corpus root (raw or organized)")
    p.add_argument("--output", type=str, default=None, help="Output style root (default: <ingest-root>/style/generated)")
    p.add_argument("--default-era", type=str, default=None, help="Fallback era when unknown")
    p.add_argument("--use-llm", action="store_true", help="Polish generated docs with configured LLM role")
    p.add_argument("--llm-role", type=str, default="ingestion_tagger", help="LLM role for polishing (default: ingestion_tagger)")
    p.add_argument("--dry-run", action="store_true", help="Preview generation without writing files")
    p.set_defaults(func=run)


def run(args) -> int:
    input_dir = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve() if args.output else ingest_root() / "style" / "generated"

    if not input_dir.is_dir():
        print(f"ERROR: input dir not found: {input_dir}")
        return 1

    docs = build_style_pack(
        input_dir=input_dir,
        output_dir=output_dir,
        default_era=args.default_era,
        use_llm=bool(args.use_llm),
        llm_role=args.llm_role,
        dry_run=bool(args.dry_run),
    )
    if not docs:
        print(f"No supported source docs found in {input_dir}")
        return 1

    llm_count = sum(1 for d in docs if d.generated_with_llm)
    print(f"Generated {len(docs)} style docs")
    print(f"LLM-polished docs: {llm_count}")
    print(f"Output root: {output_dir}")
    if args.dry_run:
        print("Dry run only: no files written")
    return 0
