"""Test that AgentLLM only supports ollama provider."""
import unittest

from backend.app.core.agents.base import AgentLLM


class TestAgentLLMOllamaOnly(unittest.TestCase):
    """AgentLLM should only support ollama provider."""

    def test_ollama_provider_accepted(self):
        """Creating AgentLLM with a role that defaults to ollama should work."""
        llm = AgentLLM("director")
        self.assertEqual(llm._config["provider"], "ollama")

    def test_unknown_provider_raises(self):
        """If config has a non-ollama provider, _get_client should raise NotImplementedError."""
        llm = AgentLLM("director")
        llm._config["provider"] = "openai_compat"
        with self.assertRaises(NotImplementedError) as ctx:
            llm._get_client()
        self.assertIn("ollama", str(ctx.exception).lower())

    def test_unknown_role_raises(self):
        """Unknown role should raise ValueError at init."""
        with self.assertRaises(ValueError):
            AgentLLM("nonexistent_role")
