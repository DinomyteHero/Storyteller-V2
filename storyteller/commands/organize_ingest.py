"""`storyteller organize-ingest` — auto-sort messy lore docs for ingestion."""
from __future__ import annotations

from pathlib import Path

from ingestion.organize import organize_documents, write_manifest
from shared.ingest_paths import ingest_root


def register(subparsers) -> None:
    p = subparsers.add_parser("organize-ingest", help="Organize messy lore docs into ingestion-ready folders")
    p.add_argument("--input", type=str, required=True, help="Folder containing unsorted documents")
    p.add_argument("--output", type=str, default=None, help="Output root (default: <ingest-root>/lore)")
    p.add_argument("--default-era", type=str, default=None, help="Fallback era when unknown")
    p.add_argument("--move", action="store_true", help="Move files instead of copy")
    p.add_argument("--dry-run", action="store_true", help="Preview organization without writing files")
    p.set_defaults(func=run)


def run(args) -> int:
    input_dir = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve() if args.output else ingest_root() / "lore"

    if not input_dir.is_dir():
        print(f"ERROR: Input directory not found: {input_dir}")
        return 1

    results = organize_documents(
        input_dir=input_dir,
        output_dir=output_dir,
        default_era=args.default_era,
        copy_mode=not args.move,
        dry_run=args.dry_run,
    )
    if not results:
        print(f"No supported documents found in {input_dir}")
        return 1

    llm_count = sum(1 for r in results if r.used_llm_fallback)
    avg_conf = sum(r.confidence for r in results) / max(len(results), 1)
    print(f"Organized {len(results)} documents into {output_dir}")
    print(f"Average classification confidence: {avg_conf:.2f}")
    print(f"LLM fallback used on {llm_count} documents")

    if not args.dry_run:
        manifest_path = output_dir / "_organize_manifest.json"
        write_manifest(results, manifest_path)
        print(f"Manifest written: {manifest_path}")

    return 0
