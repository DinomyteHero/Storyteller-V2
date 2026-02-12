"""Abstract VectorStore interface for swappable vector DB backends.

The VectorStore protocol decouples retrieval logic from the concrete vector DB
implementation (currently LanceDB). To switch backends (e.g., Chroma, Qdrant,
Pinecone), implement a new VectorStore subclass — no retriever changes needed.

Usage:
    store = LanceDBStore(db_path, table_name)
    results = store.search(query_vector, top_k=6, where="era = 'REBELLION'")
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single vector search result."""
    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class VectorStore(Protocol):
    """Protocol for vector database backends.

    Implementations must provide:
      - search(): vector similarity search with optional SQL-style WHERE filter
      - table_exists(): check if a named table/collection exists
      - get_schema_columns(): introspect available columns for safe filter building
    """

    def search(
        self,
        query_vector: list[float],
        top_k: int = 6,
        where: str | None = None,
    ) -> list[dict[str, Any]]:
        """Execute vector similarity search.

        Args:
            query_vector: Query embedding vector.
            top_k: Maximum results to return.
            where: Optional SQL-style WHERE clause for metadata filtering.
                   Syntax is backend-specific; LanceDB uses SQL fragments.

        Returns:
            List of row dicts with all columns + '_distance' score.
        """
        ...

    def table_exists(self, table_name: str) -> bool:
        """Check whether a named table/collection exists."""
        ...

    def get_schema_columns(self) -> set[str]:
        """Return the set of column names in the current table."""
        ...


class LanceDBStore:
    """LanceDB-backed VectorStore implementation.

    Wraps the existing _cache.py connection/table pooling.
    """

    def __init__(self, db_path: str | Path, table_name: str) -> None:
        self._db_path = Path(db_path)
        self._table_name = table_name
        self._table: Any | None = None
        self._schema_cols: set[str] | None = None

    def _get_table(self) -> Any:
        if self._table is None:
            from backend.app.rag._cache import get_lancedb_table
            self._table = get_lancedb_table(self._db_path, self._table_name)
        return self._table

    def table_exists(self, table_name: str | None = None) -> bool:
        """Check if the table exists in LanceDB."""
        target = table_name or self._table_name
        try:
            from backend.app.rag._cache import get_lancedb_connection
            conn = get_lancedb_connection(self._db_path)
            return target in conn.table_names()
        except Exception:
            return False

    def get_schema_columns(self) -> set[str]:
        """Return column names from the Arrow schema."""
        if self._schema_cols is None:
            table = self._get_table()
            self._schema_cols = {f.name for f in table.schema}
        return self._schema_cols

    def search(
        self,
        query_vector: list[float],
        top_k: int = 6,
        where: str | None = None,
    ) -> list[dict[str, Any]]:
        """Execute LanceDB vector search with optional WHERE filter.

        Returns list of row dicts (pydict format) with '_distance' column.
        """
        table = self._get_table()
        q = table.search(query_vector).limit(top_k)
        if where:
            q = q.where(where)
        tbl = q.to_arrow()
        if tbl.num_rows == 0:
            return []
        d = tbl.to_pydict()
        rows: list[dict[str, Any]] = []
        for i in range(tbl.num_rows):
            row = {}
            for col_name, col_values in d.items():
                row[col_name] = col_values[i] if i < len(col_values) else None
            rows.append(row)
        return rows

    def search_multi_where(
        self,
        query_vector: list[float],
        top_k: int = 6,
        where_clauses: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute search with multiple chained WHERE clauses.

        LanceDB supports chaining .where() calls (AND semantics).
        """
        table = self._get_table()
        q = table.search(query_vector).limit(top_k)
        for clause in (where_clauses or []):
            q = q.where(clause)
        tbl = q.to_arrow()
        if tbl.num_rows == 0:
            return []
        d = tbl.to_pydict()
        rows: list[dict[str, Any]] = []
        for i in range(tbl.num_rows):
            row = {}
            for col_name, col_values in d.items():
                row[col_name] = col_values[i] if i < len(col_values) else None
            rows.append(row)
        return rows
