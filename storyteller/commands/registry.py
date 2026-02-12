"""Command registry for storyteller CLI.

Keeps command discovery/wiring in one focused module so CLI entrypoint stays thin.
"""
from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Iterable

COMMAND_MODULES: tuple[str, ...] = (
    "doctor",
    "setup",
    "dev",
    "ingest",
    "query",
    "extract_knowledge",
    "organize_ingest",
    "models",
    "style_audit",
    "build_style_pack",
    "generate_era_content",
)


def iter_command_modules() -> Iterable[ModuleType]:
    """Yield command modules in stable registration order."""
    for name in COMMAND_MODULES:
        yield import_module(f"storyteller.commands.{name}")


def register_all(subparsers) -> None:
    """Register all known command modules on the provided argparse subparsers."""
    for module in iter_command_modules():
        module.register(subparsers)
