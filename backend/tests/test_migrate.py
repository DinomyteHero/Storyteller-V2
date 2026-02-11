"""DB migration smoke test."""
import os
import tempfile
import unittest

from backend.app.db.migrate import apply_schema


class TestMigrate(unittest.TestCase):
    def test_apply_schema_idempotent(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            apply_schema(path)
            apply_schema(path)
            import sqlite3
            conn = sqlite3.connect(path)
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('campaigns', 'characters', 'turn_events', 'rendered_turns', 'schema_migrations')"
            )
            tables = {r[0] for r in cur.fetchall()}
            conn.close()
            self.assertIn("campaigns", tables)
            self.assertIn("characters", tables)
            self.assertIn("turn_events", tables)
            self.assertIn("schema_migrations", tables)
        finally:
            if os.path.exists(path):
                os.unlink(path)
