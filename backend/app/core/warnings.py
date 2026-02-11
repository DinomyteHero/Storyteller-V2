"""Warning aggregation helpers for turn pipeline."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _get_container(target: Any) -> list[str] | None:
    """Return a mutable warnings list from target (list, dict, or object with .warnings)."""
    if target is None:
        return None
    if isinstance(target, list):
        return target
    if isinstance(target, dict):
        warnings = target.get("warnings")
        if warnings is None:
            warnings = []
            target["warnings"] = warnings
        return warnings
    if hasattr(target, "warnings"):
        warnings = getattr(target, "warnings", None)
        if warnings is None:
            warnings = []
            try:
                setattr(target, "warnings", warnings)
            except Exception as e:
                logger.debug("Failed to attach warnings to target: %s", e)
                return None
        return warnings
    return None


def add_warning(target: Any, message: str) -> None:
    """Append a warning to the target's warning list (deduped)."""
    if not message:
        return
    warnings = _get_container(target)
    if warnings is None:
        return
    if message not in warnings:
        warnings.append(message)
