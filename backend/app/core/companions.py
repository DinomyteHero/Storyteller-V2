"""Companion definitions and campaign seeding for KOTOR/ME-style party system.

V1.1: Three-tier depth system:
- Curated: Hand-authored in companions.yaml (depth_tier: deep)
- Generated: Auto-generated at campaign init via CompanionDeepGenAgent
- Emergent: Auto-generated at recruitment for NPCs promoted to companions
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from shared.cache import clear_cache, get_cache_value, set_cache_value

logger = logging.getLogger(__name__)

_COMPANIONS_CACHE_KEY = "companions_cache"


def _companions_path() -> Path:
    """Resolve path to data/companions.yaml relative to project root."""
    # backend/app/core/companions.py -> project_root/data/companions.yaml
    root = Path(__file__).resolve().parent.parent.parent.parent
    return root / "data" / "companions.yaml"


def load_companions(era: str | None = None) -> list[dict[str, Any]]:
    """Load companion definitions, optionally filtered by era.

    Load order:
    1. Check era pack dir: data/static/era_packs/{era}/companions.yaml
    2. Fall back to data/companions.yaml (global pool)
    3. Filter by era field if present and era is specified
    """
    cached = get_cache_value(_COMPANIONS_CACHE_KEY, lambda: None)
    if cached is None:
        all_comps: list[dict[str, Any]] = []
        # Load global pool
        path = _companions_path()
        if path.exists():
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            global_comps = data.get("companions", []) if isinstance(data, dict) else []
            all_comps.extend(c for c in global_comps if isinstance(c, dict) and c.get("id"))

        # Also check era pack companions (additive, with V2.20 fields)
        root = Path(__file__).resolve().parent.parent.parent.parent
        era_packs_dir = root / "data" / "static" / "era_packs"
        if era_packs_dir.is_dir():
            seen_ids = {c["id"] for c in all_comps}
            for era_dir in era_packs_dir.iterdir():
                if not era_dir.is_dir():
                    continue
                era_comp_path = era_dir / "companions.yaml"
                if era_comp_path.exists():
                    with open(era_comp_path, encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                    era_comps = data.get("companions", []) if isinstance(data, dict) else []
                    for c in era_comps:
                        if isinstance(c, dict) and c.get("id"):
                            if c["id"] not in seen_ids:
                                all_comps.append(c)
                                seen_ids.add(c["id"])
                            else:
                                # Merge era-pack fields into existing companion
                                for existing in all_comps:
                                    if existing.get("id") == c["id"]:
                                        for key in ("enables_affordances", "blocks_affordances",
                                                     "influence", "banter", "recruitment",
                                                     "role_in_party", "voice", "personal_quest_id"):
                                            if key in c and key not in existing:
                                                existing[key] = c[key]
                                        break
        cached = set_cache_value(_COMPANIONS_CACHE_KEY, all_comps)

    if not era:
        return cached
    # Filter: companions with no era field are available to all eras
    era_upper = era.upper()
    return [c for c in cached if not c.get("era") or str(c["era"]).upper() == era_upper]


def clear_companions_cache() -> None:
    """Clear cached companions (useful for tests)."""
    clear_cache(_COMPANIONS_CACHE_KEY)


def get_companion_by_id(comp_id: str) -> dict[str, Any] | None:
    """Return companion definition by id, or None."""
    for c in load_companions():
        if c.get("id") == comp_id:
            return c
    return None


def recruit_companion(
    world_state: dict[str, Any],
    comp_id: str,
    auto_depth: bool = True,
) -> bool:
    """Add a companion to the party by ID. Returns True if recruited, False if already in party or unknown.

    Called when an NPC matching a companion definition reaches ALLY affinity threshold,
    or when a recruitment event triggers during gameplay.

    V1.1: When auto_depth=True (default), automatically generates deep tier data
    for standard-tier companions at recruitment time (Emergent tier).
    """
    comp = get_companion_by_id(comp_id)
    if not comp:
        return False
    party = world_state.get("party") or []
    if comp_id in party:
        return False
    party.append(comp_id)
    world_state["party"] = party
    world_state.setdefault("party_affinity", {})[comp_id] = int(comp.get("default_affinity", 0))
    world_state.setdefault("party_traits", {})[comp_id] = dict(comp.get("traits") or {})
    world_state.setdefault("loyalty_progress", {})[comp_id] = 0

    # V1.1 Emergent tier: auto-generate deep data if needed
    if auto_depth and not is_deep_companion(comp_id):
        try:
            deep_data = ensure_deep_companion(comp_id)
            if deep_data:
                # Persist generated profile in world_state for durability
                profiles = world_state.setdefault("companion_deep_profiles", {})
                profiles[comp_id] = deep_data
        except Exception as e:
            logger.debug("Auto-depth generation at recruitment failed for %s: %s", comp_id, e)

    return True


def is_deep_companion(comp_id: str) -> bool:
    """Return True if the companion has deep tier data."""
    comp = get_companion_by_id(comp_id)
    if not comp:
        return False
    return str(comp.get("depth_tier", "")).lower() == "deep"


def get_deep_companion_data(comp_id: str) -> dict[str, Any] | None:
    """Return deep tier data for a companion, or None if standard tier.

    Returns dict with keys: personal_banter, opinion_triggers, personal_quest,
    dialogue_samples (only for depth_tier == 'deep' companions).
    """
    comp = get_companion_by_id(comp_id)
    if not comp or str(comp.get("depth_tier", "")).lower() != "deep":
        return None
    return {
        "personal_banter": comp.get("personal_banter") or {},
        "opinion_triggers": comp.get("opinion_triggers") or [],
        "personal_quest": comp.get("personal_quest"),
        "dialogue_samples": comp.get("dialogue_samples") or [],
    }


def match_opinion_trigger(
    comp_id: str,
    scene_tags: list[str],
) -> dict[str, Any] | None:
    """Check if any opinion trigger matches the current scene tags.

    Returns the first matching trigger dict with keys:
    situation, reaction, affinity_bonus, tags.
    Returns None if no match.
    """
    deep = get_deep_companion_data(comp_id)
    if not deep:
        return None

    tag_set = {t.lower() for t in scene_tags}
    if not tag_set:
        return None

    for trigger in deep.get("opinion_triggers") or []:
        if not isinstance(trigger, dict):
            continue
        trigger_tags = {t.lower() for t in (trigger.get("tags") or [])}
        if trigger_tags & tag_set:
            return trigger

    return None


def get_personal_banter(
    comp_id: str,
    tone: str,
) -> str | None:
    """Return a personal banter line for the companion's tone, or None.

    Falls back to 'general' banter if no tone-specific line available.
    """
    deep = get_deep_companion_data(comp_id)
    if not deep:
        return None

    banter = deep.get("personal_banter") or {}
    tone_lines = banter.get(tone.upper()) or []
    if tone_lines:
        import random
        return random.choice(tone_lines)

    general_lines = banter.get("general") or []
    if general_lines:
        import random
        return random.choice(general_lines)

    return None


def build_initial_companion_state(world_time_minutes: int = 0, era: str | None = None) -> dict[str, Any]:
    """Build companion/alignment/reputation state for new campaign.

    Party starts EMPTY. Companions are met and recruited organically through
    gameplay — via encounters, quests, and player choices. This avoids the
    'thrust into the middle' feeling of having unknown party members at start.
    """
    return {
        "campaign_start_world_time_minutes": world_time_minutes,
        "party": [],
        "party_affinity": {},
        "party_traits": {},
        "loyalty_progress": {},
        "alignment": {
            "light_dark": 0,
            "paragon_renegade": 0,
        },
        "faction_reputation": {},
        "news_feed": [],
        "banter_queue": [],
    }


# ---------------------------------------------------------------------------
# V1.1: Deep companion profile management (Generated & Emergent tiers)
# ---------------------------------------------------------------------------


def register_deep_profile(comp_id: str, deep_data: dict[str, Any]) -> bool:
    """Merge generated deep tier data into a companion's cached definition.

    This makes the companion appear as depth_tier='deep' to all existing
    functions (is_deep_companion, get_deep_companion_data, match_opinion_trigger,
    get_personal_banter) with zero changes to those functions.

    Returns True if merge succeeded, False if companion not found.
    """
    comp = get_companion_by_id(comp_id)
    if not comp:
        return False

    comp["depth_tier"] = "deep"
    for key in (
        "personal_banter",
        "opinion_triggers",
        "personal_quest",
        "dialogue_samples",
    ):
        if key in deep_data:
            comp[key] = deep_data[key]

    # Wound and revelation stages: only set if not already present (curated wins)
    if "wound" in deep_data and not comp.get("wound"):
        comp["wound"] = deep_data["wound"]
    if "revelation_stages" in deep_data and not comp.get("revelation_stages"):
        comp["revelation_stages"] = deep_data["revelation_stages"]

    logger.debug("Registered deep profile for companion %s", comp_id)
    return True


def restore_companion_profiles(profiles: dict[str, dict[str, Any]]) -> int:
    """Bulk-restore generated deep profiles from persisted world_state data.

    Called when a campaign is loaded to re-merge generated profiles into
    the companion cache. Returns the number of profiles restored.

    Args:
        profiles: Dict mapping companion_id -> deep_data (from
                  world_state_json['companion_deep_profiles'])
    """
    count = 0
    for comp_id, deep_data in (profiles or {}).items():
        if register_deep_profile(comp_id, deep_data):
            count += 1
    if count:
        logger.info("Restored %d generated companion deep profiles", count)
    return count


def ensure_deep_companion(
    comp_id: str,
    setting_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Ensure a companion has deep tier data, generating it if needed.

    If the companion already has depth_tier='deep', returns existing deep data.
    Otherwise, generates deep data via CompanionDeepGenAgent, registers it,
    and returns the generated data.

    This is the lazy-generation entry point for the Emergent tier.
    """
    # Already deep? Return existing data.
    if is_deep_companion(comp_id):
        return get_deep_companion_data(comp_id)

    comp = get_companion_by_id(comp_id)
    if not comp:
        return None

    try:
        from backend.app.core.agents.companion_deep_gen_agent import (
            CompanionDeepGenAgent,
        )
        from backend.app.core.agents.base import AgentLLM

        llm = AgentLLM("companion_deep_gen")
        agent = CompanionDeepGenAgent(llm=llm)
        deep_data = agent.generate(comp, setting_context)
        register_deep_profile(comp_id, deep_data)
        logger.info("Auto-generated deep profile for companion %s", comp_id)
        return deep_data
    except Exception as e:
        logger.warning(
            "Failed to auto-generate deep profile for %s: %s", comp_id, e
        )
        return None


def promote_npc_to_companion(
    npc_data: dict[str, Any],
    setting_context: dict[str, Any] | None = None,
    generate_depth: bool = True,
) -> str | None:
    """Promote a runtime NPC to a companion definition with deep tier data.

    Creates a companion definition from NPC data, adds it to the companion
    cache, optionally generates deep tier data, and returns the new companion ID.

    Args:
        npc_data: NPC dict (id, name, role, traits, motivation, voice, etc.)
        setting_context: Optional setting info for deep gen
        generate_depth: Whether to auto-generate deep tier data

    Returns:
        The new companion ID, or None on failure.
    """
    npc_name = npc_data.get("name", "Unknown")
    npc_id = npc_data.get("id", "")

    # Generate a companion ID from NPC ID
    comp_id = npc_id.replace("gen-npc-", "comp-gen-").replace("reactive-", "comp-")
    if not comp_id.startswith("comp-"):
        comp_id = f"comp-{comp_id}"

    # Check if already exists
    if get_companion_by_id(comp_id):
        return comp_id

    # Map NPC traits (list[str]) to companion trait axes (dict[str, int])
    npc_traits = npc_data.get("traits") or []
    if isinstance(npc_traits, list):
        from backend.app.core.agents.companion_deep_gen_agent import (
            _map_freetext_traits_to_axes,
        )

        trait_axes = _map_freetext_traits_to_axes(npc_traits)
    elif isinstance(npc_traits, dict):
        trait_axes = dict(npc_traits)
    else:
        trait_axes = {"idealist_pragmatic": 0, "merciful_ruthless": 0, "lawful_rebellious": 0}

    # Build companion definition from NPC data
    voice = npc_data.get("voice") or {}
    comp_def: dict[str, Any] = {
        "id": comp_id,
        "name": npc_name,
        "archetype": npc_data.get("role", "traveler"),
        "gender": npc_data.get("gender", "unknown"),
        "species": npc_data.get("species", "Unknown"),
        "voice_tags": [],
        "motivation": npc_data.get("motivation", ""),
        "speech_quirk": voice.get("rhetorical_style", ""),
        "traits": trait_axes,
        "default_affinity": 10,
        "loyalty_hook": voice.get("wound", ""),
        "banter_style": "stoic",
        "faction_interest": (
            [npc_data["faction_id"]]
            if npc_data.get("faction_id")
            else []
        ),
        "recruitment_context": f"Met during gameplay as {npc_data.get('role', 'an NPC')}.",
        "origin": "emergent",
    }

    # Build wound from NPC voice data if available
    if voice.get("wound"):
        comp_def["wound"] = {
            "surface": f"Something weighs on {npc_name}.",
            "deep": voice["wound"],
            "core": f"What {npc_name} truly needs remains hidden.",
        }

    # Add to companion cache
    all_comps = load_companions()
    all_comps.append(comp_def)

    # Generate deep tier data if requested
    if generate_depth:
        try:
            from backend.app.core.agents.companion_deep_gen_agent import (
                CompanionDeepGenAgent,
            )
            from backend.app.core.agents.base import AgentLLM

            llm = AgentLLM("companion_deep_gen")
            agent = CompanionDeepGenAgent(llm=llm)
            deep_data = agent.generate(comp_def, setting_context)
            register_deep_profile(comp_id, deep_data)
            logger.info(
                "Promoted NPC %s to deep companion %s", npc_name, comp_id
            )
        except Exception as e:
            logger.warning(
                "Promoted NPC %s to companion %s (depth gen failed: %s)",
                npc_name,
                comp_id,
                e,
            )
    else:
        logger.info("Promoted NPC %s to companion %s (no depth)", npc_name, comp_id)

    return comp_id
