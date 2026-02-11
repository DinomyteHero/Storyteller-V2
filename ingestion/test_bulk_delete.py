"""Tests for bulk delete filter validation in LanceStore."""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import pytest

from ingestion.store import LanceStore


class TestDeleteByFilterValidation:
    """Test that delete_by_filter rejects empty filters and accepts valid ones."""

    def test_no_filters_raises(self):
        """At least one filter must be specified."""
        store = LanceStore.__new__(LanceStore)
        with pytest.raises(ValueError, match="At least one filter"):
            store.delete_by_filter()

    def test_era_filter_builds_condition(self):
        """Verify the method accepts era parameter (unit validation only)."""
        # We test the validation logic, not actual DB operations.
        # LanceStore.delete_by_filter checks for at least one filter before DB ops.
        store = LanceStore.__new__(LanceStore)
        # Create a mock table that has the needed methods
        class MockTable:
            def to_pandas(self, columns=None):
                import pandas as pd
                return pd.DataFrame({"id": []})
            def delete(self, where):
                pass
        store.table = MockTable()
        store._cache = type("C", (), {"invalidate_all": lambda self: None})()
        deleted = store.delete_by_filter(era="REBELLION")
        assert isinstance(deleted, int)
        assert deleted == 0

    def test_source_filter_accepted(self):
        store = LanceStore.__new__(LanceStore)
        class MockTable:
            def to_pandas(self, columns=None):
                import pandas as pd
                return pd.DataFrame({"id": []})
            def delete(self, where):
                pass
        store.table = MockTable()
        store._cache = type("C", (), {"invalidate_all": lambda self: None})()
        deleted = store.delete_by_filter(source="my_novel.txt")
        assert deleted == 0

    def test_doc_type_filter_accepted(self):
        store = LanceStore.__new__(LanceStore)
        class MockTable:
            def to_pandas(self, columns=None):
                import pandas as pd
                return pd.DataFrame({"id": []})
            def delete(self, where):
                pass
        store.table = MockTable()
        store._cache = type("C", (), {"invalidate_all": lambda self: None})()
        deleted = store.delete_by_filter(doc_type="narrative")
        assert deleted == 0

    def test_multiple_filters_accepted(self):
        store = LanceStore.__new__(LanceStore)
        class MockTable:
            def to_pandas(self, columns=None):
                import pandas as pd
                return pd.DataFrame({"id": []})
            def delete(self, where):
                pass
        store.table = MockTable()
        store._cache = type("C", (), {"invalidate_all": lambda self: None})()
        deleted = store.delete_by_filter(era="LOTF", doc_type="narrative")
        assert deleted == 0

    def test_sql_injection_safe(self):
        """Verify that single quotes in filter values are escaped."""
        store = LanceStore.__new__(LanceStore)
        class MockTable:
            def __init__(self):
                self.last_where = None
            def to_pandas(self, columns=None):
                import pandas as pd
                return pd.DataFrame({"id": []})
            def delete(self, where):
                self.last_where = where
        mock_table = MockTable()
        store.table = mock_table
        store._cache = type("C", (), {"invalidate_all": lambda self: None})()
        store.delete_by_filter(era="it's a trap")
        assert "''" in mock_table.last_where  # escaped single quote
