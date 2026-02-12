"""LLM client for Ollama-compatible endpoints (Ollama /api/generate)."""

import json as _json
import os
import httpx
import logging
from typing import Any, Dict, Iterator, Optional

logger = logging.getLogger(__name__)

# Ollama can be slow on large prompts; default 5 minutes, configurable via env
_LLM_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "300"))


class LLMClientError(Exception):
    """Raised when an LLM request fails after exhausting retries."""


class LLMClient:
    """Client for interacting with Ollama-compatible LLM endpoints."""

    def __init__(self, base_url: str | None = None, model: Optional[str] = None, timeout: float | None = None):
        base_url = (base_url or "http://localhost:11434").strip()
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._timeout = timeout or _LLM_TIMEOUT
        self.client = httpx.Client(timeout=self._timeout)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying HTTP client (optional, for clean shutdown)."""
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    # ------------------------------------------------------------------
    # Model auto-detection
    # ------------------------------------------------------------------

    def _ensure_model(self) -> None:
        if self.model:
            return
        try:
            resp = self.client.get(f"{self.base_url}/api/tags")
            if resp.status_code != 200:
                raise ValueError("Could not fetch models")
            models = resp.json().get("models", [])
            if not models:
                raise ValueError("No models available")
            self.model = models[0]["name"]
            logger.info("Auto-detected model: %s", self.model)
        except Exception as e:
            logger.error("Failed to auto-detect model: %s", e)
            raise ValueError("Model not specified and auto-detection failed") from e

    # ------------------------------------------------------------------
    # Core LLM call with error handling
    # ------------------------------------------------------------------

    def _call_llm(self, prompt: str, system_prompt: Optional[str] = None, json_mode: bool = False) -> str:
        """Call the LLM; return raw response text.

        If json_mode is True, passes ``format: "json"`` to Ollama so the
        model is constrained to emit valid JSON.

        Raises :class:`LLMClientError` on unrecoverable failures so that
        calling agents can fall back to deterministic behaviour.
        """
        self._ensure_model()
        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        if system_prompt:
            payload["system"] = system_prompt
        if json_mode:
            payload["format"] = "json"

        try:
            response = self.client.post(f"{self.base_url}/api/generate", json=payload)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            logger.error("LLM request timed out (model=%s): %s", self.model, exc)
            raise LLMClientError(
                f"LLM request timed out after {self.client.timeout.read}s"
            ) from exc
        except httpx.ConnectError as exc:
            logger.error(
                "Cannot connect to Ollama at %s – is the server running? %s",
                self.base_url, exc,
            )
            raise LLMClientError(
                f"Cannot connect to Ollama at {self.base_url} – is the server running?"
            ) from exc
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Ollama returned HTTP %d: %s",
                exc.response.status_code,
                exc.response.text[:500],
            )
            raise LLMClientError(
                f"Ollama HTTP error {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            # Catch-all for any other httpx transport/protocol errors
            logger.error("LLM network error: %s", exc)
            raise LLMClientError(f"LLM network error: {exc}") from exc

        try:
            body = response.json()
        except _json.JSONDecodeError as exc:
            logger.error(
                "Ollama response was not valid JSON (status %d, first 500 chars): %s",
                response.status_code,
                response.text[:500],
            )
            raise LLMClientError("Ollama returned non-JSON response") from exc

        return body.get("response", "")

    # ------------------------------------------------------------------
    # Streaming LLM call (V2.8)
    # ------------------------------------------------------------------

    def _call_llm_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> Iterator[str]:
        """Stream tokens from Ollama. Yields individual token strings.

        Uses httpx streaming to read NDJSON lines incrementally.
        Each line is a JSON object with a ``response`` field containing
        the next token(s).

        Raises :class:`LLMClientError` on connection failures.
        """
        self._ensure_model()
        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            with self.client.stream(
                "POST",
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=_LLM_TIMEOUT,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    try:
                        data = _json.loads(line)
                    except _json.JSONDecodeError:
                        continue
                    token = data.get("response", "")
                    if token:
                        yield token
                    if data.get("done", False):
                        break
        except httpx.TimeoutException as exc:
            logger.error("LLM stream timed out (model=%s): %s", self.model, exc)
            raise LLMClientError(
                f"LLM stream timed out after {_LLM_TIMEOUT}s"
            ) from exc
        except httpx.ConnectError as exc:
            logger.error(
                "Cannot connect to Ollama at %s for streaming: %s",
                self.base_url, exc,
            )
            raise LLMClientError(
                f"Cannot connect to Ollama at {self.base_url}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Ollama stream returned HTTP %d",
                exc.response.status_code,
            )
            raise LLMClientError(
                f"Ollama stream HTTP error {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            logger.error("LLM stream network error: %s", exc)
            raise LLMClientError(f"LLM stream network error: {exc}") from exc
