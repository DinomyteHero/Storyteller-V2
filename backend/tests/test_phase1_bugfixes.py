"""Phase 1 bug fix tests: NULL reference, empty LLM response, StopIteration,
case-preserving regex, intent_router timeout.

Covers:
  1.1 — NULL legacy_era_id in campaign_setup
  1.2 — intent_router timeout default (15s)
  1.3 — Empty response detection in AnthropicClient and OpenAICompatClient
  1.4a — StopIteration crash in test_provider with empty models
  1.5 — Case-preserving regex replacements in narrative_validator
"""
import os
import re
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import httpx

# ---------------------------------------------------------------------------
# 1.1 — NULL legacy_era_id in campaign_setup
# ---------------------------------------------------------------------------


class TestNullLegacyEraId(unittest.TestCase):
    """Verify _resolve_requested_period handles None legacy_era_id."""

    def _make_catalog_item(self, setting_id, period_id, legacy_era_id=None):
        return {
            "setting_id": setting_id,
            "period_id": period_id,
            "legacy_era_id": legacy_era_id,
        }

    @patch("backend.app.api.campaign_setup._catalog_items")
    def test_none_legacy_era_id_does_not_crash(self, mock_catalog):
        """Item with legacy_era_id=None should not throw AttributeError."""
        from backend.app.api.campaign_setup import _resolve_requested_period

        mock_catalog.return_value = [
            self._make_catalog_item("star_wars_legends", "rebellion", None),
        ]
        # Should match on period_id, not crash on None.strip()
        result = _resolve_requested_period(
            setting_id=None, period_id=None, time_period="rebellion"
        )
        self.assertEqual(result[1], "rebellion")

    @patch("backend.app.api.campaign_setup._catalog_items")
    def test_empty_string_legacy_era_id(self, mock_catalog):
        """Item with legacy_era_id='' should work fine."""
        from backend.app.api.campaign_setup import _resolve_requested_period

        mock_catalog.return_value = [
            self._make_catalog_item("star_wars_legends", "rebellion", ""),
        ]
        result = _resolve_requested_period(
            setting_id=None, period_id=None, time_period="rebellion"
        )
        self.assertEqual(result[1], "rebellion")

    @patch("backend.app.api.campaign_setup._catalog_items")
    def test_legacy_era_id_match(self, mock_catalog):
        """Item matched via legacy_era_id should return correctly."""
        from backend.app.api.campaign_setup import _resolve_requested_period

        mock_catalog.return_value = [
            self._make_catalog_item("star_wars_legends", "rebellion", "LOTF"),
        ]
        result = _resolve_requested_period(
            setting_id=None, period_id=None, time_period="lotf"
        )
        self.assertEqual(result[0], "star_wars_legends")
        self.assertEqual(result[1], "rebellion")
        self.assertEqual(result[2], "LOTF")


# ---------------------------------------------------------------------------
# 1.2 — intent_router timeout default
# ---------------------------------------------------------------------------


class TestIntentRouterTimeout(unittest.TestCase):
    """Verify intent_router role gets a short timeout (15s), not the default 300s."""

    def test_intent_router_timeout_is_15s(self):
        from backend.app.config import get_role_timeout

        timeout = get_role_timeout("intent_router")
        self.assertEqual(timeout, 15.0)

    def test_narrator_timeout_is_120s(self):
        from backend.app.config import get_role_timeout

        timeout = get_role_timeout("narrator")
        self.assertEqual(timeout, 120.0)

    def test_unknown_role_defaults_to_300s(self):
        from backend.app.config import get_role_timeout

        timeout = get_role_timeout("some_unknown_role")
        self.assertEqual(timeout, 300.0)

    def test_choice_crafter_timeout_is_60s(self):
        from backend.app.config import get_role_timeout

        timeout = get_role_timeout("choice_crafter")
        self.assertEqual(timeout, 60.0)


# ---------------------------------------------------------------------------
# 1.3 — Empty LLM response detection
# ---------------------------------------------------------------------------


class TestAnthropicEmptyResponse(unittest.TestCase):
    """AnthropicClient.complete() should raise on empty response."""

    def _make_client(self):
        from backend.app.core.llm_provider import AnthropicClient

        return AnthropicClient(
            model="test-model",
            api_key="test-key",
            base_url="http://localhost:9999",
        )

    @patch("httpx.Client.post")
    def test_empty_content_raises(self, mock_post):
        from backend.app.core.llm_provider import LLMProviderError

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "content": [],
            "usage": {"input_tokens": 10, "output_tokens": 0},
        }
        mock_post.return_value = mock_response

        client = self._make_client()
        with self.assertRaises(LLMProviderError) as ctx:
            client.complete("test prompt")
        self.assertIn("empty response", str(ctx.exception).lower())

    @patch("httpx.Client.post")
    def test_whitespace_only_content_raises(self, mock_post):
        from backend.app.core.llm_provider import LLMProviderError

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "content": [{"type": "text", "text": "   \n  "}],
            "usage": {"input_tokens": 10, "output_tokens": 1},
        }
        mock_post.return_value = mock_response

        client = self._make_client()
        with self.assertRaises(LLMProviderError):
            client.complete("test prompt")

    @patch("httpx.Client.post")
    def test_valid_response_succeeds(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "content": [{"type": "text", "text": "Hello!"}],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        mock_post.return_value = mock_response

        client = self._make_client()
        result = client.complete("test prompt")
        self.assertEqual(result, "Hello!")


class TestOpenAICompatEmptyResponse(unittest.TestCase):
    """OpenAICompatClient.complete() should raise on empty response."""

    def _make_client(self):
        from backend.app.core.llm_provider import OpenAICompatClient

        return OpenAICompatClient(
            model="test-model",
            api_key="test-key",
            base_url="http://localhost:9999",
        )

    @patch("httpx.Client.post")
    def test_empty_choices_raises(self, mock_post):
        from backend.app.core.llm_provider import LLMProviderError

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [],
            "usage": {"prompt_tokens": 10, "completion_tokens": 0},
        }
        mock_post.return_value = mock_response

        client = self._make_client()
        with self.assertRaises(LLMProviderError) as ctx:
            client.complete("test prompt")
        self.assertIn("empty choices", str(ctx.exception).lower())

    @patch("httpx.Client.post")
    def test_empty_content_in_choice_raises(self, mock_post):
        from backend.app.core.llm_provider import LLMProviderError

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": ""}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 0},
        }
        mock_post.return_value = mock_response

        client = self._make_client()
        with self.assertRaises(LLMProviderError) as ctx:
            client.complete("test prompt")
        self.assertIn("empty response content", str(ctx.exception).lower())

    @patch("httpx.Client.post")
    def test_null_content_in_choice_raises(self, mock_post):
        from backend.app.core.llm_provider import LLMProviderError

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": None}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 0},
        }
        mock_post.return_value = mock_response

        client = self._make_client()
        with self.assertRaises(LLMProviderError):
            client.complete("test prompt")

    @patch("httpx.Client.post")
    def test_valid_response_succeeds(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello!"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        mock_post.return_value = mock_response

        client = self._make_client()
        result = client.complete("test prompt")
        self.assertEqual(result, "Hello!")


# ---------------------------------------------------------------------------
# 1.4b — StopIteration in test_provider with empty models
# ---------------------------------------------------------------------------


class TestProviderEmptyModels(unittest.TestCase):
    """test_provider() should return error, not crash, when models dict is empty."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name
        from backend.app.db.migrate import apply_schema
        apply_schema(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_empty_models_returns_error(self):
        """Provider with no models should return ok=False, not StopIteration."""
        from backend.app.api.v2_settings import test_provider, TestResult

        # Patch CLOUD_PROVIDERS to have a provider with empty models
        empty_provider = {
            "anthropic": {
                "label": "Test",
                "env_var": "TEST_KEY",
                "base_url": "http://localhost",
                "client_type": "anthropic",
                "models": {},
            }
        }
        with patch("backend.app.api.v2_settings.CLOUD_PROVIDERS", empty_provider), \
             patch("backend.app.api.v2_settings.resolve_api_key", return_value="test-key"), \
             patch("backend.app.api.v2_settings._get_conn") as mock_conn:
            mock_conn.return_value = MagicMock()
            mock_conn.return_value.close = MagicMock()
            result = test_provider("anthropic")
            self.assertFalse(result.ok)
            self.assertIn("no models", result.error.lower())


# ---------------------------------------------------------------------------
# 1.5 — Case-preserving regex replacement in narrative_validator
# ---------------------------------------------------------------------------


class TestPreserveCase(unittest.TestCase):
    """_preserve_case correctly matches case of the original word."""

    def test_uppercase_input(self):
        from backend.app.core.nodes.narrative_validator import _preserve_case

        self.assertEqual(_preserve_case("SUCCEEDS", "struggles"), "STRUGGLES")

    def test_title_case_input(self):
        from backend.app.core.nodes.narrative_validator import _preserve_case

        self.assertEqual(_preserve_case("Succeeds", "struggles"), "Struggles")

    def test_lowercase_input(self):
        from backend.app.core.nodes.narrative_validator import _preserve_case

        self.assertEqual(_preserve_case("succeeds", "struggles"), "struggles")

    def test_empty_original(self):
        from backend.app.core.nodes.narrative_validator import _preserve_case

        self.assertEqual(_preserve_case("", "struggles"), "struggles")


class TestCasePreservingRewriter(unittest.TestCase):
    """_rewrite_contradictions preserves case in rewrites."""

    def test_title_case_succeeds_becomes_struggles(self):
        from backend.app.core.nodes.narrative_validator import _rewrite_contradictions

        text = "She succeeds in her attempt."
        corrected, repairs = _rewrite_contradictions(text, success=False)
        self.assertIn("struggles", corrected)
        self.assertNotIn("succeeds", corrected)
        self.assertTrue(len(repairs) > 0)

    def test_uppercase_succeeds_becomes_uppercase_struggles(self):
        from backend.app.core.nodes.narrative_validator import _rewrite_contradictions

        text = "SUCCEEDS against all odds."
        corrected, repairs = _rewrite_contradictions(text, success=False)
        self.assertIn("STRUGGLES", corrected)

    def test_title_case_Succeeds_becomes_Struggles(self):
        from backend.app.core.nodes.narrative_validator import _rewrite_contradictions

        text = "Succeeds in the task."
        corrected, repairs = _rewrite_contradictions(text, success=False)
        self.assertIn("Struggles", corrected)

    def test_failure_to_success_preserves_case(self):
        from backend.app.core.nodes.narrative_validator import _rewrite_contradictions

        text = "He Fails to open the door."
        corrected, repairs = _rewrite_contradictions(text, success=True)
        self.assertIn("Succeeds", corrected)
        self.assertNotIn("Fails", corrected)

    def test_multi_word_replacement_manages_to(self):
        from backend.app.core.nodes.narrative_validator import _rewrite_contradictions

        text = "He manages to dodge the blast."
        corrected, repairs = _rewrite_contradictions(text, success=False)
        self.assertIn("tries to", corrected)
        self.assertNotIn("manages to", corrected)

    def test_title_case_multi_word_manages_to(self):
        from backend.app.core.nodes.narrative_validator import _rewrite_contradictions

        text = "Manages to dodge the blast."
        corrected, repairs = _rewrite_contradictions(text, success=False)
        self.assertIn("Tries to", corrected)

    def test_no_contradiction_returns_unchanged(self):
        from backend.app.core.nodes.narrative_validator import _rewrite_contradictions

        text = "The cantina was dark and quiet."
        corrected, repairs = _rewrite_contradictions(text, success=False)
        self.assertEqual(corrected, text)
        self.assertEqual(len(repairs), 0)

    def test_success_none_returns_unchanged(self):
        """When success is None (no mechanic check), text is unchanged."""
        from backend.app.core.nodes.narrative_validator import _check_mechanic_consistency

        text = "She succeeds brilliantly."
        corrected, warnings, repairs = _check_mechanic_consistency(
            text, {"success": None}
        )
        self.assertEqual(corrected, text)
        self.assertEqual(len(repairs), 0)


if __name__ == "__main__":
    unittest.main()
