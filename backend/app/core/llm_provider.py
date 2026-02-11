"""LLM provider abstraction: unified interface for Ollama, Anthropic, and OpenAI-compatible backends.

Each provider implements the LLMProviderProtocol. AgentLLM._get_client() dispatches
to the correct provider based on per-role configuration.

V3.0: Hybrid model support — local for speed, cloud for quality.
"""
from __future__ import annotations

import json as _json
import logging
import os
from typing import Any, Dict, Iterator, Optional, Protocol, runtime_checkable

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", os.environ.get("OLLAMA_TIMEOUT", "300")))


class LLMProviderError(Exception):
    """Raised when an LLM request fails."""


@runtime_checkable
class LLMProviderProtocol(Protocol):
    """Unified interface for LLM providers."""

    def complete(self, prompt: str, system_prompt: Optional[str] = None, json_mode: bool = False) -> str:
        """Generate a completion. Returns raw response text."""
        ...

    def complete_stream(self, prompt: str, system_prompt: Optional[str] = None) -> Iterator[str]:
        """Stream tokens. Yields individual token strings."""
        ...


class AnthropicClient:
    """Client for Anthropic's Messages API (Claude models).

    Requires ANTHROPIC_API_KEY environment variable or api_key parameter.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-5-20250929",
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 4096,
    ):
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.base_url = (base_url or "https://api.anthropic.com").rstrip("/")
        self.max_tokens = max_tokens
        self.client = httpx.Client(timeout=_DEFAULT_TIMEOUT)

    def close(self) -> None:
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def complete(self, prompt: str, system_prompt: Optional[str] = None, json_mode: bool = False) -> str:
        """Call Anthropic Messages API."""
        if not self.api_key:
            raise LLMProviderError("ANTHROPIC_API_KEY not set")

        messages = [{"role": "user", "content": prompt}]
        payload: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }
        if system_prompt:
            payload["system"] = system_prompt

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        try:
            response = self.client.post(
                f"{self.base_url}/v1/messages",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise LLMProviderError(f"Anthropic request timed out") from exc
        except httpx.ConnectError as exc:
            raise LLMProviderError(f"Cannot connect to Anthropic API at {self.base_url}") from exc
        except httpx.HTTPStatusError as exc:
            raise LLMProviderError(
                f"Anthropic HTTP error {exc.response.status_code}: {exc.response.text[:500]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"Anthropic network error: {exc}") from exc

        try:
            body = response.json()
        except _json.JSONDecodeError as exc:
            raise LLMProviderError("Anthropic returned non-JSON response") from exc

        # Extract text from content blocks
        content = body.get("content", [])
        text_parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))
        return "".join(text_parts)

    def complete_stream(self, prompt: str, system_prompt: Optional[str] = None) -> Iterator[str]:
        """Stream tokens from Anthropic SSE API."""
        if not self.api_key:
            raise LLMProviderError("ANTHROPIC_API_KEY not set")

        messages = [{"role": "user", "content": prompt}]
        payload: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
            "stream": True,
        }
        if system_prompt:
            payload["system"] = system_prompt

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        try:
            with self.client.stream(
                "POST",
                f"{self.base_url}/v1/messages",
                json=payload,
                headers=headers,
                timeout=_DEFAULT_TIMEOUT,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]  # Strip "data: " prefix
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        data = _json.loads(data_str)
                    except _json.JSONDecodeError:
                        continue
                    if data.get("type") == "content_block_delta":
                        delta = data.get("delta", {})
                        if delta.get("type") == "text_delta":
                            text = delta.get("text", "")
                            if text:
                                yield text
                    elif data.get("type") == "message_stop":
                        break
        except httpx.TimeoutException as exc:
            raise LLMProviderError("Anthropic stream timed out") from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"Anthropic stream error: {exc}") from exc


class OpenAICompatClient:
    """Client for OpenAI-compatible APIs (OpenAI, local servers, etc.).

    Requires OPENAI_API_KEY environment variable or api_key parameter.
    Works with any OpenAI-compatible endpoint (OpenRouter, Together, vLLM, etc.).
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 4096,
    ):
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = (base_url or "https://api.openai.com").rstrip("/")
        self.max_tokens = max_tokens
        self.client = httpx.Client(timeout=_DEFAULT_TIMEOUT)

    def close(self) -> None:
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def complete(self, prompt: str, system_prompt: Optional[str] = None, json_mode: bool = False) -> str:
        """Call OpenAI-compatible chat completions API."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers: Dict[str, str] = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"

        try:
            response = self.client.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise LLMProviderError("OpenAI-compatible request timed out") from exc
        except httpx.ConnectError as exc:
            raise LLMProviderError(f"Cannot connect to OpenAI-compatible API at {self.base_url}") from exc
        except httpx.HTTPStatusError as exc:
            raise LLMProviderError(
                f"OpenAI-compatible HTTP error {exc.response.status_code}: {exc.response.text[:500]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"OpenAI-compatible network error: {exc}") from exc

        try:
            body = response.json()
        except _json.JSONDecodeError as exc:
            raise LLMProviderError("OpenAI-compatible returned non-JSON response") from exc

        choices = body.get("choices", [])
        if not choices:
            return ""
        return choices[0].get("message", {}).get("content", "")

    def complete_stream(self, prompt: str, system_prompt: Optional[str] = None) -> Iterator[str]:
        """Stream tokens from OpenAI-compatible SSE API."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "stream": True,
        }

        headers: Dict[str, str] = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"

        try:
            with self.client.stream(
                "POST",
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=_DEFAULT_TIMEOUT,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        data = _json.loads(data_str)
                    except _json.JSONDecodeError:
                        continue
                    choices = data.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
        except httpx.TimeoutException as exc:
            raise LLMProviderError("OpenAI-compatible stream timed out") from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"OpenAI-compatible stream error: {exc}") from exc


def create_provider(
    provider: str,
    model: str,
    base_url: str = "",
    api_key: str = "",
) -> Any:
    """Factory: create an LLM provider client by name.

    Supported providers: 'ollama', 'anthropic', 'openai', 'openai_compat'.
    """
    if provider == "ollama":
        from backend.llm_client import LLMClient
        return LLMClient(base_url=base_url or None, model=model)
    elif provider == "anthropic":
        return AnthropicClient(
            model=model,
            api_key=api_key or None,
            base_url=base_url or None,
        )
    elif provider in ("openai", "openai_compat"):
        return OpenAICompatClient(
            model=model,
            api_key=api_key or None,
            base_url=base_url or None,
        )
    else:
        raise NotImplementedError(
            f"Provider '{provider}' not supported. Supported: ollama, anthropic, openai, openai_compat."
        )
