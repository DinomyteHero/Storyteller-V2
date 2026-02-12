"""`storyteller generate-era-content` — auto-generate era pack YAML from ingested lore."""
from __future__ import annotations

from pathlib import Path

from shared.config import ERA_PACK_DIR


def register(subparsers) -> None:
    p = subparsers.add_parser(
        "generate-era-content",
        help="Generate quest/companion YAML scaffolds from ingested lore (deterministic + optional LLM)",
    )
    p.add_argument("--era", type=str, required=True, help="Era identifier (e.g. REBELLION, LEGACY)")
    p.add_argument("--output", type=str, default=None, help="Output directory (default: era_packs/<era>/generated/)")
    p.add_argument("--num-quests", type=int, default=6, help="Number of quests to generate (default: 6)")
    p.add_argument("--num-companions", type=int, default=4, help="Number of companions to generate (default: 4)")
    p.add_argument("--use-llm", action="store_true", help="Use LLM to fill in creative placeholders")
    p.add_argument("--llm-role", type=str, default="ingestion_tagger", help="LLM role for enrichment")
    p.add_argument("--db", type=str, default=None, help="LanceDB path (uses default if not specified)")
    p.add_argument("--dry-run", action="store_true", help="Preview generation without writing files")
    p.set_defaults(func=run)


def run(args) -> int:
    from ingestion.era_content_generator import generate_era_content

    era = args.era.strip().upper()
    output_dir = (
        Path(args.output).expanduser().resolve()
        if args.output
        else Path(str(ERA_PACK_DIR)) / era.lower() / "generated"
    )

    print(f"Generating era content for: {era}")
    print(f"Output directory: {output_dir}")
    if args.dry_run:
        print("(dry run — no files will be written)")

    result = generate_era_content(
        era=era,
        output_dir=output_dir,
        num_quests=args.num_quests,
        num_companions=args.num_companions,
        use_llm=bool(args.use_llm),
        llm_role=args.llm_role,
        db_path=args.db,
        dry_run=bool(args.dry_run),
    )

    print(f"\nGenerated {len(result.quests)} quests, {len(result.companions)} companions")
    print(f"Lore chunks used: {result.manifest.get('lore_chunks_used', 0)}")
    print(f"Entities detected: {result.manifest.get('entities_detected', {})}")
    print(f"Genres detected: {result.manifest.get('genres_detected', [])}")

    if not args.dry_run:
        print(f"\nFiles written to: {output_dir}")
        print("  generated_quests.yaml      — Review and merge into quests.yaml")
        print("  generated_companions.yaml   — Review and merge into companions.yaml")
        print("  _generation_manifest.json   — Generation metadata")
        print("\nIMPORTANT: Generated content contains [AUTHOR:] placeholders.")
        print("Review and edit before merging into your era pack.")
    else:
        print("\nDry run complete. No files written.")

    return 0
