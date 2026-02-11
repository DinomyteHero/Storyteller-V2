"""Schema migration: applies numbered SQL files from migrations/ in order.

Idempotent: each migration name recorded in schema_migrations; applied once.

Usage:
    python -m backend.app.db.migrate --db ./data/storyteller.db
"""
import argparse
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

SCHEMA_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  name TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL
);
"""

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _migration_files() -> list[Path]:
    """Return sorted list of .sql files in migrations/ (0001_*.sql, 0002_*.sql, ...)."""
    if not MIGRATIONS_DIR.exists():
        return []
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    return files


def apply_schema(db_path: str) -> None:
    """Apply all pending migrations from migrations/ in order."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row

    try:
        conn.executescript(SCHEMA_MIGRATIONS_TABLE)
        conn.commit()

        cursor = conn.cursor()
        for fp in _migration_files():
            name = fp.stem  # e.g. 0001_init
            cursor.execute(
                "SELECT name FROM schema_migrations WHERE name = ?",
                (name,),
            )
            if cursor.fetchone():
                continue
            sql = fp.read_text(encoding="utf-8")
            try:
                conn.executescript(sql)
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e).lower():
                    pass
                else:
                    raise
            now = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
                (name, now),
            )
            conn.commit()
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply migrations to SQLite database."
    )
    parser.add_argument(
        "--db",
        type=str,
        default="./data/storyteller.db",
        help="Path to SQLite database file",
    )
    args = parser.parse_args()
    apply_schema(args.db)
    print(f"Migrations applied: {args.db}")


if __name__ == "__main__":
    main()
