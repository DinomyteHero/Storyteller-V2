"""Concurrency tests for event_store turn-number reservation."""

from __future__ import annotations

import sqlite3
import tempfile
import threading
from pathlib import Path

from backend.app.core.event_store import reserve_next_turn_number
from backend.app.db.migrate import apply_schema


def _seed_campaign(conn: sqlite3.Connection, campaign_id: str = "cmp-1") -> None:
    conn.execute(
        """
        INSERT INTO campaigns (id, title, time_period, world_state_json, created_at, updated_at)
        VALUES (?, 'Test', 'REBELLION', '{}', datetime('now'), datetime('now'))
        """,
        (campaign_id,),
    )
    conn.commit()


def test_reserve_next_turn_number_sequential_allocations() -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "story.db")
        apply_schema(db_path)
        conn = sqlite3.connect(db_path)
        try:
            _seed_campaign(conn)
            a = reserve_next_turn_number(conn, "cmp-1")
            b = reserve_next_turn_number(conn, "cmp-1")
            c = reserve_next_turn_number(conn, "cmp-1")
            conn.commit()
            assert (a, b, c) == (1, 2, 3)
        finally:
            conn.close()


def test_reserve_next_turn_number_concurrent_unique_allocations() -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "story.db")
        apply_schema(db_path)
        conn = sqlite3.connect(db_path)
        try:
            _seed_campaign(conn)
        finally:
            conn.close()

        start = threading.Barrier(8)
        out: list[int] = []
        lock = threading.Lock()

        def worker() -> None:
            local = sqlite3.connect(db_path, timeout=5.0)
            try:
                start.wait()
                t = reserve_next_turn_number(local, "cmp-1", max_retries=50)
                local.commit()
                with lock:
                    out.append(t)
            finally:
                local.close()

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert sorted(out) == [1, 2, 3, 4, 5, 6, 7, 8]
