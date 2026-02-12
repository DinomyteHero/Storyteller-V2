"""Test AgentLLM provider configuration and multi-provider support."""
import unittest

from backend.app.core.agents.base import AgentLLM


class TestAgentLLMProviders(unittest.TestCase):
    """AgentLLM provider configuration tests."""

    def test_ollama_provider_accepted(self):
        """Creating AgentLLM with a role that defaults to ollama should work."""
        llm = AgentLLM("director")
        self.assertEqual(llm._config["provider"], "ollama")

    def test_unsupported_provider_raises(self):
        """If config has a truly unsupported provider, create_provider should raise NotImplementedError."""
        llm = AgentLLM("director")
        llm._config["provider"] = "totally_fake_provider"
        with self.assertRaises(NotImplementedError):
            llm._get_client()

    def test_supported_cloud_providers_accepted(self):
        """V3.0: cloud providers (anthropic, openai, openai_compat) should be accepted."""
        for provider in ("anthropic", "openai", "openai_compat"):
            llm = AgentLLM("director")
            llm._config["provider"] = provider
            # Should not raise — the client is created, even if it can't connect
            client = llm._get_client()
            self.assertIsNotNone(client)
            llm._client = None  # Reset for next iteration

    def test_unknown_role_raises(self):
        """Unknown role should raise ValueError at init."""
        with self.assertRaises(ValueError):
            AgentLLM("nonexistent_role")
