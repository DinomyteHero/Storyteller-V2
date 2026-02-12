#!/usr/bin/env python3
"""Check playability gates for discovered content periods.

Combines content catalog metadata + lore index coverage thresholds.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import lancedb

from backend.app.content.repository import CONTENT_REPOSITORY
from backend.app.config import resolve_vectordb_path, LORE_TABLE_NAME


def _count_rows(table, *, setting_id: str, period_id: str, era_id: str) -> dict[str, int]:
    out = {"total": 0, "novel": 0, "with_npc_links": 0}
    tbl = table.to_arrow()
    d = tbl.to_pydict()
    schema_cols = {f.name for f in table.schema}

    def _match(i: int) -> bool:
        if "setting_id" in schema_cols and "period_id" in schema_cols:
            s = str((d.get("setting_id") or [""])[i] or "").strip().lower()
            p = str((d.get("period_id") or [""])[i] or "").strip().lower()
            return s == setting_id.lower() and p == period_id.lower()
        if "era" in schema_cols:
            e = str((d.get("era") or [""])[i] or "").strip().lower()
            return e == era_id.strip().lower()
        return True

    for i in range(tbl.num_rows):
        if not _match(i):
            continue
        out["total"] += 1
        doc_type = str((d.get("doc_type") or [""])[i] or "") if d.get("doc_type") else ""
        if doc_type.lower() == "novel":
            out["novel"] += 1
        rel = str((d.get("related_npcs_json") or [""])[i] or "") if d.get("related_npcs_json") else ""
        if rel and rel != "[]":
            out["with_npc_links"] += 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate playability gates per setting/period")
    ap.add_argument("--db", type=str, default=None, help="LanceDB path (defaults to VECTORDB_PATH or ./data/lancedb)")
    ap.add_argument("--min-lore-chunks", type=int, default=50)
    ap.add_argument("--min-novel-chunks", type=int, default=10)
    ap.add_argument("--min-npc-linked-chunks", type=int, default=5)
    args = ap.parse_args()

    items = CONTENT_REPOSITORY.list_catalog()
    if not items:
        print("ERR no catalog items discovered")
        return 1

    db_path = resolve_vectordb_path(args.db)
    if not Path(db_path).exists():
        print(f"ERR lancedb path not found: {db_path}")
        return 1

    db = lancedb.connect(str(db_path))
    try:
        table = db.open_table(LORE_TABLE_NAME)
    except Exception as exc:
        print(f"ERR cannot open table {LORE_TABLE_NAME}: {exc}")
        return 1

    failures = 0
    for item in items:
        counts = _count_rows(
            table,
            setting_id=item["setting_id"],
            period_id=item["period_id"],
            era_id=item["legacy_era_id"],
        )
        reasons: list[str] = []
        if counts["total"] < args.min_lore_chunks:
            reasons.append(f"lore<{args.min_lore_chunks}")
        if counts["novel"] < args.min_novel_chunks:
            reasons.append(f"novel<{args.min_novel_chunks}")
        if counts["with_npc_links"] < args.min_npc_linked_chunks:
            reasons.append(f"npc_links<{args.min_npc_linked_chunks}")

        status = "OK " if not reasons else "ERR"
        print(
            f"{status} {item['setting_id']}/{item['period_id']}: "
            f"lore={counts['total']} novel={counts['novel']} npc_links={counts['with_npc_links']}"
            + ("" if not reasons else f" reasons={','.join(reasons)}")
        )
        if reasons:
            failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
