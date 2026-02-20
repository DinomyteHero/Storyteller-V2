"""Role-based LLM wrapper: Ollama-only.

AgentLLM(role) returns a client with .complete(system_prompt, user_prompt, json_mode=False, raw_json_mode=False).
If json_mode=True: enforce JSON-only response and validate parse; retry once on invalid.
If raw_json_mode=True: skip internal JSON validation/retry and return raw output.
"""
from __future__ import annotations

import json
import logging
import time
from contextvars import ContextVar
from typing import Any, Iterator, Protocol

from backend.app.config import MODEL_CONFIG
from backend.app.core.json_repair import ensure_json  # noqa: F401 — re-exported


class LLMProvider(Protocol):
    def generate(self, system_prompt: str, user_prompt: str) -> str: ...

logger = logging.getLogger(__name__)
_LLM_TIMINGS: ContextVar[dict[str, list[float]]] = ContextVar("llm_timings", default={})
_LLM_TOKENS: ContextVar[dict[str, list[dict[str, int]]]] = ContextVar("llm_tokens", default={})


def reset_llm_timings() -> None:
    """Reset per-turn LLM timing collection."""
    _LLM_TIMINGS.set({})


def get_llm_timings() -> dict[str, Any]:
    """Return summarized LLM timings collected for the current turn."""
    raw = _LLM_TIMINGS.get() or {}
    summary: dict[str, Any] = {}
    for role, samples in raw.items():
        if not samples:
            continue
        summary[role] = {
            "count": len(samples),
            "total_s": round(sum(samples), 3),
            "max_s": round(max(samples), 3),
            "avg_s": round(sum(samples) / len(samples), 3),
        }
    return summary


def _record_llm_timing(role: str, elapsed: float) -> None:
    data = dict(_LLM_TIMINGS.get() or {})
    samples = list(data.get(role) or [])
    samples.append(elapsed)
    data[role] = samples
    _LLM_TIMINGS.set(data)


def reset_llm_tokens() -> None:
    """Reset per-turn LLM token usage collection."""
    _LLM_TOKENS.set({})


def get_llm_token_usage() -> dict[str, Any]:
    """Return summarized LLM token usage collected for the current turn."""
    raw = _LLM_TOKENS.get() or {}
    summary: dict[str, Any] = {}
    for role, samples in raw.items():
        if not samples:
            continue
        total_input = sum(s.get("input_tokens", 0) for s in samples)
        total_output = sum(s.get("output_tokens", 0) for s in samples)
        summary[role] = {
            "calls": len(samples),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
        }
    return summary


def _record_llm_tokens(role: str, input_tokens: int, output_tokens: int) -> None:
    data = dict(_LLM_TOKENS.get() or {})
    samples = list(data.get(role) or [])
    samples.append({"input_tokens": input_tokens, "output_tokens": output_tokens})
    data[role] = samples
    _LLM_TOKENS.set(data)


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

    def _call_provider_timed(
        self,
        client: Any,
        user_prompt: str,
        system_prompt: str,
        json_mode: bool = False,
        call_label: str = "",
    ) -> str:
        start = time.perf_counter()
        try:
            return self._call_provider(client, user_prompt, system_prompt, json_mode=json_mode)
        finally:
            elapsed = time.perf_counter() - start
            _record_llm_timing(self._role, elapsed)
            from backend.app.core.llm_provider import get_last_token_counts
            token_counts = get_last_token_counts()
            _record_llm_tokens(self._role, token_counts.get("input", 0), token_counts.get("output", 0))
            label = f" [{call_label}]" if call_label else ""
            logger.info("LLM call [%s]%s completed in %.2fs", self._role, label, elapsed)

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
        except Exception:
            logger.exception("AgentLLM %s: failed to initialize provider", self._role)
            raise

        try:
            raw = self._call_provider_timed(
                client,
                user_prompt,
                system_prompt,
                json_mode=json_mode,
                call_label="primary",
            )
        except Exception:
            # V3.0: Try fallback provider before giving up
            fallback = self._try_fallback_client()
            if fallback:
                logger.warning("AgentLLM %s: primary failed, trying fallback provider", self._role)
                try:
                    raw = self._call_provider_timed(
                        fallback,
                        user_prompt,
                        system_prompt,
                        json_mode=json_mode,
                        call_label="fallback",
                    )
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
            raw2 = self._call_provider_timed(
                client,
                user_prompt + "\n\n" + correction,
                system_prompt,
                json_mode=True,
                call_label="json_repair",
            )
        except Exception:
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
        except Exception:
            logger.exception("AgentLLM %s: failed to initialize provider for streaming", self._role)
            raise

        try:
            start = time.perf_counter()
            try:
                yield from self._stream_provider(client, user_prompt, system_prompt)
            finally:
                elapsed = time.perf_counter() - start
                _record_llm_timing(self._role, elapsed)
                logger.info("LLM stream [%s] completed in %.2fs", self._role, elapsed)
        except Exception:
            logger.exception("AgentLLM %s: streaming LLM call failed", self._role)
            raise


# Backward compat
def now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
