"""Cloud provider health probe — checks reachability of configured cloud LLM providers at startup.

Runs once at app startup. Logs warnings if cloud providers are configured but unreachable.
Does NOT auto-switch providers (design decision: no silent fallbacks).
"""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

# Anthropic API health endpoint (lightweight models list)
_ANTHROPIC_HEALTH_URL = "https://api.anthropic.com/v1/models"
_PROBE_TIMEOUT = 5.0


def check_cloud_providers() -> dict[str, bool]:
    """Probe configured cloud providers and return reachability status.

    Returns a dict like {"anthropic": True, "openai": False}.
    Only checks providers that are actually configured for at least one role.
    """
    from backend.app.config import MODEL_CONFIG

    # Collect unique cloud providers in use
    cloud_providers: set[str] = set()
    for cfg in MODEL_CONFIG.values():
        provider = cfg.get("provider", "")
        if provider and provider != "ollama":
            cloud_providers.add(provider)

    if not cloud_providers:
        logger.info("No cloud LLM providers configured — all roles using local Ollama.")
        return {}

    results: dict[str, bool] = {}
    for provider in sorted(cloud_providers):
        reachable = _probe_provider(provider)
        results[provider] = reachable
        if reachable:
            logger.info("Cloud provider '%s' is reachable.", provider)
        else:
            # Log cloud roles that will be affected
            affected_roles = [
                role for role, cfg in MODEL_CONFIG.items()
                if cfg.get("provider") == provider
            ]
            logger.warning(
                "Cloud provider '%s' is UNREACHABLE. Affected roles: %s. "
                "These roles will fail until the provider is available.",
                provider,
                ", ".join(affected_roles),
            )

    return results


def _probe_provider(provider: str) -> bool:
    """Check if a cloud provider's API endpoint is reachable."""
    if provider == "anthropic":
        return _probe_anthropic()
    elif provider in ("openai", "openai_compat"):
        return _probe_openai()
    else:
        logger.debug("No health probe defined for provider '%s', skipping.", provider)
        return True  # Assume reachable for unknown providers


def _probe_anthropic() -> bool:
    """Check Anthropic API reachability with a lightweight request."""
    import os
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        logger.warning(
            "ANTHROPIC_API_KEY not set but Anthropic provider is configured. "
            "Cloud LLM calls will fail."
        )
        return False
    try:
        resp = httpx.get(
            _ANTHROPIC_HEALTH_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            timeout=_PROBE_TIMEOUT,
        )
        return resp.status_code in (200, 401, 403)  # Any response means reachable
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


def _probe_openai() -> bool:
    """Check OpenAI API reachability."""
    import os
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        logger.warning(
            "OPENAI_API_KEY not set but OpenAI provider is configured. "
            "Cloud LLM calls will fail."
        )
        return False
    try:
        resp = httpx.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=_PROBE_TIMEOUT,
        )
        return resp.status_code in (200, 401, 403)
    except (httpx.ConnectError, httpx.TimeoutException):
        return False
