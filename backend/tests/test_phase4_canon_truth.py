from __future__ import annotations

import os
import tempfile

from backend.app.api.v2_campaigns import (
    _merge_canon_constraints_into_world_state,
    _seed_immutable_canon_truth_facts,
)
from backend.app.db.connection import get_connection
from backend.app.db.migrate import apply_schema
from backend.app.models.turn_contract import Fact
from backend.app.core.truth_ledger import get_facts_with_meta, upsert_facts


def test_immutable_truth_fact_cannot_be_overwritten() -> None:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name
    try:
        apply_schema(db_path)
        conn = get_connection(db_path)
        try:
            conn.execute(
                "INSERT INTO campaigns (id, title, time_period, world_state_json) VALUES (?, ?, ?, ?)",
                ("camp-imm", "Canon Test", "REBELLION", "{}"),
            )
            upsert_facts(
                conn,
                "camp-imm",
                "setup",
                [Fact(fact_key="canon_event_test", fact_value="0 BBY: Death Star destroyed")],
                is_immutable=True,
            )
            upsert_facts(
                conn,
                "camp-imm",
                "turn-2",
                [Fact(fact_key="canon_event_test", fact_value="0 BBY: Death Star survives")],
                is_immutable=False,
            )
            facts, immutable = get_facts_with_meta(conn, "camp-imm")
            assert facts["canon_event_test"] == "0 BBY: Death Star destroyed"
            assert immutable["canon_event_test"] is True
        finally:
            conn.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_seed_immutable_canon_truth_facts_and_world_state_ledger() -> None:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name
    try:
        apply_schema(db_path)
        conn = get_connection(db_path)
        try:
            conn.execute(
                "INSERT INTO campaigns (id, title, time_period, world_state_json) VALUES (?, ?, ?, ?)",
                ("camp-seed", "Seed Test", "REBELLION", "{}"),
            )
            events = [
                "0 BBY: Death Star destroyed at the Battle of Yavin by Luke Skywalker",
                "4 ABY: Battle of Endor - Emperor Palpatine and Darth Vader killed",
            ]
            _seed_immutable_canon_truth_facts(conn, "camp-seed", events)
            facts, immutable = get_facts_with_meta(conn, "camp-seed")
            assert len(facts) == 2
            assert all(immutable.get(k) for k in facts.keys())
        finally:
            conn.close()

        ws: dict = {}
        _merge_canon_constraints_into_world_state(
            ws,
            [
                "0 BBY: Death Star destroyed at the Battle of Yavin by Luke Skywalker",
                "4 ABY: Battle of Endor - Emperor Palpatine and Darth Vader killed",
            ],
        )
        ledger = ws.get("ledger") or {}
        facts = ledger.get("established_facts") or []
        constraints = ledger.get("constraints") or []
        assert any("Canon:" in item for item in facts)
        assert any("Immutable canon event:" in item for item in constraints)
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)
