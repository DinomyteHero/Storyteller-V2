"""Consolidated JSON extraction and repair utilities.

Single source of truth for extracting JSON objects from LLM responses
that may be wrapped in markdown fences or contain trailing commas.
"""
from __future__ import annotations

import re


def extract_json_object(text: str) -> str | None:
    """Extract the first complete JSON object from text.

    Handles:
    - Markdown code fences (```json ... ``` or ``` ... ```)
    - Leading/trailing non-JSON text
    - Trailing commas before ] or }

    Returns the extracted JSON string, or None if no valid JSON object is found.
    """
    if not text or not text.strip():
        return None
    t = text.strip()
    # Strip markdown code fences
    if "```json" in t:
        t = t.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in t:
        t = t.split("```", 1)[1].split("```", 1)[0].strip()
    # Find first '{' and match braces
    start = t.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(t)):
        if t[i] == "{":
            depth += 1
        elif t[i] == "}":
            depth -= 1
            if depth == 0:
                result = t[start : i + 1]
                # Fix trailing commas before ] or }
                result = re.sub(r",\s*([}\]])", r"\1", result)
                return result
    # Unmatched braces
    return None


def extract_json_array(text: str) -> str | None:
    """Extract the first complete JSON array from text.

    Mirrors extract_json_object but finds [...] instead of {...}.
    Handles markdown code fences and trailing commas.

    Returns the extracted JSON string, or None if no valid JSON array is found.
    """
    if not text or not text.strip():
        return None
    t = text.strip()
    # Strip markdown code fences
    if "```json" in t:
        t = t.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in t:
        t = t.split("```", 1)[1].split("```", 1)[0].strip()
    # Find first '[' and match brackets
    start = t.find("[")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape_next = False
    for i in range(start, len(t)):
        c = t[i]
        if escape_next:
            escape_next = False
            continue
        if c == "\\":
            escape_next = True
            continue
        if c == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                result = t[start : i + 1]
                # Fix trailing commas before ] or }
                result = re.sub(r",\s*([}\]])", r"\1", result)
                return result
    # Unmatched brackets
    return None


def ensure_json(text: str) -> str | None:
    """Extract a JSON object from response text.

    Thin wrapper over extract_json_object for backward compatibility.
    Returns the extracted JSON string, or None if not found.
    """
    return extract_json_object(text)


def deterministic_repair(text: str) -> str:
    """Extract and repair a JSON object from text, returning '{}' on failure.

    Strict fail-safe parsing where a valid JSON string is always required
    (even if empty).
    """
    result = extract_json_object(text)
    return result if result is not None else "{}"
