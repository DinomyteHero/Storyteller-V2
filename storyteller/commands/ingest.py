"""``storyteller ingest`` — run ingestion with guardrails.

Wraps ``ingestion.ingest`` (simple) and ``ingestion.ingest_lore`` (lore)
with pre-flight checks: Ollama reachability, model availability,
PDF file detection with pipeline guidance, and progress hints.

If a virtual environment (venv/ or .venv/) exists, it will be used automatically.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from shared.ingest_paths import ingest_root


def register(subparsers) -> None:
    p = subparsers.add_parser("ingest", help="Ingest documents into the vector store")
    p.add_argument(
        "--pipeline", choices=["simple", "lore"], default="lore",
        help="Ingestion pipeline: 'simple' (TXT/EPUB flat chunks) or 'lore' (PDF/EPUB/TXT enriched). Default: lore",
    )
    p.add_argument("--input", type=str, default=None, help="Input directory (default: <ingest-root>/lore)")
    p.add_argument("--era", "--time-period", type=str, help="Era / time period label (e.g. LOTF)")
    p.add_argument("--source-type", type=str, help="Source type (e.g. novel, reference)")
    p.add_argument("--planet", type=str, help="Planet filter (lore pipeline)")
    p.add_argument("--faction", type=str, help="Faction filter (lore pipeline)")
    p.add_argument("--collection", type=str, help="Collection name (lore pipeline)")
    p.add_argument("--book-title", type=str, help="Book title override")
    p.add_argument("--out-db", type=str, default=None, help="LanceDB output path (default: <ingest-root>/lancedb)")
    p.add_argument("--era-pack", type=str, help="Era pack id for NPC tagging (defaults to --era)")
    p.add_argument("--tag-npcs", dest="tag_npcs", action="store_true", help="Enable deterministic NPC tagging")
    p.add_argument("--no-tag-npcs", dest="tag_npcs", action="store_false", help="Disable NPC tagging")
    p.set_defaults(tag_npcs=None)
    p.add_argument("--npc-tagging-mode", choices=["strict", "lenient"], default=None, help="NPC tagging mode")
    p.add_argument("--skip-checks", action="store_true", help="Skip Ollama/model pre-flight checks")
    p.add_argument("--ingest-root", type=str, default=None, help="Portable ingestion root (uses <root>/lore + <root>/lancedb)")
    p.add_argument("--no-venv", action="store_true", help="Skip venv detection, use current Python")
    p.add_argument("--yes", "--non-interactive", dest="yes", action="store_true", help="Run non-interactively (auto-confirm prompts)")
    p.add_argument("--allow-legacy", action="store_true", help="Allow deprecated simple ingestion pipeline")
    p.set_defaults(func=run)


def _find_venv_python() -> Path | None:
    """Find venv Python executable (venv/ or .venv/)."""
    root = Path.cwd()
    candidates = [
        root / "venv" / "Scripts" / "python.exe",  # Windows venv
        root / ".venv" / "Scripts" / "python.exe",  # Windows .venv
        root / "venv" / "bin" / "python",  # Unix venv
        root / ".venv" / "bin" / "python",  # Unix .venv
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _is_in_venv() -> bool:
    """Check if current Python is running in a virtual environment."""
    return hasattr(sys, 'real_prefix') or (
        hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix
    )


def _has_pdfs(input_dir: Path) -> bool:
    return any(input_dir.glob("**/*.pdf"))


def _has_supported_files(input_dir: Path) -> bool:
    exts = ("*.txt", "*.epub", "*.pdf")
    return any(f for ext in exts for f in input_dir.glob(f"**/{ext}"))


def _check_embedding_model() -> bool:
    """Verify the embedding model is accessible (downloads if needed)."""
    try:
        model_name = os.environ.get("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        print(f"  Checking embedding model: {model_name}")
        print(f"  (First run will download the model — this may take a moment)")
        from sentence_transformers import SentenceTransformer
        _ = SentenceTransformer(model_name)
        print(f"  Embedding model ready")
        return True
    except Exception as e:
        print(f"  ERROR: Embedding model failed to load: {e}")
        return False


def run(args) -> int:
    # Check for venv and warn if not using it
    if not args.no_venv:
        venv_python = _find_venv_python()
        if venv_python and not _is_in_venv():
            print()
            print(f"  WARNING: Virtual environment found but not active!")
            print(f"           Found: {venv_python.parent.parent.name}/")
            print(f"           Currently using: {sys.executable}")
            print()
            print(f"  For best results, activate the venv first:")
            if sys.platform == "win32":
                print(f"    .\\{venv_python.parent.parent.name}\\Scripts\\Activate.ps1")
            else:
                print(f"    source {venv_python.parent.parent.name}/bin/activate")
            print(f"  Then run: storyteller ingest ...")
            print()
            if not args.yes:
                resp = input("  Continue anyway? [y/N]: ")
                if resp.strip().lower() != "y":
                    return 0
            else:
                print("  --yes supplied: continuing without prompt")
        elif venv_python and _is_in_venv():
            print(f"  Using virtual environment: {Path(sys.prefix).name}/")
        elif not venv_python:
            print("  INFO: No virtual environment detected (checked venv/ and .venv/)")
            print("        Consider creating one with: python -m venv venv")
            print()

    resolved_root = Path(args.ingest_root).expanduser().resolve() if args.ingest_root else ingest_root()
    input_arg = args.input or str(resolved_root / "lore")
    out_db_arg = args.out_db or str(resolved_root / "lancedb")

    input_dir = Path(input_arg).resolve()
    args._resolved_input = str(input_dir)
    args._resolved_out_db = str(Path(out_db_arg).expanduser().resolve())

    # Validate input directory
    if not input_dir.is_dir():
        print(f"  ERROR: Input directory not found: {input_dir}")
        print(f"         Create it and add your documents, or specify --input <path>")
        return 1

    if not _has_supported_files(input_dir):
        print(f"  ERROR: No supported files found in {input_dir}")
        print(f"         Supported formats: .txt, .epub, .pdf")
        return 1

    # Guardrail: legacy simple pipeline requires explicit opt-in
    if args.pipeline == "simple" and not args.allow_legacy:
        print("  ERROR: The simple pipeline is deprecated and gated behind --allow-legacy")
        print("         Use --pipeline lore (recommended) or re-run with --allow-legacy")
        return 1

    # Guardrail: PDFs found but using simple pipeline
    if args.pipeline == "simple" and _has_pdfs(input_dir):
        print(f"  WARNING: PDF files detected in {input_dir}")
        print(f"           The 'simple' pipeline does NOT support PDFs.")
        print(f"           Use the 'lore' pipeline instead:")
        print(f"")
        print(f"             python -m storyteller ingest --pipeline lore --input {args._resolved_input}")
        print(f"")
        if not args.yes:
            resp = input("  Continue with simple pipeline anyway? (PDFs will be skipped) [y/N]: ")
            if resp.strip().lower() != "y":
                return 0
        else:
            print("  --yes supplied: continuing with simple pipeline")

    # Pre-flight checks (unless skipped)
    if not args.skip_checks:
        if not _check_embedding_model():
            return 1

    # Build argv for the underlying ingestion module
    if args.pipeline == "lore":
        return _run_lore(args)
    return _run_simple(args)


def _run_lore(args) -> int:
    """Dispatch to ingestion.ingest_lore.main()."""
    argv = ["ingest_lore", "--input", str(args._resolved_input)]
    if args.era:
        argv.extend(["--time-period", args.era])
    if args.planet:
        argv.extend(["--planet", args.planet])
    if args.faction:
        argv.extend(["--faction", args.faction])
    if args.source_type:
        argv.extend(["--source-type", args.source_type])
    if args.collection:
        argv.extend(["--collection", args.collection])
    if args.book_title:
        argv.extend(["--book-title", args.book_title])
    if args.era_pack:
        argv.extend(["--era-pack", args.era_pack])
    if args.tag_npcs is True:
        argv.append("--tag-npcs")
    elif args.tag_npcs is False:
        argv.append("--no-tag-npcs")
    if args.npc_tagging_mode:
        argv.extend(["--npc-tagging-mode", args.npc_tagging_mode])
    if args._resolved_out_db:
        argv.extend(["--db", args._resolved_out_db])

    print(f"\n  Running lore ingestion pipeline ...")
    print(f"  Input: {args._resolved_input}")
    print()

    # Temporarily replace sys.argv for argparse in the target module
    old_argv = sys.argv
    sys.argv = argv
    try:
        from ingestion.ingest_lore import main as lore_main
        rc = lore_main()
        return int(rc or 0)
    finally:
        sys.argv = old_argv


def _run_simple(args) -> int:
    """Dispatch to ingestion.ingest.main()."""
    argv = ["ingest", "--input_dir", str(args._resolved_input)]
    if args.era:
        argv.extend(["--era", args.era])
    if args.source_type:
        argv.extend(["--source_type", args.source_type])
    if args.era_pack:
        argv.extend(["--era-pack", args.era_pack])
    if args.tag_npcs is True:
        argv.append("--tag-npcs")
    elif args.tag_npcs is False:
        argv.append("--no-tag-npcs")
    if args.npc_tagging_mode:
        argv.extend(["--npc-tagging-mode", args.npc_tagging_mode])
    if args._resolved_out_db:
        argv.extend(["--db", args._resolved_out_db])

    print(f"\n  Running simple ingestion pipeline ...")
    print(f"  Input: {args._resolved_input}")
    print()

    old_argv = sys.argv
    sys.argv = argv
    try:
        from ingestion.ingest import main as simple_main
        rc = simple_main()
        return int(rc or 0)
    finally:
        sys.argv = old_argv
