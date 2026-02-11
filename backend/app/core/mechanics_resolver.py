"""Deterministic mechanics helpers for strict intent/check resolution."""
from __future__ import annotations

import random
from dataclasses import dataclass

from backend.app.models.turn_contract import Outcome, OutcomeCheck


@dataclass(frozen=True)
class CheckConfig:
    skill: str
    dc: int
    advantage: bool = False
    disadvantage: bool = False
    base_mod: int = 0
    situational_mod: int = 0


def resolve_check(config: CheckConfig, rng: random.Random | None = None) -> Outcome:
    """Resolve a d20 check deterministically (if seeded RNG is passed)."""
    roller = rng or random.Random()
    r1 = roller.randint(1, 20)
    r2 = roller.randint(1, 20)
    if config.advantage and not config.disadvantage:
        roll = max(r1, r2)
    elif config.disadvantage and not config.advantage:
        roll = min(r1, r2)
    else:
        roll = r1

    total = roll + config.base_mod + config.situational_mod
    if roll == 20:
        category = "CRIT_SUCCESS"
    elif roll == 1:
        category = "CRIT_FAIL"
    elif total >= config.dc + 5:
        category = "SUCCESS"
    elif total >= config.dc:
        category = "PARTIAL"
    else:
        category = "FAIL"

    return Outcome(
        category=category,
        check=OutcomeCheck(
            skill=config.skill,
            dc=config.dc,
            roll=roll,
            total=total,
            mods={"base": config.base_mod, "situational": config.situational_mod},
        ),
        consequences=[],
        tags=[],
    )

