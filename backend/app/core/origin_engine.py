"""Origin engine: constrained turn loop for the playable backstory.

The origin story runs BEFORE the prologue. It is a short (3-turn) sequence
that lets the player experience a defining moment from their character's
past, based on the ``OriginScreenplay`` generated at campaign creation.

Key design:
- ``origin_mode: True`` in ``world_state_json`` activates the constrained mode.
- The LangGraph pipeline runs **unchanged**; ``arc_planner_node`` detects
  origin_mode FIRST (before prologue_mode) and uses ``ORIGIN_STAGES``.
- When the origin is complete (all stages visited), ``is_origin_complete()``
  returns True and the caller transitions to prologue_mode.

Flow: Origin (3 turns) → Prologue (3-5 turns) → Arc 1
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Constrained origin stages
ORIGIN_STAGES = ["SCENE_SET", "DILEMMA", "RESOLUTION"]

# Minimum turns per origin stage before advancing
_ORIGIN_MIN_TURNS: dict[str, int] = {
    "SCENE_SET": 1,
    "DILEMMA": 1,
    "RESOLUTION": 1,
}

# Pacing hints per origin stage (injected into arc_guidance for Director)
_ORIGIN_PACING_HINTS: dict[str, str] = {
    "SCENE_SET": (
        "Set the scene for the origin flashback. Establish the immediate environment, "
        "the player's situation in the past, and introduce 1-2 key NPCs from their "
        "backstory. This is intimate and personal — focus on sensory details and emotion."
    ),
    "DILEMMA": (
        "Present the defining dilemma. The player faces a choice with no clear right "
        "answer — it reveals who they are at their core. The stakes are personal, not "
        "world-shaking. Choices here shape the character's psychology and alignment."
    ),
    "RESOLUTION": (
        "Resolve the origin moment. Show the immediate aftermath of the player's choice, "
        "then provide a transition that connects this memory to the present day. End with "
        "a forward-looking beat that leads into the prologue."
    ),
}

_ORIGIN_TENSION: dict[str, str] = {
    "SCENE_SET": "INTIMATE",
    "DILEMMA": "ESCALATING",
    "RESOLUTION": "BITTERSWEET",
}


def initialize_origin(
    world_state: dict[str, Any], screenplay: dict[str, Any]
) -> dict[str, Any]:
    """Write origin mode flags into world_state_json.

    Call this once after ``OriginScreenplayAgent.generate()`` at campaign
    creation. Returns the mutated world_state dict.
    """
    world_state["origin_mode"] = True
    world_state["origin_screenplay"] = screenplay
    world_state["origin_arc_state"] = {
        "current_stage": ORIGIN_STAGES[0],
        "stage_start_turn": 0,
        "stages_visited": [ORIGIN_STAGES[0]],
    }
    # Inject opening scene as the first arc_seed hint
    opening_scene = screenplay.get("opening_scene", "")
    if opening_scene:
        arc_seed = (
            world_state.get("arc_seed")
            if isinstance(world_state.get("arc_seed"), dict)
            else {}
        )
        arc_seed["origin_opening_scene"] = opening_scene
        world_state["arc_seed"] = arc_seed
    logger.info("Origin initialized: stage=%s", ORIGIN_STAGES[0])
    return world_state


def is_origin_complete(world_state: dict[str, Any]) -> bool:
    """Return True if the origin turn loop should end.

    Criteria (any of):
    - ``origin_mode`` is False or absent
    - All ``ORIGIN_STAGES`` have been visited
    - ``origin_arc_state.current_stage`` is ``RESOLUTION`` and at least
      1 turn has been spent there
    """
    if not world_state.get("origin_mode"):
        return True
    origin_arc = world_state.get("origin_arc_state")
    if not isinstance(origin_arc, dict):
        return True
    stages_visited = origin_arc.get("stages_visited") or []
    if all(s in stages_visited for s in ORIGIN_STAGES):
        current = origin_arc.get("current_stage", "")
        start = int(origin_arc.get("stage_start_turn", 0))
        current_turn = world_state.get("turn_number") or 0
        if current == "RESOLUTION" and (current_turn - start) >= 1:
            return True
    return False


def advance_origin_stage(
    world_state: dict[str, Any], turn_number: int
) -> tuple[str, bool]:
    """Attempt to advance the origin stage. Returns (current_stage, transitioned).

    Called by the origin branch in arc_planner_node. Pure function against
    the world_state dict (does NOT write back — caller writes).
    """
    origin_arc = world_state.get("origin_arc_state")
    if not isinstance(origin_arc, dict):
        return ORIGIN_STAGES[0], False

    current_stage = origin_arc.get("current_stage") or ORIGIN_STAGES[0]
    stage_start_turn = int(origin_arc.get("stage_start_turn", 0))
    turns_in_stage = max(0, turn_number - stage_start_turn)
    min_turns = _ORIGIN_MIN_TURNS.get(current_stage, 1)

    if turns_in_stage < min_turns:
        return current_stage, False

    idx = (
        ORIGIN_STAGES.index(current_stage)
        if current_stage in ORIGIN_STAGES
        else 0
    )
    if idx < len(ORIGIN_STAGES) - 1:
        next_stage = ORIGIN_STAGES[idx + 1]
        logger.info(
            "Origin stage advance: %s -> %s at turn %d",
            current_stage,
            next_stage,
            turn_number,
        )
        return next_stage, True
    return current_stage, False


def build_origin_arc_guidance(
    world_state: dict[str, Any], turn_number: int
) -> dict[str, Any]:
    """Build arc_guidance dict for an origin turn.

    Mirrors the structure of the normal arc_planner output so the Director
    and other downstream nodes receive a compatible interface.
    """
    origin_arc = world_state.get("origin_arc_state") or {}
    current_stage = origin_arc.get("current_stage") or ORIGIN_STAGES[0]
    stage_start_turn = int(origin_arc.get("stage_start_turn", 0))
    stages_visited: list[str] = list(
        origin_arc.get("stages_visited") or [current_stage]
    )
    turns_in_stage = max(0, turn_number - stage_start_turn)

    # Attempt to advance
    next_stage, transitioned = advance_origin_stage(world_state, turn_number)
    if transitioned:
        current_stage = next_stage
        stage_start_turn = turn_number
        turns_in_stage = 0
        if current_stage not in stages_visited:
            stages_visited.append(current_stage)

    screenplay = world_state.get("origin_screenplay") or {}
    pacing_hint = _ORIGIN_PACING_HINTS.get(current_stage, "")
    tension_level = _ORIGIN_TENSION.get(current_stage, "INTIMATE")

    # Inject dilemma during DILEMMA stage
    if current_stage == "DILEMMA":
        dilemma = screenplay.get("dilemma", "")
        if dilemma:
            pacing_hint = f"{pacing_hint}\nDilemma: {dilemma}"

    # Inject resolution hook during RESOLUTION stage
    if current_stage == "RESOLUTION":
        hook = screenplay.get("resolution_hook", "")
        if hook:
            pacing_hint = f"{pacing_hint}\nResolution hook: {hook}"

    return {
        # Expose origin stage as arc_stage so downstream nodes work unchanged
        "arc_stage": current_stage,
        "origin_mode": True,
        "origin_stage": current_stage,
        "priority_threads": [],
        "tension_level": tension_level,
        "pacing_hint": pacing_hint,
        "suggested_weight": {"SOCIAL": 0.6, "EXPLORE": 0.2, "COMMIT": 0.2},
        "transition_occurred": transitioned,
        "turns_in_stage": turns_in_stage,
        "active_themes": [],
        "theme_guidance": "",
        "hero_beat": "ORIGIN",
        "hero_pacing": pacing_hint,
        "archetype_hints": [],
        "era_transition_pending": False,
        # Arc state for persistence (written back by Commit node)
        "arc_state": {
            "current_stage": current_stage,
            "stage_start_turn": stage_start_turn,
        },
        "origin_arc_state": {
            "current_stage": current_stage,
            "stage_start_turn": stage_start_turn,
            "stages_visited": stages_visited,
        },
    }


def build_origin_handoff(
    world_state: dict[str, Any],
) -> dict[str, Any]:
    """Build the origin handoff dict when origin completes.

    This is written to ``world_state_json["origin_handoff"]`` and read by
    the prologue engine to maintain narrative continuity.
    """
    screenplay = world_state.get("origin_screenplay") or {}
    origin_arc = world_state.get("origin_arc_state") or {}

    return {
        "origin_completed": True,
        "origin_title": screenplay.get("origin_title", ""),
        "background_id": screenplay.get("background_id", ""),
        "species_id": screenplay.get("species_id", ""),
        "tone": screenplay.get("tone", "intimate"),
        "dilemma": screenplay.get("dilemma", ""),
        "resolution_hook": screenplay.get("resolution_hook", ""),
        "stages_completed": origin_arc.get("stages_visited", []),
        "npc_names": [
            n.get("name")
            for n in (screenplay.get("npc_cast") or [])
            if isinstance(n, dict) and n.get("name")
        ],
    }


def transition_origin_to_prologue(world_state: dict[str, Any]) -> dict[str, Any]:
    """Transition from origin mode to prologue mode.

    Called when ``is_origin_complete()`` returns True. Clears origin flags
    and preserves the handoff data for the prologue engine.
    """
    # Build handoff before clearing
    handoff = build_origin_handoff(world_state)
    world_state["origin_handoff"] = handoff

    # Clear origin mode
    world_state["origin_mode"] = False

    logger.info(
        "Origin complete — transitioning to prologue. Stages: %s",
        handoff.get("stages_completed"),
    )
    return world_state
