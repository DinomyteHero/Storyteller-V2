"""Persist UI preferences (theme, toggles) to a local JSON file.

File: data/ui_prefs.json
Falls back gracefully if the file is missing, corrupt, or unwritable.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_PREFS_PATH = Path(__file__).resolve().parents[1] / "data" / "ui_prefs.json"

# Keys we persist (must match session_state names)
_PREF_KEYS = frozenset({
    "theme_name",
    "typewriter_effect",
    "reduce_motion",
    "high_contrast",
    "ui_mode",
    "show_debug",
})


def load_preferences() -> dict:
    """Load saved preferences from disk. Returns {} on any error.

    Also seeds the write-on-change cache so the next save is a no-op if
    nothing changed.
    """
    global _last_saved
    try:
        if _PREFS_PATH.exists():
            data = json.loads(_PREFS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                result = {k: v for k, v in data.items() if k in _PREF_KEYS}
                _last_saved = dict(result)
                return result
    except Exception as exc:
        logger.debug("Could not load UI prefs: %s", exc)
    return {}


_last_saved: dict | None = None


def save_preferences(prefs: dict) -> None:
    """Write preferences to disk **only when values have changed**.

    Keeps an in-process snapshot of the last written state to avoid
    redundant disk I/O on every Streamlit rerun.
    """
    global _last_saved
    filtered = {k: v for k, v in prefs.items() if k in _PREF_KEYS}
    if _last_saved is not None and filtered == _last_saved:
        return  # nothing changed
    try:
        _PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _PREFS_PATH.write_text(
            json.dumps(filtered, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        _last_saved = filtered
    except Exception as exc:
        logger.debug("Could not save UI prefs: %s", exc)
