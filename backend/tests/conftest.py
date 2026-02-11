"""Pytest setup: force temp files into workspace and disable optional LLM repair."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4


def pytest_sessionstart(session) -> None:
    """Redirect temp files to a writable workspace path for tests."""
    tmp_root = Path(__file__).resolve().parent / ".tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    for key in ("TMPDIR", "TEMP", "TMP"):
        os.environ[key] = str(tmp_root)
    tempfile.tempdir = str(tmp_root)
    os.environ["MECHANIC_LLM_REPAIR_ENABLED"] = "0"
    os.environ["STORYTELLER_DUMMY_EMBEDDINGS"] = "1"

    class _WorkspaceTemporaryDirectory:
        """TemporaryDirectory variant that uses a workspace path with safe permissions."""

        def __init__(self, suffix: str | None = None, prefix: str | None = None, dir: str | None = None, **_kwargs):
            base = Path(dir) if dir else tmp_root
            name = f"{(prefix or 'tmp')}{uuid4().hex}{suffix or ''}"
            self._path = base / name
            self._path.mkdir(parents=True, exist_ok=False)

        def __enter__(self) -> str:
            return str(self._path)

        def __exit__(self, exc_type, exc, tb) -> None:
            shutil.rmtree(self._path, ignore_errors=True)

    tempfile.TemporaryDirectory = _WorkspaceTemporaryDirectory
