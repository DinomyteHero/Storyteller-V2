from __future__ import annotations

from dataclasses import dataclass

from backend.app.rag import lore_retriever


class _FakeEncoder:
    def encode(self, texts, show_progress_bar=False):
        return [[0.1, 0.2, 0.3]]


@dataclass
class _FakeField:
    name: str


class _FakeArrow:
    def __init__(self, rows):
        self._rows = rows
        self.num_rows = len(rows)

    def to_pydict(self):
        cols = {}
        for row in self._rows:
            for k, v in row.items():
                cols.setdefault(k, []).append(v)
        return cols


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows
        self.filters: list[str] = []

    def limit(self, _k):
        return self

    def where(self, clause):
        self.filters.append(clause)
        return self

    def to_arrow(self):
        # return all rows; tests validate filter clauses were applied
        return _FakeArrow(self._rows)


class _FakeTable:
    def __init__(self, rows):
        self._rows = rows
        self.schema = [_FakeField(k) for k in rows[0].keys()]
        self.last_query = None

    def search(self, _vector):
        self.last_query = _FakeQuery(self._rows)
        return self.last_query


def test_retrieve_lore_applies_setting_period_and_related_npc_filters(monkeypatch):
    rows = [
        {
            "text": "alpha",
            "era": "rebellion",
            "time_period": "rebellion",
            "setting_id": "star_wars_legends",
            "period_id": "rebellion",
            "doc_type": "novel",
            "section_kind": "scene",
            "related_npcs_json": '["leia_organa"]',
            "characters_json": '["leia_organa"]',
            "book_title": "Book",
            "chapter_title": "Ch1",
            "chunk_id": "c1",
            "_distance": 0.1,
            "source_type": "novel",
            "planet": "Yavin",
            "faction": "Rebel",
            "universe": "sw",
        }
    ]
    fake_table = _FakeTable(rows)

    monkeypatch.setattr(lore_retriever, "get_lancedb_table", lambda *_: fake_table)
    monkeypatch.setattr(lore_retriever, "get_encoder", lambda *_: _FakeEncoder())
    monkeypatch.setattr(lore_retriever, "_assert_vector_dim", lambda *_: None)

    out = lore_retriever.retrieve_lore(
        "find leia",
        top_k=3,
        setting_id="star_wars_legends",
        period_id="rebellion",
        related_npcs=["leia_organa"],
        db_path=".",
        table_name="lore_chunks",
    )

    assert out
    applied = "\n".join(fake_table.last_query.filters)
    assert "setting_id = 'star_wars_legends'" in applied
    assert "period_id = 'rebellion'" in applied
    assert "related_npcs_json LIKE '%\"leia_organa\"%'" in applied
    assert out[0]["metadata"]["setting_id"] == "star_wars_legends"
    assert out[0]["metadata"]["period_id"] == "rebellion"
