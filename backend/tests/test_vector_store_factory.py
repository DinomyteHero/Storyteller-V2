from __future__ import annotations

import pytest

from backend.app.rag.vector_store import LanceDBStore, create_vector_store


def test_create_vector_store_defaults_to_lancedb(tmp_path):
    store = create_vector_store(tmp_path, "lore_chunks")
    assert isinstance(store, LanceDBStore)


def test_create_vector_store_unsupported_backend_raises(tmp_path):
    with pytest.raises(ValueError):
        create_vector_store(tmp_path, "lore_chunks", backend="qdrant")
