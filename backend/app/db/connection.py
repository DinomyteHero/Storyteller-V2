"""SQLite connection factory for Storyteller database layer.

Provides configured connections with:
- sqlite3.Row row factory (dict-like access)
- Foreign keys enabled (PRAGMA foreign_keys = ON)
"""
import sqlite3
from collections.abc import Generator
from pathlib import Path


def get_connection(db_path: str) -> sqlite3.Connection:
    """Return a configured SQLite connection.

    Args:
        db_path: Path to the SQLite database file. Parent directories
                 are created if they do not exist.

    Returns:
        sqlite3.Connection with row_factory=sqlite3.Row and foreign
        keys enabled.

    Note:
        Compatible with Windows paths. The connection does not
        auto-close; callers must close it or use as a context manager.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency that yields a SQLite connection.

    Uses DEFAULT_DB_PATH from project config. The connection is
    automatically closed when the request finishes.
    """
    from backend.app.config import DEFAULT_DB_PATH

    conn = get_connection(DEFAULT_DB_PATH)
    try:
        yield conn
    finally:
        conn.close()
