"""Tests for RAG caching: SentenceTransformer and LanceDB connection reuse."""
import os
import unittest
from unittest.mock import patch, MagicMock

from backend.app.rag._cache import get_encoder, clear_caches


class TestEncoderCache(unittest.TestCase):
    """Verify that get_encoder() caches the SentenceTransformer instance."""

    def setUp(self):
        clear_caches()

    def tearDown(self):
        clear_caches()

    @patch("backend.app.rag._cache.SentenceTransformer", create=True)
    def test_encoder_cached_across_calls(self, mock_st_class):
        """get_encoder() called twice with the same model should only construct once."""
        if os.environ.get("STORYTELLER_DUMMY_EMBEDDINGS", "").strip().lower() in ("1", "true", "yes"):
            self.skipTest("Dummy embeddings enabled; SentenceTransformer caching not exercised.")
        # Patch the import inside get_encoder
        mock_instance = MagicMock()
        mock_st_class.return_value = mock_instance

        with patch.dict("sys.modules", {"sentence_transformers": MagicMock(SentenceTransformer=mock_st_class)}):
            enc1 = get_encoder("test-model")
            enc2 = get_encoder("test-model")

        self.assertIs(enc1, enc2, "Should return the same cached instance")
        # The factory (SentenceTransformer) should only be called once
        mock_st_class.assert_called_once_with("test-model")

    @patch("backend.app.rag._cache.SentenceTransformer", create=True)
    def test_different_models_get_separate_instances(self, mock_st_class):
        """Different model names get separate cached instances."""
        if os.environ.get("STORYTELLER_DUMMY_EMBEDDINGS", "").strip().lower() in ("1", "true", "yes"):
            self.skipTest("Dummy embeddings enabled; SentenceTransformer caching not exercised.")
        mock_a = MagicMock()
        mock_b = MagicMock()
        mock_st_class.side_effect = [mock_a, mock_b]

        with patch.dict("sys.modules", {"sentence_transformers": MagicMock(SentenceTransformer=mock_st_class)}):
            enc_a = get_encoder("model-a")
            enc_b = get_encoder("model-b")

        self.assertIsNot(enc_a, enc_b)
        self.assertEqual(mock_st_class.call_count, 2)
