"""Time economy: configurable costs per action type.

Centralized in this module (not scattered). Tuned so WorldSim ticks occur roughly every 6–12 turns in typical play.
Override tick length via WORLD_TICK_INTERVAL_HOURS env (default 4 = 240 min).
Run: python backend/scripts/tick_pacing_sim.py to verify pacing.
"""
from __future__ import annotations

import os

# --- Tick length ---
# WorldSim runs when world clock crosses this boundary. Default 240 min = 4 hours.
# Set WORLD_TICK_INTERVAL_HOURS env to override (e.g. 2 for faster ticks).
WORLD_TICK_INTERVAL_HOURS = float(os.environ.get("WORLD_TICK_INTERVAL_HOURS", "4"))
WORLD_TICK_MINUTES = int(WORLD_TICK_INTERVAL_HOURS * 60)

# --- Action time costs (minutes) ---
# dialogue_only: TALK when router skips mechanic (short exchange)
DIALOGUE_ONLY_MINUTES = 8

# quick_action: INTERACT (grab, take), SNEAK
QUICK_ACTION_MINUTES = 18

# risky_action: ATTACK (combat exchange)
RISKY_ACTION_MINUTES = 35

# investigate: INVESTIGATE, search
INVESTIGATE_MINUTES = 25

# persuade: PERSUADE, negotiate
PERSUADE_MINUTES = 20

# travel_short: TRAVEL (one location hop)
TRAVEL_SHORT_MINUTES = 45

# travel_hyperspace: interplanetary travel (hyperspace jump)
TRAVEL_HYPERSPACE_MINUTES = 480  # 8 hours

# idle: IDLE (no input) advances no time
IDLE_MINUTES = 0

# Map action_type -> cost (for MechanicAgent)
ACTION_TIME_COSTS: dict[str, int] = {
    "TALK": DIALOGUE_ONLY_MINUTES,
    "IDLE": IDLE_MINUTES,
    "TRAVEL": TRAVEL_SHORT_MINUTES,
    "ATTACK": RISKY_ACTION_MINUTES,
    "SNEAK": QUICK_ACTION_MINUTES,
    "PERSUADE": PERSUADE_MINUTES,
    "INVESTIGATE": INVESTIGATE_MINUTES,
    "INTERACT": QUICK_ACTION_MINUTES,
}


def get_time_cost(action_type: str) -> int:
    """Return minutes for action_type; default to QUICK_ACTION for unknown."""
    return ACTION_TIME_COSTS.get(action_type, QUICK_ACTION_MINUTES)
