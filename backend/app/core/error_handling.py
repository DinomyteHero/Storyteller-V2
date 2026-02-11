"""Error handling utilities: structured logging and error responses."""
from __future__ import annotations

import logging
import traceback
from typing import Any

logger = logging.getLogger(__name__)


def log_error_with_context(
    error: Exception,
    node_name: str,
    campaign_id: str | None = None,
    turn_number: int | None = None,
    agent_name: str | None = None,
    extra_context: dict[str, Any] | None = None,
) -> None:
    """
    Log an error with full context: campaign_id, turn_number, node/agent name, and stack trace.
    
    Args:
        error: The exception that occurred
        node_name: Name of the graph node (e.g., 'narrator', 'architect', 'world_sim')
        campaign_id: Campaign ID for context
        turn_number: Turn number for context
        agent_name: Agent class/method name (e.g., 'NarratorAgent.generate')
        extra_context: Additional context dict to include in log
    """
    context_parts = []
    if campaign_id:
        context_parts.append(f"campaign_id={campaign_id}")
    if turn_number is not None:
        context_parts.append(f"turn_number={turn_number}")
    if agent_name:
        context_parts.append(f"agent={agent_name}")
    context_str = ", ".join(context_parts) if context_parts else "no context"
    
    extra = {}
    if extra_context:
        extra.update(extra_context)
    if campaign_id:
        extra["campaign_id"] = campaign_id
    if turn_number is not None:
        extra["turn_number"] = turn_number
    if agent_name:
        extra["agent_name"] = agent_name
    extra["node_name"] = node_name
    
    logger.error(
        f"[{node_name}] Error: {type(error).__name__}: {str(error)} ({context_str})",
        exc_info=True,
        extra=extra,
    )


def create_error_response(
    error_code: str,
    message: str,
    node: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create a structured error response for API endpoints.
    
    Args:
        error_code: Error code (e.g., 'NARRATOR_LLM_FAILED', 'ARCHITECT_JSON_INVALID')
        message: Human-readable error message
        node: Graph node where error occurred
        details: Additional error details
        
    Returns:
        Structured error dict
    """
    response: dict[str, Any] = {
        "error_code": error_code,
        "message": message,
    }
    if node:
        response["node"] = node
    if details:
        response["details"] = details
    return response
