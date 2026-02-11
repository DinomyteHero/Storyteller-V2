"""Deterministic NPC generator using Era Pack templates."""
from __future__ import annotations

import hashlib
import random
from typing import Any

from backend.app.world.era_pack_models import EraPack, EraNpcTemplate


def derive_seed(campaign_id: str, turn_number: int, counter: int = 0) -> int:
    """Derive a stable integer seed from campaign + turn + counter."""
    base = f"{campaign_id}:{turn_number}:{counter}"
    digest = hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]
    return int(digest, 16)


def _pick_template(
    templates: list[EraNpcTemplate],
    rng: random.Random,
    location_id: str,
    faction_id: str | None = None,
) -> EraNpcTemplate | None:
    if not templates:
        return None
    scored: list[tuple[int, EraNpcTemplate]] = []
    for t in templates:
        score = 0
        if faction_id and faction_id in (t.tags or []):
            score += 2
        if location_id and location_id in (t.tags or []):
            score += 1
        scored.append((score, t))
    rng.shuffle(scored)
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1] if scored else None


def _pick_template_from_encounters(
    templates: list[EraNpcTemplate],
    encounter_table: list,
    rng: random.Random,
) -> EraNpcTemplate | None:
    """Pick a template using a location's encounter_table (weighted, deterministic).

    encounter_table entries are expected to have `template_id` and `weight`.
    """
    if not templates or not encounter_table:
        return None
    templates_by_id = {t.id: t for t in templates if getattr(t, "id", None)}
    weighted: list[tuple[int, EraNpcTemplate]] = []
    for e in encounter_table:
        tid = getattr(e, "template_id", None) or (e.get("template_id") if isinstance(e, dict) else None)
        w = getattr(e, "weight", None) if not isinstance(e, dict) else e.get("weight")
        if not tid:
            continue
        t = templates_by_id.get(str(tid))
        if t is None:
            continue
        try:
            weight = int(w or 0)
        except Exception:
            weight = 0
        if weight <= 0:
            continue
        weighted.append((weight, t))
    if not weighted:
        return None
    total = sum(w for w, _ in weighted)
    # Deterministic weighted choice from seeded RNG
    roll = rng.uniform(0, total)
    acc = 0.0
    for w, t in weighted:
        acc += w
        if roll <= acc:
            return t
    return weighted[-1][1]


def _pick_from_list(options: list[str], rng: random.Random, fallback: str = "") -> str:
    if options:
        return str(rng.choice(options))
    return fallback


def _pick_traits(traits: list[str], rng: random.Random, max_traits: int = 2) -> list[str]:
    if not traits:
        return []
    pool = list(traits)
    rng.shuffle(pool)
    return pool[: max_traits]


# Archetype-to-template trait hints for Hero's Journey awareness
_ARCHETYPE_TRAIT_HINTS: dict[str, list[str]] = {
    "MENTOR": ["wise", "experienced", "patient", "cryptic", "knowledgeable"],
    "SHADOW": ["ruthless", "cunning", "powerful", "charismatic", "dark"],
    "THRESHOLD_GUARDIAN": ["stern", "vigilant", "testing", "imposing", "dutiful"],
    "ALLY": ["loyal", "resourceful", "friendly", "capable", "supportive"],
    "SHAPESHIFTER": ["ambiguous", "charming", "deceptive", "unpredictable", "secretive"],
    "HERALD": ["urgent", "dramatic", "purposeful", "messenger", "catalyst"],
    "TRICKSTER": ["irreverent", "clever", "comic", "disruptive", "insightful"],
}

# Archetype-to-role hints
_ARCHETYPE_ROLE_HINTS: dict[str, list[str]] = {
    "MENTOR": ["sage", "teacher", "elder", "veteran", "master"],
    "SHADOW": ["rival", "nemesis", "dark lord", "hunter", "enforcer"],
    "THRESHOLD_GUARDIAN": ["guard", "gatekeeper", "officer", "sentinel", "warden"],
    "ALLY": ["friend", "partner", "comrade", "associate", "aide"],
    "SHAPESHIFTER": ["informant", "double agent", "enigma", "contact", "wildcard"],
    "HERALD": ["messenger", "scout", "envoy", "harbinger", "courier"],
    "TRICKSTER": ["rogue", "prankster", "jester", "gambler", "con artist"],
}


def generate_npc(
    *,
    era_pack: EraPack | None,
    location_id: str,
    faction_id: str | None = None,
    seed: int | None = None,
    campaign_id: str | None = None,
    turn_number: int | None = None,
    counter: int = 0,
    archetype_hint: str | None = None,
) -> dict[str, Any]:
    """Generate a deterministic NPC record from templates and a seed.

    If archetype_hint is provided (e.g., "MENTOR", "SHADOW"), the generated
    NPC will be influenced by Hero's Journey archetype traits and role hints.
    """
    if seed is None:
        if not campaign_id:
            campaign_id = "campaign"
        if turn_number is None:
            turn_number = 0
        seed = derive_seed(campaign_id, turn_number, counter)
    rng = random.Random(seed)

    templates = era_pack.npcs.templates if era_pack else []
    template = None
    if era_pack:
        loc = era_pack.location_by_id(location_id)
        if loc and getattr(loc, "encounter_table", None):
            template = _pick_template_from_encounters(templates, list(loc.encounter_table or []), rng)
    if template is None:
        template = _pick_template(templates, rng, location_id, faction_id)

    namebank = ""
    if template and template.namebank:
        namebank = template.namebank

    name_options: list[str] = []
    if era_pack and namebank and namebank in era_pack.namebanks:
        name_options = era_pack.namebanks.get(namebank, []) or []
    elif era_pack and "default" in era_pack.namebanks:
        name_options = era_pack.namebanks.get("default", []) or []

    name = _pick_from_list(name_options, rng, fallback="Wanderer")
    role = template.role if template and template.role else "NPC"
    archetype = template.archetype if template and template.archetype else ""
    traits = _pick_traits(template.traits if template else [], rng)
    motivation = _pick_from_list(template.motivations if template else [], rng, fallback="get through the day")
    secret = _pick_from_list(template.secrets if template else [], rng, fallback="")
    voice_tags = list(template.voice_tags if template else [])
    species = _pick_from_list(template.species if template else [], rng, fallback="")

    # Hero's Journey archetype enhancement
    archetype_upper = (archetype_hint or "").upper().strip()
    if archetype_upper and archetype_upper in _ARCHETYPE_TRAIT_HINTS:
        # Blend archetype traits with template traits
        arch_traits = _ARCHETYPE_TRAIT_HINTS[archetype_upper]
        extra = _pick_traits(arch_traits, rng, max_traits=1)
        traits = list(set(traits + extra))
        # Override role if template role is generic
        if role in ("NPC", "npc", "") and archetype_upper in _ARCHETYPE_ROLE_HINTS:
            role_options = _ARCHETYPE_ROLE_HINTS[archetype_upper]
            role = _pick_from_list(role_options, rng, fallback=role)
        # Set archetype from hint if not already set
        if not archetype:
            archetype = archetype_upper

    seed_info = {
        "seed": seed,
        "campaign_id": campaign_id,
        "turn_number": turn_number,
        "counter": counter,
        "template_id": template.id if template else "",
    }
    npc_id_source = f"{seed}:{name}:{role}:{template.id if template else ''}"
    npc_id = "gen_" + hashlib.sha256(npc_id_source.encode("utf-8")).hexdigest()[:12]

    stats_json = {
        "origin": "procedural",
        "generated": True,
        "era_id": era_pack.era_id if era_pack else "",
        "template_id": template.id if template else "",
        "archetype": archetype,
        "archetype_hint": archetype_upper or None,
        "traits": traits,
        "motivation": motivation,
        "secret": secret,
        "voice_tags": voice_tags,
        "species": species,
        "faction_id": faction_id,
        "default_location_id": location_id,
        "seed_info": seed_info,
    }

    return {
        "character_id": npc_id,
        "name": name,
        "role": role,
        "relationship_score": 0,
        "secret_agenda": secret or None,
        "location_id": location_id,
        "stats_json": stats_json,
        "hp_current": 10,
    }
