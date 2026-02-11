#!/usr/bin/env python3
"""Tick pacing simulation: run N actions with default costs, report turns per tick.
Target: median tick every 6–12 turns in typical play.
Usage: python backend/scripts/tick_pacing_sim.py [--turns N] [--sessions M]
"""
from __future__ import annotations

import argparse
import random
import statistics
import sys
from pathlib import Path

# Ensure backend is on path
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.time_economy import (
    get_time_cost,
    WORLD_TICK_MINUTES,
    ACTION_TIME_COSTS,
)

# Typical session action mix (action_type -> weight)
# More dialogue/interact, fewer combat/travel
TYPICAL_MIX: list[tuple[str, float]] = [
    ("TALK", 0.25),
    ("INTERACT", 0.20),
    ("TRAVEL", 0.15),
    ("INVESTIGATE", 0.12),
    ("PERSUADE", 0.12),
    ("SNEAK", 0.08),
    ("ATTACK", 0.05),
    ("IDLE", 0.03),
]


def pick_action(rng: random.Random) -> str:
    """Pick action type according to typical mix."""
    r = rng.random()
    cum = 0.0
    for action, weight in TYPICAL_MIX:
        cum += weight
        if r < cum:
            return action
    return "TALK"


def simulate_session(num_turns: int, rng: random.Random | None = None) -> list[int]:
    """Simulate one session; return list of turn indices where tick occurred (1-based)."""
    rng = rng or random.Random()
    t = 0
    ticks: list[int] = []
    for turn in range(1, num_turns + 1):
        action = pick_action(rng)
        cost = get_time_cost(action)
        t_next = t + cost
        # Tick when we cross boundary
        tick_before = t // WORLD_TICK_MINUTES
        tick_after = t_next // WORLD_TICK_MINUTES
        while tick_after > tick_before:
            tick_before += 1
            ticks.append(turn)
        t = t_next
    return ticks


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate tick pacing for typical play")
    parser.add_argument("--turns", "-n", type=int, default=50, help="Turns per session (default 50)")
    parser.add_argument("--sessions", "-s", type=int, default=100, help="Sessions to simulate (default 100)")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for reproducibility")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    all_turns_per_tick: list[int] = []

    for _ in range(args.sessions):
        ticks = simulate_session(args.turns, rng)
        for i in range(1, len(ticks)):
            all_turns_per_tick.append(ticks[i] - ticks[i - 1])
        if len(ticks) == 1:
            all_turns_per_tick.append(ticks[0])
        elif len(ticks) == 0 and args.turns > 0:
            all_turns_per_tick.append(args.turns)

    if not all_turns_per_tick:
        print("No ticks occurred in any session.")
        return

    print("=== Tick Pacing Simulation ===")
    print(f"Tick length: {WORLD_TICK_MINUTES} min ({WORLD_TICK_MINUTES // 60}h)")
    print(f"Sessions: {args.sessions}, Turns/session: {args.turns}")
    print()
    print("Action costs:")
    for k, v in sorted(ACTION_TIME_COSTS.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v} min")
    print()
    print("Turns between ticks (typical mix):")
    print(f"  Min:    {min(all_turns_per_tick)}")
    print(f"  Median: {statistics.median(all_turns_per_tick):.1f}")
    print(f"  Mean:   {statistics.mean(all_turns_per_tick):.1f}")
    print(f"  Max:    {max(all_turns_per_tick)}")
    print()
    target = (6, 12)
    median_val = statistics.median(all_turns_per_tick)
    if target[0] <= median_val <= target[1]:
        print(f"[OK] Median {median_val:.1f} is within target {target[0]}-{target[1]} turns per tick")
    else:
        print(f"[TUNE] Median {median_val:.1f} outside target {target[0]}-{target[1]}. Adjust costs in backend/app/time_economy.py")


if __name__ == "__main__":
    main()
