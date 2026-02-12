"""Storyteller AI – unified CLI dispatcher.

All subcommands live in ``storyteller/commands/*.py`` and expose a
``register(subparsers)`` function that adds themselves to argparse.
"""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="storyteller",
        description="Storyteller AI — local narrative RPG engine CLI",
    )
    sub = parser.add_subparsers(dest="command")

    # Import and register each command
    from storyteller.commands import doctor, setup, dev, ingest, query, extract_knowledge, organize_ingest, models, style_audit, build_style_pack, generate_era_content

    doctor.register(sub)
    setup.register(sub)
    dev.register(sub)
    ingest.register(sub)
    query.register(sub)
    extract_knowledge.register(sub)
    organize_ingest.register(sub)
    models.register(sub)
    style_audit.register(sub)
    build_style_pack.register(sub)
    generate_era_content.register(sub)

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Each command stores a ``func`` on the namespace
    rc = args.func(args)
    sys.exit(rc or 0)
