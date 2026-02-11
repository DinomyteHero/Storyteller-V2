"""TurnContract builders, validators, and deterministic repair loop."""
from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

from backend.app.core.truth_ledger import contradiction_errors
from backend.app.models.state import ActionSuggestion, MechanicOutput
from backend.app.models.turn_contract import Choice, ChoiceCost, Intent, Outcome, StateDelta, TurnContract, TurnDebug, TurnMeta

logger = logging.getLogger(__name__)

NON_CHOICE_LABELS = {"continue", "continue...", "next", "proceed"}


def infer_intent(user_input: str) -> Intent:
    low = (user_input or "").lower()
    mapping = [
        ("talk", "TALK"), ("ask", "TALK"), ("move", "MOVE"), ("travel", "MOVE"),
        ("fight", "FIGHT"), ("attack", "FIGHT"), ("sneak", "SNEAK"), ("hack", "HACK"),
        ("investigate", "INVESTIGATE"), ("search", "INVESTIGATE"), ("rest", "REST"),
        ("buy", "BUY"), ("use", "USE_ITEM"), ("force", "FORCE"),
    ]
    t = "TALK"
    for needle, intent in mapping:
        if needle in low:
            t = intent
            break
    return Intent(intent_type=t, target_ids={}, params={}, user_utterance=user_input or None)


def mechanic_to_outcome(m: MechanicOutput | None) -> tuple[Outcome, StateDelta]:
    if not m:
        return Outcome(category="PARTIAL", consequences=["No major change."], tags=[]), StateDelta(time_minutes=1)
    cat = "SUCCESS" if bool(m.success) else "FAIL"
    if m.roll == 20:
        cat = "CRIT_SUCCESS"
    elif m.roll == 1:
        cat = "CRIT_FAIL"
    consequences = [m.outcome_summary] if m.outcome_summary else []
    outcome = Outcome(category=cat, consequences=consequences, tags=list((m.flags or {}).keys()))
    if m.dc is not None and m.roll is not None:
        outcome.check = {
            "skill": (m.checks[0].skill if m.checks else m.action_type.lower()),
            "dc": int(m.dc),
            "roll": int(m.roll),
            "total": int(m.roll),
            "mods": {"base": 0, "situational": 0},
        }
    delta = StateDelta(
        time_minutes=int(m.time_cost_minutes or 0),
        relationship_delta={str(k): int(v) for k, v in (m.companion_affinity_delta or {}).items()},
        facts_upsert=[],
    )
    return outcome, delta


def suggestions_to_choices(actions: list[ActionSuggestion], turn_no: int) -> list[Choice]:
    if not actions:
        actions = [
            ActionSuggestion(label="Gather intel quietly", intent_text="Investigate nearby clues safely", category="EXPLORE", risk_level="SAFE"),
            ActionSuggestion(label="Talk to a local witness", intent_text="Talk to nearby NPCs", category="SOCIAL", risk_level="SAFE"),
            ActionSuggestion(label="Push into danger", intent_text="Force the issue with risk", category="COMMIT", risk_level="DANGEROUS"),
        ]
    out: list[Choice] = []
    for i, action in enumerate(actions[:4], start=1):
        risk = {"SAFE": "low", "RISKY": "med", "DANGEROUS": "high"}.get((action.risk_level or "").upper(), "med")
        out.append(
            Choice(
                id=f"t{turn_no}_c{i}",
                label=(action.label or "Act")[:80],
                intent=infer_intent(action.intent_text or action.label),
                risk=risk,
                cost=ChoiceCost(time_minutes=5),
            )
        )
    return out


def _sanitize_choices(choices: list[Choice], turn_no: int, has_companions: bool, objective_id: str | None) -> list[Choice]:
    sanitized: list[Choice] = []
    seen_labels: set[str] = set()
    seen_intents: set[str] = set()
    for c in choices:
        label = (c.label or "Act").strip()[:80]
        key = label.lower()
        if not label or key in seen_labels or key in NON_CHOICE_LABELS:
            continue
        if c.intent.intent_type in seen_intents:
            continue
        seen_labels.add(key)
        seen_intents.add(c.intent.intent_type)
        sanitized.append(c.model_copy(update={"label": label}))
    needs_safe = not any(c.risk == "low" for c in sanitized)
    needs_risky = not any(c.risk in {"med", "high"} for c in sanitized)
    if needs_safe:
        sanitized.append(
            Choice(
                id=f"t{turn_no}_safe",
                label="Ask for clarifying intel",
                intent=Intent(intent_type="INVESTIGATE", target_ids={}, params={"posture": "safe", "objective_id": objective_id} if objective_id else {"posture": "safe"}),
                risk="low",
                cost=ChoiceCost(time_minutes=4),
            )
        )
    if needs_risky:
        sanitized.append(
            Choice(
                id=f"t{turn_no}_risky",
                label="Commit to a high-stakes push",
                intent=Intent(intent_type="FIGHT", target_ids={}, params={"posture": "risky", "objective_id": objective_id} if objective_id else {"posture": "risky"}),
                risk="high",
                cost=ChoiceCost(time_minutes=8, heat=1),
            )
        )
    if objective_id and not any((c.intent.params or {}).get("objective_id") == objective_id for c in sanitized):
        c0 = sanitized[0] if sanitized else None
        if c0:
            c0.intent.params = {**(c0.intent.params or {}), "objective_id": objective_id}
    if has_companions and not any(c.intent.intent_type == "TALK" and (c.intent.params or {}).get("companion") for c in sanitized):
        sanitized.append(
            Choice(
                id=f"t{turn_no}_companion",
                label="Ask your companion for tactical input",
                intent=Intent(intent_type="TALK", target_ids={}, params={"companion": "party", "objective_id": objective_id} if objective_id else {"companion": "party"}),
                risk="low",
                cost=ChoiceCost(time_minutes=3),
            )
        )
    return sanitized[:4]


def validate_turn_contract(contract: TurnContract, ledger_facts: dict[str, Any] | None = None) -> list[str]:
    errs: list[str] = []
    if not (2 <= len(contract.choices) <= 4):
        errs.append("choices must be 2..4")
    labels = [c.label.strip().lower() for c in contract.choices]
    if len(set(labels)) != len(labels):
        errs.append("choice labels must be unique")
    if any(len(c.label) > 80 for c in contract.choices):
        errs.append("choice labels must be <= 80 chars")
    if any(lbl in NON_CHOICE_LABELS for lbl in labels):
        errs.append("choices include non-choice placeholder labels")
    intents = [c.intent.intent_type for c in contract.choices]
    if len(set(intents)) < 2:
        errs.append("choices must include distinct intents")
    if not any(c.risk == "low" for c in contract.choices):
        errs.append("must include at least one safe/information option")
    if not any(c.risk in {"med", "high"} for c in contract.choices):
        errs.append("must include at least one risky/progress option")
    if ledger_facts:
        claims = {f.fact_key: f.fact_value for f in contract.state_delta.facts_upsert}
        errs.extend(contradiction_errors(claims, ledger_facts))
    return errs


def _repair_with_json_patch(contract: TurnContract, turn_no: int, has_companions: bool, objective_id: str | None) -> tuple[TurnContract, list[dict[str, Any]]]:
    base = deepcopy(contract.model_dump(mode="json"))
    patches: list[dict[str, Any]] = []
    fixed_choices = _sanitize_choices([Choice.model_validate(c) for c in base.get("choices", [])], turn_no, has_companions, objective_id)
    if fixed_choices != contract.choices:
        patches.append({"op": "replace", "path": "/choices", "value": [c.model_dump(mode="json") for c in fixed_choices]})
        base["choices"] = [c.model_dump(mode="json") for c in fixed_choices]
    repaired = TurnContract.model_validate(base)
    return repaired, patches


def build_turn_contract(
    *,
    mode: str,
    campaign_id: str,
    turn_id: str,
    display_text: str,
    scene_goal: str,
    obstacle: str,
    stakes: str,
    mechanic_result: MechanicOutput | None,
    suggested_actions: list[ActionSuggestion],
    meta: TurnMeta,
    ledger_facts: dict[str, Any] | None = None,
    has_companions: bool = False,
    force_scene_transition: bool = False,
) -> TurnContract:
    outcome, state_delta = mechanic_to_outcome(mechanic_result)
    turn_no = int(turn_id.split("t")[-1]) if "t" in turn_id else 1
    objective_id = None
    if meta.active_objectives:
        first = meta.active_objectives[0] or {}
        objective_id = str(first.get("objective_id") or "").strip() or None
    choices = _sanitize_choices(suggestions_to_choices(suggested_actions, turn_no), turn_no, has_companions, objective_id)
    if force_scene_transition:
        state_delta.flags_set["scene_transition"] = True
        obstacle = f"{obstacle} Scene transition in effect."
    contract = TurnContract(
        mode=mode,
        campaign_id=campaign_id,
        turn_id=turn_id,
        display_text=display_text,
        scene_goal=scene_goal,
        obstacle=obstacle,
        stakes=stakes,
        outcome=outcome,
        state_delta=state_delta,
        choices=choices,
        meta=meta,
    )

    # Repair loop (max 2) preserving outcome/state_delta
    errors = validate_turn_contract(contract, ledger_facts)
    repair_count = 0
    while errors and repair_count < 2:
        original_outcome = deepcopy(contract.outcome.model_dump(mode="json"))
        original_delta = deepcopy(contract.state_delta.model_dump(mode="json"))
        contract, patches = _repair_with_json_patch(contract, turn_no, has_companions, objective_id)
        repair_count += 1
        if contract.outcome.model_dump(mode="json") != original_outcome or contract.state_delta.model_dump(mode="json") != original_delta:
            logger.error("Repair attempted to mutate outcome/state_delta; reverting.")
            contract.outcome = Outcome.model_validate(original_outcome)
            contract.state_delta = StateDelta.model_validate(original_delta)
        errors = validate_turn_contract(contract, ledger_facts)
        logger.info("turn_contract_repair campaign_id=%s turn_id=%s repair_count=%s patch_ops=%s errors=%s", campaign_id, turn_id, repair_count, len(patches), errors)

    if errors:
        # Deterministic safe fallback
        fallback_choices = _sanitize_choices([], turn_no, has_companions, objective_id)
        contract.display_text = (display_text or "").strip() or "The situation shifts abruptly. Choose your next approach."
        contract.choices = fallback_choices[:3]

    contract.debug = TurnDebug(validation_errors=errors, repaired=repair_count > 0, repair_count=repair_count)
    return contract
