"""Narrative validator node: post-narration validation + repair loop."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from backend.app.core.turn_contract import build_turn_contract
from backend.app.core.truth_ledger import detect_contradictions
from backend.app.models.turn_contract import TurnContract

logger = logging.getLogger(__name__)

_SUCCESS_PATTERNS = [
    re.compile(r"\bsucceed(?:s|ed)?\b", re.I),
    re.compile(r"\bmanage[ds]?\s+to\b", re.I),
]
_FAILURE_PATTERNS = [
    re.compile(r"\bfail(?:s|ed)?\b", re.I),
    re.compile(r"\bmiss(?:es|ed)?\b", re.I),
]


def _check_mechanic_consistency(final_text: str, mechanic_result: dict[str, Any] | None) -> list[str]:
    warnings: list[str] = []
    if not mechanic_result or not final_text:
        return warnings
    success = mechanic_result.get("success")
    if success is None:
        return warnings
    if success is False:
        for pat in _SUCCESS_PATTERNS:
            if pat.search(final_text):
                warnings.append("Narrative contradicts failed mechanic result.")
                break
    if success is True:
        for pat in _FAILURE_PATTERNS:
            if pat.search(final_text):
                warnings.append("Narrative contradicts successful mechanic result.")
                break
    return warnings


def _check_constraint_contradictions(final_text: str, constraints: list[str]) -> list[str]:
    return []


def _validate_choices(contract: TurnContract) -> list[str]:
    issues: list[str] = []
    if not (2 <= len(contract.choices) <= 4):
        issues.append("choices must contain 2..4 options")
    labels = [c.label.strip().lower() for c in contract.choices]
    if len(set(labels)) != len(labels):
        issues.append("choices must be distinct")
    for c in contract.choices:
        if not c.intent.intent_type:
            issues.append(f"choice {c.id} missing intent_type")
        if len(c.label.strip()) < 3:
            issues.append(f"choice {c.id} label not actionable")
    return issues


def _validate_lore_constraints(state: dict[str, Any], contract: TurnContract) -> list[str]:
    campaign = state.get("campaign") or {}
    ws = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
    ws = ws if isinstance(ws, dict) else {}
    allowed_factions = set(ws.get("allowed_factions") or [])
    if not allowed_factions:
        return []
    issues: list[str] = []
    for choice in contract.choices:
        faction = choice.intent.target_ids.faction_id
        if faction and faction not in allowed_factions and not choice.intent.params.get("original"):
            issues.append(f"choice {choice.id} uses disallowed faction '{faction}'")
    return issues


def _repair_state_fields(state: dict[str, Any]) -> dict[str, Any]:
    """Safe deterministic repair used when strict validation fails."""
    repaired = dict(state)
    suggestions = list(repaired.get("suggested_actions") or [])[:4]
    if len(suggestions) < 2:
        suggestions.extend([
            {"id": "repair_1", "label": "Survey the area", "intent_text": "Survey the area", "risk_level": "SAFE"},
            {"id": "repair_2", "label": "Ask for intel", "intent_text": "Ask for intel", "risk_level": "SAFE"},
        ])
    repaired["suggested_actions"] = suggestions[:4]
    return repaired


def narrative_validator_node(state: dict[str, Any]) -> dict[str, Any]:
    final_text = state.get("final_text") or ""
    mechanic_result = state.get("mechanic_result") or {}
    campaign = state.get("campaign") or {}
    ws = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
    ws = ws if isinstance(ws, dict) else {}

    validation_warnings: list[str] = []
    validation_warnings.extend(_check_mechanic_consistency(final_text, mechanic_result))

    current = dict(state)
    max_repairs = 2
    repairs = 0
    for attempt in range(max_repairs + 1):
        try:
            contract = build_turn_contract(current)
            schema_contract = TurnContract.model_validate(contract.model_dump(mode="json"))
            choice_issues = _validate_choices(schema_contract)
            lore_issues = _validate_lore_constraints(current, schema_contract)
            contradictions = detect_contradictions(final_text, ws.get("canonical_facts") or {})
            issues = choice_issues + lore_issues + contradictions
            if not issues:
                current["turn_contract"] = schema_contract.model_dump(mode="json")
                break
            validation_warnings.extend(issues)
            logger.warning("Turn contract validation failed (attempt %s): %s", attempt + 1, json.dumps(issues))
            if attempt < max_repairs:
                repairs += 1
                current = _repair_state_fields(current)
                logger.warning("Repair attempt %s applied.", repairs)
            else:
                fallback = _repair_state_fields(current)
                fallback_contract = build_turn_contract(fallback)
                current["turn_contract"] = fallback_contract.model_dump(mode="json")
        except Exception as exc:
            validation_warnings.append(f"turn_contract schema validation error: {exc}")
            logger.warning("Turn contract schema failure attempt=%s error=%s", attempt + 1, exc)
            if attempt < max_repairs:
                repairs += 1
                current = _repair_state_fields(current)
            else:
                current["turn_contract"] = build_turn_contract(_repair_state_fields(current)).model_dump(mode="json")

    existing_warnings = list(current.get("warnings") or [])
    for w in validation_warnings:
        if w not in existing_warnings:
            existing_warnings.append(w)
    current["warnings"] = existing_warnings
    current["validation_notes"] = validation_warnings
    return current
