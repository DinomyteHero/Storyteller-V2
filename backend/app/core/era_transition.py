"""Era transition manager: handles progression between Star Wars eras.

V3.0: Complete galactic timeline with all era packs, adjacency validation,
and Historical/Sandbox campaign modes (HOI4-style).

Timeline adjacency is enforced in BOTH modes — you cannot jump thousands
of years between eras. The mode only controls whether player choices alter
established canon lore or play within it.

Historical: Canon events are immutable. The Death Star is destroyed at Yavin
  regardless of what you do. You're a side character in the established story.
  Failures are real — you can lose missions and face consequences — but the
  galaxy's macro history proceeds as written.

Sandbox: Player choices CAN alter the macro universe. If you help the Empire
  prevent the Death Star's destruction, it survives. Factions can be destroyed
  or reshaped. But timeline adjacency still applies — eras must progress in
  chronological order through adjacent periods.

Triggers when an arc reaches RESOLUTION and narrative milestones are met.
Carries over: player sheet, companions, KG entities, episodic memories.
Resets: NPC cast, factions, locations (loaded from new era pack).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from backend.app.content.repository import CONTENT_REPOSITORY

logger = logging.getLogger(__name__)

# ── Campaign Modes ───────────────────────────────────────────────────

CampaignMode = Literal["historical", "sandbox"]

CAMPAIGN_MODE_DESCRIPTIONS: dict[str, str] = {
    "historical": (
        "Canon events proceed as established in Star Wars Legends lore. "
        "Your choices shape your personal story but cannot alter galactic history. "
        "You may fail missions and face real consequences — the galaxy moves on regardless."
    ),
    "sandbox": (
        "Your choices can reshape galactic history. Factions rise and fall based on "
        "your actions. Canon events may be prevented, altered, or accelerated. "
        "The timeline still progresses through adjacent eras — no impossible jumps."
    ),
}


def get_campaign_mode(world_state: dict[str, Any]) -> CampaignMode:
    """Read campaign mode from world_state, default to historical."""
    mode = (world_state.get("campaign_mode") or "historical").lower().strip()
    if mode in ("historical", "sandbox"):
        return mode  # type: ignore[return-value]
    return "historical"


# ── Galactic Timeline ────────────────────────────────────────────────

@dataclass(frozen=True)
class EraDefinition:
    """Static definition of an era in the Star Wars Legends timeline."""
    era_id: str
    display_name: str
    time_period: str
    approx_bby: int  # Approximate midpoint in BBY (negative = ABY)
    summary: str


# Complete chronological timeline — ordered from ancient to far future.
# approx_bby: positive = BBY (Before Battle of Yavin), negative = ABY (After).
ERA_TIMELINE: list[EraDefinition] = [
    EraDefinition(
        era_id="KOTOR",
        display_name="Knights of the Old Republic",
        time_period="~3954 BBY",
        approx_bby=3954,
        summary="The Jedi Civil War's aftermath. Sith remnants, ancient mysteries, and the Force at its most primal.",
    ),
    EraDefinition(
        era_id="DARK_TIMES",
        display_name="The Dark Times",
        time_period="19-0 BBY",
        approx_bby=10,
        summary="Order 66's aftermath. Jedi hunted, Empire rising, the galaxy's darkest hour before rebellion.",
    ),
    EraDefinition(
        era_id="REBELLION",
        display_name="the Galactic Civil War",
        time_period="0-4 ABY",
        approx_bby=-2,
        summary="Alliance vs. Empire. The Death Star, Yavin, Hoth, Endor. Hope against tyranny.",
    ),
    EraDefinition(
        era_id="NEW_REPUBLIC",
        display_name="the New Republic Era",
        time_period="5-19 ABY",
        approx_bby=-12,
        summary="Thrawn's return, the fledgling Republic, Luke's Jedi academy. Political chess and rebirth.",
    ),
    EraDefinition(
        era_id="NEW_JEDI_ORDER",
        display_name="the Yuuzhan Vong War",
        time_period="25-29 ABY",
        approx_bby=-27,
        summary="Extragalactic invasion. Coruscant falls. The Jedi tested by an enemy the Force cannot sense.",
    ),
    EraDefinition(
        era_id="LEGACY",
        display_name="the Legacy Era",
        time_period="130-138 ABY",
        approx_bby=-134,
        summary="Darth Krayt's Rule of One. Three-way civil war: One Sith vs. Fel Empire vs. Alliance Remnant.",
    ),
]

# Lookup by era_id (case-insensitive)
_ERA_BY_ID: dict[str, EraDefinition] = {e.era_id: e for e in ERA_TIMELINE}

# Legacy compat: flat list of era_ids in chronological order
ERA_PROGRESSION: list[str] = [e.era_id for e in ERA_TIMELINE]

# Legacy compat: display names
ERA_DISPLAY_NAMES: dict[str, str] = {e.era_id: e.display_name for e in ERA_TIMELINE}


def get_era_definition(era_id: str) -> EraDefinition | None:
    """Look up an era definition by ID (case-insensitive)."""
    return _ERA_BY_ID.get(era_id.upper().strip())


def get_era_index(era_id: str) -> int | None:
    """Return the chronological index (0-based) of an era, or None if unknown."""
    upper = era_id.upper().strip()
    for i, era in enumerate(ERA_TIMELINE):
        if era.era_id == upper:
            return i
    return None


# ── Adjacency & Transition Validation ────────────────────────────────

# Adjacent era pairs that can naturally connect in a saga.
# Same-era sequels are always allowed (not listed here, handled in code).
# Key: (from_era, to_era) -> narrative bridge text.
ADJACENT_TRANSITIONS: dict[tuple[str, str], str] = {
    # KOTOR is isolated — 3900+ year gap to Dark Times. No natural transition.
    # Within-KOTOR sequels are fine (same era).

    # Dark Times -> Rebellion: ~19 year gap. Natural for same character.
    ("DARK_TIMES", "REBELLION"): (
        "Years of hiding and survival have hardened you. "
        "The scattered whispers of resistance have grown into a true Rebellion. "
        "The Alliance to Restore the Republic needs every fighter it can get."
    ),

    # Rebellion -> New Republic: ~1-5 year gap. Direct sequel.
    ("REBELLION", "NEW_REPUBLIC"): (
        "Five years have passed since the Battle of Endor. "
        "The Empire is shattered but not dead. The New Republic holds Coruscant, "
        "but Grand Admiral Thrawn has returned from the Unknown Regions."
    ),

    # New Republic -> NJO: ~6-10 year gap. Same generation.
    ("NEW_REPUBLIC", "NEW_JEDI_ORDER"): (
        "Two decades of fragile peace are shattered. "
        "An enemy from beyond the galaxy has come — the Yuuzhan Vong, "
        "warriors who cannot be felt in the Force."
    ),

    # NJO -> Legacy: ~100 year gap. Descendant/legacy campaign.
    ("NEW_JEDI_ORDER", "LEGACY"): (
        "A century of change has reshaped the galaxy. "
        "The Yuuzhan Vong War is ancient history. Darth Krayt has seized Coruscant "
        "and imposed the Rule of One. Your legacy endures — but in what form?"
    ),
}

# Legacy compat
ERA_TIME_GAPS: dict[str, str] = {
    f"{k[0]}->{k[1]}": v for k, v in ADJACENT_TRANSITIONS.items()
}


def is_adjacent(from_era: str, to_era: str) -> bool:
    """Check if two eras are chronologically adjacent (valid transition).

    Same-era is always valid (sequel within the same time period).
    Otherwise, must be in ADJACENT_TRANSITIONS.
    """
    from_upper = from_era.upper().strip()
    to_upper = to_era.upper().strip()

    # Same era: always valid (anthology / sequel within era)
    if from_upper == to_upper:
        return True

    return (from_upper, to_upper) in ADJACENT_TRANSITIONS


def validate_era_transition(
    from_era: str,
    to_era: str,
) -> tuple[bool, str]:
    """Validate whether an era transition is allowed.

    Returns (is_valid, reason).
    Timeline adjacency is enforced in BOTH Historical and Sandbox modes.
    """
    from_upper = from_era.upper().strip()
    to_upper = to_era.upper().strip()

    from_def = get_era_definition(from_upper)
    to_def = get_era_definition(to_upper)

    if not from_def:
        return False, f"Unknown source era: {from_era}"
    if not to_def:
        return False, f"Unknown target era: {to_era}"

    # Ensure target era has playable content on disk before allowing transition.
    try:
        CONTENT_REPOSITORY.get_pack(to_upper)
    except Exception:
        return False, f"No era pack found for target era: {to_era}"

    # Same era: always OK
    if from_upper == to_upper:
        return True, "Same-era sequel"

    # Must be adjacent
    if not is_adjacent(from_upper, to_upper):
        from_idx = get_era_index(from_upper)
        to_idx = get_era_index(to_upper)
        if from_idx is not None and to_idx is not None and to_idx < from_idx:
            return False, (
                f"Cannot go backward in the timeline: "
                f"{from_def.display_name} ({from_def.time_period}) -> "
                f"{to_def.display_name} ({to_def.time_period})"
            )
        # Calculate approximate gap
        gap = abs(from_def.approx_bby - to_def.approx_bby)
        return False, (
            f"Timeline gap too large ({gap:,} years): "
            f"{from_def.display_name} ({from_def.time_period}) -> "
            f"{to_def.display_name} ({to_def.time_period}). "
            f"Eras must be chronologically adjacent."
        )

    # Forward-only check (no going backward even between adjacent eras)
    from_idx = get_era_index(from_upper)
    to_idx = get_era_index(to_upper)
    if from_idx is not None and to_idx is not None and to_idx < from_idx:
        return False, (
            f"Cannot go backward: {from_def.display_name} -> {to_def.display_name}"
        )

    return True, "Adjacent era transition"


def get_allowed_next_eras(current_era: str) -> list[str]:
    """Return list of eras that can follow the current one.

    Always includes same-era (sequel) plus the next adjacent era if one exists.
    """
    current_upper = current_era.upper().strip()
    allowed = [current_upper]  # Same-era sequel always allowed

    for (from_era, to_era) in ADJACENT_TRANSITIONS:
        if from_era == current_upper:
            allowed.append(to_era)

    return allowed


# ── Historical vs Sandbox Behavior ───────────────────────────────────

def get_canon_constraints(era_id: str, mode: CampaignMode) -> dict[str, Any]:
    """Return canon constraints for the given era and mode.

    Historical: returns immutable canon facts and events that MUST occur.
    Sandbox: returns canon facts as initial conditions that CAN be altered.
    """
    era = get_era_definition(era_id)
    if not era:
        return {"mode": mode, "canon_facts": [], "canon_mutable": mode == "sandbox"}

    return {
        "mode": mode,
        "era_id": era.era_id,
        "era_display_name": era.display_name,
        "era_summary": era.summary,
        "canon_mutable": mode == "sandbox",
        # In historical mode, the narrator/director should respect these as ground truth.
        # In sandbox mode, they're starting conditions the player can alter.
        "mode_instruction": (
            "Canon events in this era are IMMUTABLE. The player's story exists within "
            "established history. Missions can fail — the player faces real consequences — "
            "but galactic-scale events proceed as written in Legends lore."
            if mode == "historical"
            else
            "The player's choices CAN alter the course of galactic history. Canon events "
            "are starting conditions, not certainties. If the player's actions logically "
            "prevent or change a major event, honor that divergence believably. "
            "Consequences must still be realistic — victories aren't guaranteed and "
            "failures have lasting impact."
        ),
    }


# ── Legacy-Compatible Functions ──────────────────────────────────────

def get_next_era(current_era: str) -> str | None:
    """Return the next chronologically adjacent era, or None if at the end.

    Only returns eras that are in ADJACENT_TRANSITIONS (skips non-adjacent gaps).
    """
    current_upper = current_era.upper().strip()
    for (from_era, to_era) in ADJACENT_TRANSITIONS:
        if from_era == current_upper:
            return to_era
    return None


def can_transition(
    current_era: str,
    arc_stage: str | None,
    arc_guidance: dict | None = None,
) -> bool:
    """Check if an era transition is available.

    Conditions:
    - Current arc is in RESOLUTION stage
    - There is a next era to transition to
    - Arc guidance indicates the resolution is sufficiently complete
    """
    if not arc_stage or arc_stage.upper() != "RESOLUTION":
        return False
    if get_next_era(current_era) is None:
        return False
    # Check if resolution has progressed enough (at least 2 turns in RESOLUTION)
    if arc_guidance:
        turns_in_stage = arc_guidance.get("turns_in_stage", 0)
        if turns_in_stage < 2:
            return False
    return True


def build_transition_summary(
    current_era: str,
    next_era: str,
    player_name: str = "the protagonist",
    mode: CampaignMode = "historical",
) -> str:
    """Build a cinematic era transition narrative summary."""
    current_def = get_era_definition(current_era)
    next_def = get_era_definition(next_era)
    current_display = current_def.display_name if current_def else current_era
    next_display = next_def.display_name if next_def else next_era

    bridge = ADJACENT_TRANSITIONS.get(
        (current_era.upper().strip(), next_era.upper().strip()),
        "Time passes. The galaxy transforms.",
    )

    summary = (
        f"The chapter of {current_display} draws to a close.\n\n"
        f"{bridge}\n\n"
        f"A new chapter begins: {next_display}.\n\n"
        f"{player_name}'s story continues, shaped by everything that came before."
    )

    if mode == "sandbox":
        summary += (
            "\n\nThe galaxy remembers what you changed. "
            "History has diverged from the path that was written."
        )

    return summary


def execute_transition(
    world_state: dict[str, Any],
    current_era: str,
    next_era: str,
) -> dict[str, Any]:
    """Execute an era transition on world_state.

    Validates adjacency before proceeding. Raises ValueError if invalid.

    Carries over:
    - Player sheet (preserved externally in characters table)
    - Companions (party, party_affinity, party_traits)
    - Ledger (established_facts, constraints — threads are closed)
    - Era summaries (compressed memory of previous eras)
    - Episodic memories (preserved in DB table, campaign-scoped)
    - Campaign mode (historical/sandbox persists across eras)

    Resets:
    - Active factions (loaded fresh from new era pack)
    - NPC cast (new era = new cast, old NPCs remain in KG)
    - Arc state (resets to SETUP for new era)
    - News feed (cleared for new era)
    """
    # Validate adjacency (hard rule in both modes)
    is_valid, reason = validate_era_transition(current_era, next_era)
    if not is_valid:
        raise ValueError(f"Invalid era transition: {reason}")

    new_ws = dict(world_state)

    # Preserve campaign mode across transitions
    mode = get_campaign_mode(world_state)
    new_ws["campaign_mode"] = mode

    # Reset arc state to SETUP for new era
    new_ws["arc_state"] = {
        "current_stage": "SETUP",
        "stage_start_turn": 0,  # Will be updated by next arc planner run
    }

    # Close all open threads (they belong to the old era)
    ledger = dict(new_ws.get("ledger") or {})
    closed_threads = ledger.get("open_threads") or []
    if closed_threads:
        facts = list(ledger.get("established_facts") or [])
        for thread in closed_threads:
            facts.append(f"[{current_era}] Resolved: {thread}")
        ledger["established_facts"] = facts
    ledger["open_threads"] = []
    # Reset active themes for new era
    ledger["active_themes"] = []
    new_ws["ledger"] = ledger

    # Clear news feed
    new_ws["news_feed"] = []

    # Active factions will be loaded from the new era pack by the encounter system
    # Mark them for refresh
    new_ws["active_factions"] = []
    new_ws["_era_factions_stale"] = True

    # In sandbox mode, carry forward any lore divergences as established facts
    if mode == "sandbox":
        divergences = list(new_ws.get("lore_divergences") or [])
        if divergences:
            facts = list((new_ws.get("ledger") or {}).get("established_facts") or [])
            for div in divergences:
                facts.append(f"[DIVERGENCE from {current_era}] {div}")
            ledger = dict(new_ws.get("ledger") or {})
            ledger["established_facts"] = facts
            new_ws["ledger"] = ledger

    # Compress current era into a summary
    era_summaries = list(new_ws.get("era_summaries") or [])
    current_def = get_era_definition(current_era)
    current_display = current_def.display_name if current_def else current_era
    facts = (new_ws.get("ledger") or {}).get("established_facts") or []
    recent_facts = [f for f in facts if not f.startswith(f"[{current_era}]")][:5]
    summary_text = (
        f"During {current_display}: " + "; ".join(recent_facts)
        if recent_facts
        else f"Lived through {current_display}."
    )
    era_summaries.append(summary_text)
    new_ws["era_summaries"] = era_summaries

    logger.info(
        "Era transition executed: %s -> %s (mode=%s)", current_era, next_era, mode
    )
    return new_ws
