"""Role-based LLM wrapper: Ollama-only.

AgentLLM(role) returns a client with .complete(system_prompt, user_prompt, json_mode=False, raw_json_mode=False).
If json_mode=True: enforce JSON-only response and validate parse; retry once on invalid.
If raw_json_mode=True: skip internal JSON validation/retry and return raw output.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Iterator, Protocol

from backend.app.config import MODEL_CONFIG
from backend.app.core.json_repair import ensure_json  # noqa: F401 — re-exported


class LLMProvider(Protocol):
    def generate(self, system_prompt: str, user_prompt: str) -> str: ...

logger = logging.getLogger(__name__)


class LLMResult(str):
    """String result with optional metadata for warnings and repairs."""

    def __new__(cls, value: str, warnings: list[str] | None = None, repaired: bool = False):
        obj = str.__new__(cls, value)
        obj.warnings = warnings or []
        obj.repaired = repaired
        return obj


class AgentLLM:
    """Role-based LLM: reads MODEL_CONFIG[role]. Supports multiple providers via llm_provider.

    V3.0: Supports ollama (default), anthropic, openai, and openai_compat providers.
    One client per call to avoid VRAM overload (for local models).
    """

    def __init__(self, role: str) -> None:
        if role not in MODEL_CONFIG:
            raise ValueError(f"Unknown role: {role}. Known: {list(MODEL_CONFIG)}")
        self._role = role
        self._config = dict(MODEL_CONFIG[role])
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy client factory — provider is config-driven (env-overridable per role).

        V3.0: Supports ollama, anthropic, openai, and openai_compat providers
        via the unified create_provider() factory.
        """
        if self._client is not None:
            return self._client
        provider = self._config.get("provider", "ollama")
        model = self._config.get("model", "")
        base_url = self._config.get("base_url", "")
        api_key = self._config.get("api_key", "")
        from backend.app.core.llm_provider import create_provider
        self._client = create_provider(provider, model, base_url, api_key)
        return self._client

    def _call_provider(self, client: Any, user_prompt: str, system_prompt: str, json_mode: bool = False) -> str:
        """Call the provider using its native interface.

        Ollama uses _call_llm(); cloud providers use complete().
        """
        if hasattr(client, "_call_llm"):
            # Ollama LLMClient
            return client._call_llm(user_prompt, system_prompt, json_mode=json_mode)
        elif hasattr(client, "complete"):
            # Cloud providers (AnthropicClient, OpenAICompatClient)
            return client.complete(user_prompt, system_prompt, json_mode=json_mode)
        else:
            raise TypeError(f"Provider {type(client).__name__} has no complete or _call_llm method")

    def _stream_provider(self, client: Any, user_prompt: str, system_prompt: str) -> Iterator[str]:
        """Stream from the provider using its native interface."""
        if hasattr(client, "_call_llm_stream"):
            yield from client._call_llm_stream(user_prompt, system_prompt)
        elif hasattr(client, "complete_stream"):
            yield from client.complete_stream(user_prompt, system_prompt)
        else:
            raise TypeError(f"Provider {type(client).__name__} has no streaming method")

    def _try_fallback_client(self) -> Any | None:
        """Create a fallback client if configured. Returns None if not available."""
        fallback_provider = self._config.get("fallback_provider")
        fallback_model = self._config.get("fallback_model")
        if not fallback_provider:
            return None
        try:
            from backend.app.core.llm_provider import create_provider
            return create_provider(
                fallback_provider,
                fallback_model or self._config.get("model", ""),
                self._config.get("base_url", ""),
            )
        except Exception as e:
            logger.warning("AgentLLM %s: fallback provider init failed: %s", self._role, e)
            return None

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
        raw_json_mode: bool = False,
    ) -> str:
        """
        Call the LLM; return raw response text.
        If json_mode=True: request JSON-only, validate parse, retry once on invalid.
        If raw_json_mode=True: skip internal JSON validation/retry and return raw output.

        V3.0: Falls back to fallback_provider if primary fails.
        """
        try:
            client = self._get_client()
        except Exception as e:
            logger.exception("AgentLLM %s: failed to initialize provider", self._role)
            raise

        try:
            raw = self._call_provider(client, user_prompt, system_prompt, json_mode=json_mode)
        except Exception as e:
            # V3.0: Try fallback provider before giving up
            fallback = self._try_fallback_client()
            if fallback:
                logger.warning("AgentLLM %s: primary failed, trying fallback provider", self._role)
                try:
                    raw = self._call_provider(fallback, user_prompt, system_prompt, json_mode=json_mode)
                except Exception as e2:
                    logger.exception("AgentLLM %s: fallback provider also failed", self._role)
                    raise e2
            else:
                logger.exception("AgentLLM %s: LLM call failed", self._role)
                raise

        if not json_mode or raw_json_mode:
            return LLMResult(raw)

        # Validate JSON; retry once with correction prompt
        parsed = ensure_json(raw)
        if parsed:
            try:
                json.loads(parsed)
                return LLMResult(parsed)
            except json.JSONDecodeError:
                pass
        logger.warning("AgentLLM %s: invalid JSON, retrying once.", self._role)
        warnings: list[str] = ["LLM JSON parse failed: repaired output used."]
        correction = (
            "Your previous response was not valid JSON. Output ONLY a single valid JSON object, no markdown or extra text."
        )
        try:
            raw2 = self._call_provider(client, user_prompt + "\n\n" + correction, system_prompt, json_mode=True)
        except Exception as e:
            logger.exception("AgentLLM %s: LLM call failed on JSON repair", self._role)
            raise
        out = ensure_json(raw2)
        if out:
            try:
                json.loads(out)
                return LLMResult(out, warnings=warnings, repaired=True)
            except json.JSONDecodeError:
                pass
        raise ValueError(
            f"Invalid JSON from LLM role={self._role} after retry. "
            f"Raw (truncated): {raw2[:200]}"
        )

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Alias for .complete(system_prompt, user_prompt, json_mode=False)."""
        return self.complete(system_prompt, user_prompt, json_mode=False)

    def complete_stream(self, system_prompt: str, user_prompt: str) -> Iterator[str]:
        """Stream tokens from LLM. Yields individual token strings.

        V2.8: Used by NarratorAgent.generate_stream() for SSE narration.
        V3.0: Supports streaming from all provider types.
        """
        try:
            client = self._get_client()
        except Exception as e:
            logger.exception("AgentLLM %s: failed to initialize provider for streaming", self._role)
            raise

        try:
            yield from self._stream_provider(client, user_prompt, system_prompt)
        except Exception as e:
            logger.exception("AgentLLM %s: streaming LLM call failed", self._role)
            raise


# Backward compat
def now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
