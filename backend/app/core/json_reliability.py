"""JSON reliability wrapper for LLM calls that must return structured JSON.

Provides validate+retry logic with schema validation and safe fallbacks.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, TypeVar

from backend.app.core.agents.base import AgentLLM, ensure_json
from backend.app.core.warnings import add_warning
from pydantic import BaseModel, ValidationError
from backend.app.constants import JSON_RELIABILITY_MAX_RETRIES

logger = logging.getLogger(__name__)

T = TypeVar("T")


class JSONReliabilityError(Exception):
    """Raised when JSON validation fails after all retries."""

    def __init__(self, role: str, agent_name: str, campaign_id: str | None, reason: str):
        self.role = role
        self.agent_name = agent_name
        self.campaign_id = campaign_id
        self.reason = reason
        super().__init__(f"[{role}:{agent_name}] JSON validation failed: {reason}")


def call_with_json_reliability(
    llm: AgentLLM,
    role: str,
    agent_name: str,
    campaign_id: str | None,
    system_prompt: str,
    user_prompt: str,
    schema_class: type[BaseModel] | None = None,
    validator_fn: Callable[[Any], tuple[bool, str]] | None = None,
    fallback_fn: Callable[[], T] | None = None,
    max_retries: int = JSON_RELIABILITY_MAX_RETRIES,
    warnings: list[str] | None = None,
) -> T:
    """
    Call LLM with JSON reliability: validate+retry logic with schema validation.

    Args:
        llm: AgentLLM instance
        role: Role name (e.g., 'architect', 'biographer')
        agent_name: Agent name for logging (e.g., 'CampaignArchitect', 'BiographerAgent')
        campaign_id: Campaign ID for logging (optional)
        system_prompt: System prompt
        user_prompt: User prompt
        schema_class: Pydantic model class for validation (optional)
        validator_fn: Optional validator (returns (ok, reason)) for additional checks
        fallback_fn: Function to call if all retries fail (must return T)
        max_retries: Maximum number of retry attempts (default JSON_RELIABILITY_MAX_RETRIES)

    Returns:
        Validated JSON data (dict if no schema, or schema_class instance if provided)

    Raises:
        JSONReliabilityError: If all retries fail and no fallback is provided
    """
    role_label = role.capitalize()
    if llm is None:
        if fallback_fn:
            logger.info(f"[{role}:{agent_name}] No LLM available, using fallback")
            add_warning(warnings, f"LLM unavailable: {role_label} used fallback output.")
            return fallback_fn()
        raise JSONReliabilityError(role, agent_name, campaign_id, "No LLM available and no fallback provided")

    last_error: str | None = None
    last_raw: str | None = None
    repaired_warning_emitted = False

    for attempt in range(1, max_retries + 1):
        try:
            # Attempt #1: normal call
            if attempt == 1:
                raw = llm.complete(system_prompt, user_prompt, json_mode=True, raw_json_mode=True)
            # Attempt #2: strict repair prompt
            elif attempt == 2:
                repair_prompt = (
                    "Your previous response was not valid JSON or did not match the required schema. "
                    "Output ONLY valid JSON that matches this schema. No extra text, no markdown, no explanations."
                )
                raw = llm.complete(system_prompt, user_prompt + "\n\n" + repair_prompt, json_mode=True, raw_json_mode=True)
            # Attempt #3: include invalid output and ask to correct
            else:
                invalid_preview = (last_raw or "")[:500] if last_raw else "No response received"
                correction_prompt = (
                    f"Your previous response was invalid:\n{invalid_preview}\n\n"
                    "Please correct it. Output ONLY valid JSON that matches the required schema. No extra text."
                )
                raw = llm.complete(system_prompt, user_prompt + "\n\n" + correction_prompt, json_mode=True, raw_json_mode=True)

            last_raw = raw
            if getattr(raw, "repaired", False) and not repaired_warning_emitted:
                add_warning(warnings, f"{role_label} JSON parse failed: repaired output used.")
                repaired_warning_emitted = True

            # Extract JSON from response
            js = ensure_json(raw)
            if not js:
                last_error = "No valid JSON found in response"
                logger.warning(
                    f"[{role}:{agent_name}] Attempt {attempt} failed: {last_error}"
                    + (f" (campaign_id={campaign_id})" if campaign_id else "")
                )
                continue

            # Parse JSON
            try:
                data = json.loads(js)
            except json.JSONDecodeError as e:
                last_error = f"JSON parse error: {str(e)}"
                logger.warning(
                    f"[{role}:{agent_name}] Attempt {attempt} failed: {last_error}"
                    + (f" (campaign_id={campaign_id})" if campaign_id else "")
                )
                continue

            # Validate schema if provided
            try:
                validated: Any = data
                if schema_class:
                    validated = schema_class.model_validate(data)
                if validator_fn:
                    ok, reason = validator_fn(validated)
                    if not ok:
                        last_error = f"Validator rejected output: {reason}"
                        logger.warning(
                            f"[{role}:{agent_name}] Attempt {attempt} failed: {last_error}"
                            + (f" (campaign_id={campaign_id})" if campaign_id else "")
                        )
                        continue
                if attempt > 1 and not repaired_warning_emitted:
                    add_warning(warnings, f"{role_label} JSON parse failed: repaired output used.")
                    repaired_warning_emitted = True
                logger.info(
                    f"[{role}:{agent_name}] JSON validation succeeded on attempt {attempt}"
                    + (f" (campaign_id={campaign_id})" if campaign_id else "")
                )
                return validated
            except ValidationError as e:
                last_error = f"Schema validation failed: {str(e)}"
                logger.warning(
                    f"[{role}:{agent_name}] Attempt {attempt} failed: {last_error}"
                    + (f" (campaign_id={campaign_id})" if campaign_id else "")
                )
                continue

        except Exception as e:
            last_error = f"LLM call exception: {str(e)}"
            logger.warning(
                f"[{role}:{agent_name}] Attempt {attempt} failed: {last_error}"
                + (f" (campaign_id={campaign_id})" if campaign_id else "")
            )
            if attempt == max_retries:
                logger.exception(f"[{role}:{agent_name}] All retries exhausted")

    # All retries failed
    error_msg = f"All {max_retries} attempts failed. Last error: {last_error}"
    logger.error(
        f"[{role}:{agent_name}] {error_msg}"
        + (f" (campaign_id={campaign_id})" if campaign_id else "")
        + ". Falling back to safe default."
    )

    if fallback_fn:
        logger.info(f"[{role}:{agent_name}] Using fallback function")
        add_warning(warnings, f"LLM error: {role_label} used fallback output.")
        return fallback_fn()

    raise JSONReliabilityError(role, agent_name, campaign_id, error_msg)
