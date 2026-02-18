"""Prologue engine: constrained turn loop for the opening sequence.

The prologue runs before Arc 1. It is a short (3-5 turn) sequence that
introduces the player to the setting and their character's situation,
based on the ``PrologueScreenplay`` generated at campaign creation.

Key design:
- ``prologue_mode: True`` in ``world_state_json`` activates the constrained mode.
- The LangGraph pipeline runs **unchanged**; only ``arc_planner_node`` changes
  behaviour when it detects prologue mode (uses ``PROLOGUE_STAGES`` instead
  of ``SETUP→RISING→CLIMAX→RESOLUTION``).
- When the prologue is complete (all stages visited or player action triggers
  ``departure_trigger``), ``is_prologue_complete()`` returns True and the
  caller should call ``build_origin_context_manifest()`` then clear the flag.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Constrained prologue stages (shorter than main arc)
PROLOGUE_STAGES = ["SETUP", "INCITING_INCIDENT", "DEPARTURE"]

# Minimum turns per prologue stage before advancing
_PROLOGUE_MIN_TURNS: dict[str, int] = {
    "SETUP": 1,
    "INCITING_INCIDENT": 1,
    "DEPARTURE": 1,
}

# Pacing hints per prologue stage (injected into arc_guidance for Director)
_PROLOGUE_PACING_HINTS: dict[str, str] = {
    "SETUP": (
        "Introduce the opening scene. Establish atmosphere, the immediate situation, "
        "and the 1-2 NPCs present. No major conflict yet — orient the player."
    ),
    "INCITING_INCIDENT": (
        "The inciting moment occurs. Something disrupts the status quo and forces "
        "the player to act. Choices here establish the character's initial alignment."
    ),
    "DEPARTURE": (
        "The player is on the cusp of leaving. Wrap up the prologue with a clear "
        "transition hook that connects to the main arc. Make the departure feel earned."
    ),
}

_PROLOGUE_TENSION: dict[str, str] = {
    "SETUP": "CALM",
    "INCITING_INCIDENT": "ESCALATING",
    "DEPARTURE": "RESOLVING",
}


def initialize_prologue(world_state: dict[str, Any], screenplay: dict[str, Any]) -> dict[str, Any]:
    """Write prologue mode flags into world_state_json.

    Call this once after ``PrologueScreenplayAgent.generate()`` at campaign
    creation. Returns the mutated world_state dict.
    """
    world_state["prologue_mode"] = True
    world_state["prologue_screenplay"] = screenplay
    world_state["prologue_arc_state"] = {
        "current_stage": PROLOGUE_STAGES[0],
        "stage_start_turn": 0,
        "stages_visited": [PROLOGUE_STAGES[0]],
    }
    # Seed the opening location from screenplay
    opening_loc = screenplay.get("opening_location_id")
    if opening_loc and not world_state.get("current_location"):
        world_state["current_location"] = opening_loc
    # Inject opening narration as the first arc_seed hint
    opening_narration = screenplay.get("opening_narration", "")
    if opening_narration:
        arc_seed = world_state.get("arc_seed") if isinstance(world_state.get("arc_seed"), dict) else {}
        arc_seed["prologue_opening_narration"] = opening_narration
        world_state["arc_seed"] = arc_seed
    logger.info("Prologue initialized: stage=%s location=%s", PROLOGUE_STAGES[0], opening_loc)
    return world_state


def is_prologue_complete(world_state: dict[str, Any]) -> bool:
    """Return True if the prologue turn loop should end.

    Criteria (any of):
    - ``prologue_mode`` is False or absent
    - All ``PROLOGUE_STAGES`` have been visited
    - ``prologue_arc_state.current_stage`` is ``DEPARTURE`` and at least
      1 turn has been spent there
    """
    if not world_state.get("prologue_mode"):
        return True
    prologue_arc = world_state.get("prologue_arc_state")
    if not isinstance(prologue_arc, dict):
        return True
    stages_visited = prologue_arc.get("stages_visited") or []
    if all(s in stages_visited for s in PROLOGUE_STAGES):
        current = prologue_arc.get("current_stage", "")
        start = int(prologue_arc.get("stage_start_turn", 0))
        # Need at least 1 turn in DEPARTURE before completing
        current_turn = world_state.get("turn_number") or 0
        if current == "DEPARTURE" and (current_turn - start) >= 1:
            return True
    return False


def advance_prologue_stage(world_state: dict[str, Any], turn_number: int) -> tuple[str, bool]:
    """Attempt to advance the prologue stage. Returns (current_stage, transitioned).

    Called by the prologue branch in arc_planner_node. Pure function against
    the world_state dict (does NOT write back — caller writes ``prologue_arc_state``
    to the world_state via arc_guidance).
    """
    prologue_arc = world_state.get("prologue_arc_state")
    if not isinstance(prologue_arc, dict):
        return PROLOGUE_STAGES[0], False

    current_stage = prologue_arc.get("current_stage") or PROLOGUE_STAGES[0]
    stage_start_turn = int(prologue_arc.get("stage_start_turn", 0))
    turns_in_stage = max(0, turn_number - stage_start_turn)
    min_turns = _PROLOGUE_MIN_TURNS.get(current_stage, 1)

    if turns_in_stage < min_turns:
        return current_stage, False

    idx = PROLOGUE_STAGES.index(current_stage) if current_stage in PROLOGUE_STAGES else 0
    if idx < len(PROLOGUE_STAGES) - 1:
        next_stage = PROLOGUE_STAGES[idx + 1]
        logger.info(
            "Prologue stage advance: %s -> %s at turn %d",
            current_stage, next_stage, turn_number,
        )
        return next_stage, True
    return current_stage, False


def build_prologue_arc_guidance(
    world_state: dict[str, Any], turn_number: int
) -> dict[str, Any]:
    """Build arc_guidance dict for a prologue turn.

    Mirrors the structure of the normal arc_planner output so the Director
    and other downstream nodes receive a compatible interface.
    """
    prologue_arc = world_state.get("prologue_arc_state") or {}
    current_stage = prologue_arc.get("current_stage") or PROLOGUE_STAGES[0]
    stage_start_turn = int(prologue_arc.get("stage_start_turn", 0))
    stages_visited: list[str] = list(prologue_arc.get("stages_visited") or [current_stage])
    turns_in_stage = max(0, turn_number - stage_start_turn)

    # Attempt to advance
    next_stage, transitioned = advance_prologue_stage(world_state, turn_number)
    if transitioned:
        current_stage = next_stage
        stage_start_turn = turn_number
        turns_in_stage = 0
        if current_stage not in stages_visited:
            stages_visited.append(current_stage)

    screenplay = world_state.get("prologue_screenplay") or {}
    pacing_hint = _PROLOGUE_PACING_HINTS.get(current_stage, "")
    tension_level = _PROLOGUE_TENSION.get(current_stage, "CALM")

    # Inject inciting moment into pacing hint during INCITING_INCIDENT
    if current_stage == "INCITING_INCIDENT":
        inciting = screenplay.get("inciting_moment", "")
        if inciting:
            pacing_hint = f"{pacing_hint}\nInciting moment: {inciting}"

    # Inject departure trigger during DEPARTURE
    if current_stage == "DEPARTURE":
        departure = screenplay.get("departure_trigger", "")
        if departure:
            pacing_hint = f"{pacing_hint}\nDeparture trigger: {departure}"

    return {
        # Expose prologue stage as arc_stage so downstream nodes work unchanged
        "arc_stage": current_stage,
        "prologue_mode": True,
        "prologue_stage": current_stage,
        "priority_threads": [],
        "tension_level": tension_level,
        "pacing_hint": pacing_hint,
        "suggested_weight": {"SOCIAL": 0.5, "EXPLORE": 0.4, "COMMIT": 0.1},
        "transition_occurred": transitioned,
        "turns_in_stage": turns_in_stage,
        "active_themes": [],
        "theme_guidance": "",
        "hero_beat": "PROLOGUE",
        "hero_pacing": pacing_hint,
        "archetype_hints": [],
        "era_transition_pending": False,
        # Arc state for persistence (written back by Commit node)
        "arc_state": {
            "current_stage": current_stage,
            "stage_start_turn": stage_start_turn,
        },
        "prologue_arc_state": {
            "current_stage": current_stage,
            "stage_start_turn": stage_start_turn,
            "stages_visited": stages_visited,
        },
    }


def build_origin_context_manifest(
    world_state: dict[str, Any],
    player: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the origin_context dict to persist at prologue end.

    Written to ``world_state_json["origin_context"]`` by the
    ``POST /prologue/complete`` endpoint. The Director and ArcWeaver
    read this for the first ~5 Arc 1 turns to maintain narrative continuity.
    """
    screenplay = world_state.get("prologue_screenplay") or {}
    prologue_arc = world_state.get("prologue_arc_state") or {}

    # Gather everything that happened during the prologue
    character = player or {}
    background_id = (
        character.get("background_id")
        or character.get("background")
        or screenplay.get("origin_context", {}).get("background_id", "unknown")
    )
    species_id = (
        character.get("species_id")
        or screenplay.get("origin_context", {}).get("species_id", "human")
    )

    ledger = world_state.get("ledger") or {}
    established_facts = (ledger.get("established_facts") or [])[:10]
    open_threads = (ledger.get("open_threads") or [])[:5]

    # NPCs encountered in the prologue (from screenplay cast)
    npc_cast = screenplay.get("npc_cast") or []
    npc_names = [n.get("name") for n in npc_cast if isinstance(n, dict) and n.get("name")]

    origin_context: dict[str, Any] = {
        "background_id": background_id,
        "species_id": species_id,
        "prologue_completed": True,
        "prologue_title": screenplay.get("prologue_title", "Prologue"),
        "opening_location_id": screenplay.get("opening_location_id", ""),
        "tone": screenplay.get("tone", "gritty"),
        "inciting_moment": screenplay.get("inciting_moment", ""),
        "departure_trigger": screenplay.get("departure_trigger", ""),
        "npc_names_encountered": npc_names,
        "prologue_facts": established_facts,
        "prologue_threads": open_threads,
        "stages_completed": prologue_arc.get("stages_visited", []),
    }

    # Merge any origin_context already in screenplay (from PrologueScreenplay.origin_context)
    screenplay_origin = screenplay.get("origin_context")
    if isinstance(screenplay_origin, dict):
        for k, v in screenplay_origin.items():
            if k not in origin_context:
                origin_context[k] = v

    return origin_context
