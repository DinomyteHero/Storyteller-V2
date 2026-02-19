"""SceneFrame builder node: establishes the immutable scene context for the turn.

Inserted between arc_planner and director. Pure Python — no LLM, no DB writes.
All downstream nodes (Director, Narrator, SuggestionRefiner, Commit) read the
scene_frame from state and must not contradict it.

V2.18: Adds topic anchoring, NPC voice profiles, subtext, agenda, style tags, pressure.
"""
from __future__ import annotations

import logging
from typing import Any

from backend.app.models.dialogue_turn import (
    NPCRef,
    SceneFrame,
    compute_scene_hash,
)
from backend.app.content.repository import CONTENT_REPOSITORY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# V2.18: KOTOR-soul derivation helpers
# ---------------------------------------------------------------------------

# NPC role keywords → topic_primary mapping
_NPC_ROLE_TOPICS: dict[str, str] = {
    "authority": "compliance", "guard": "suspicion", "officer": "authority",
    "commander": "authority", "captain": "authority", "admiral": "authority",
    "mentor": "identity", "teacher": "discipline", "jedi": "purpose",
    "master": "purpose", "sage": "wisdom",
    "informant": "trust", "spy": "loyalty", "contact": "reliability",
    "agent": "loyalty", "operative": "loyalty",
    "merchant": "value", "trader": "leverage", "shopkeeper": "value",
    "smuggler": "risk", "pilot": "freedom",
    "rival": "dominance", "bounty hunter": "survival", "assassin": "survival",
    "crime boss": "power", "crime lord": "power", "gang leader": "power",
    "diplomat": "compromise", "senator": "allegiance", "politician": "ambition",
    "governor": "authority", "bureaucrat": "compliance",
    "companion": "bond", "friend": "loyalty", "ally": "commitment",
    "stranger": "trust", "refugee": "survival", "prisoner": "freedom",
    "scientist": "truth", "doctor": "duty", "mechanic": "resourcefulness",
    "bartender": "information", "entertainer": "distraction",
}

# Arc stage → secondary topic overlay
_ARC_STAGE_TOPICS: dict[str, str] = {
    "SETUP": "first impressions",
    "RISING": "escalating stakes",
    "CLIMAX": "final reckoning",
    "RESOLUTION": "aftermath",
}

# Scene type → default topic for no-NPC scenes
_SCENE_TYPE_TOPICS: dict[str, str] = {
    "combat": "survival",
    "stealth": "caution",
    "travel": "journey",
    "exploration": "discovery",
    "dialogue": "understanding",
}

# Arc stage + topic → subtext templates
_SUBTEXT_TEMPLATES: dict[str, str] = {
    "SETUP": "Establishing whether {topic} can exist here.",
    "RISING": "Testing the limits of {topic} under pressure.",
    "CLIMAX": "{topic} will be decided one way or another.",
    "RESOLUTION": "What {topic} meant — and what it cost.",
}

# NPC role + arc stage → agenda templates
_AGENDA_TEMPLATES: dict[str, dict[str, str]] = {
    "SETUP": {
        "authority": "Assess the newcomer's usefulness.",
        "guard": "Determine if this person is a threat.",
        "mentor": "See if the student is ready to listen.",
        "informant": "Test whether this person can be trusted.",
        "merchant": "Find out what they can afford — or what they need.",
        "rival": "Establish dominance early.",
        "companion": "Decide if this partnership has potential.",
        "default": "Size up the stranger.",
    },
    "RISING": {
        "authority": "Tighten control before things slip further.",
        "guard": "Find the leak in security.",
        "mentor": "Push the student past their comfort zone.",
        "informant": "Deliver the dangerous truth.",
        "merchant": "Leverage the rising tension for profit.",
        "rival": "Exploit a weakness before it's too late.",
        "companion": "Confront the elephant in the room.",
        "default": "Press for commitment.",
    },
    "CLIMAX": {
        "authority": "Make the player choose a side.",
        "guard": "Execute orders — or break them.",
        "mentor": "Let go. The student must face this alone.",
        "informant": "Reveal the final piece of the puzzle.",
        "merchant": "Everything has a price. Name yours.",
        "rival": "Settle this — one way or another.",
        "companion": "Stand together or walk away.",
        "default": "Force the decision.",
    },
    "RESOLUTION": {
        "authority": "Reckon with the consequences.",
        "guard": "Resume the watch, changed.",
        "mentor": "Reflect on what was learned.",
        "informant": "Disappear — the truth is out.",
        "merchant": "Collect on old debts.",
        "rival": "Accept the outcome, bitter or sweet.",
        "companion": "Acknowledge what this cost.",
        "default": "Look back at what happened.",
    },
}

# Location keywords → style tags
_LOCATION_STYLE_TAGS: dict[str, list[str]] = {
    "cantina": ["noir", "seedy"],
    "tavern": ["noir", "seedy"],
    "temple": ["Socratic", "contemplative"],
    "jedi": ["Socratic", "contemplative"],
    "command": ["military", "terse"],
    "bridge": ["military", "terse"],
    "hangar": ["industrial", "urgent"],
    "docking": ["transient", "wary"],
    "market": ["bustling", "transactional"],
    "street": ["urban", "watchful"],
    "palace": ["formal", "political"],
    "senate": ["formal", "political"],
    "prison": ["oppressive", "desperate"],
    "med": ["clinical", "vulnerable"],
    "wilderness": ["isolated", "primal"],
    "swamp": ["mystical", "unsettling"],
}

# Voice tag → rhetorical style mapping (first voice_tag drives this)
_VOICE_TAG_RHETORICAL: dict[str, str] = {
    "mystical": "Socratic", "wise": "Socratic", "serene": "Socratic",
    "academic": "Socratic", "analytical": "analytical",
    "sarcastic": "deflective", "wry": "deflective", "dry": "deflective",
    "commanding": "blunt", "clipped": "blunt", "terse": "blunt",
    "gruff": "blunt", "fierce": "blunt",
    "menacing": "intimidating", "cold": "intimidating", "icy": "intimidating",
    "smooth": "persuasive", "diplomatic": "persuasive", "charming": "persuasive",
    "passionate": "poetic", "expressive": "poetic",
    "calculating": "coldly practical", "tactical": "coldly practical",
    "nervous": "anxious", "uncertain": "anxious", "apologetic": "anxious",
    "earnest": "sincere", "warm": "sincere", "hopeful": "sincere",
}

# Tell mannerisms mapped from voice_tag keywords
_VOICE_TAG_TELLS: dict[str, str] = {
    "measured": "pauses before answering, as if weighing each word",
    "deliberate": "speaks slowly, each sentence carefully constructed",
    "nervous": "fidgets with something — a ring, a hem, a datapad",
    "cold": "maintains eye contact without blinking",
    "wry": "one corner of the mouth twitches — almost a smile",
    "commanding": "stands with hands clasped behind back",
    "mystical": "gazes past you, as if seeing something you can't",
    "fierce": "jaw clenches between sentences",
    "smooth": "leans in slightly, voice dropping half a register",
    "gruff": "clears throat before speaking, as if the words cost effort",
    "calculating": "eyes narrow slightly before each response",
    "sarcastic": "tilts head, the faintest smirk pulling at one corner",
    "diplomatic": "nods thoughtfully before responding, as if considering all sides",
    "terse": "speaks in clipped fragments, never wasting a syllable",
    "serene": "breathes deeply before speaking, utterly still",
    "passionate": "gestures broadly, voice rising with conviction",
    "weary": "exhales slowly, shoulders carrying visible weight",
}


def _derive_topic(
    npc_refs: list[NPCRef],
    scene_type: str,
    arc_stage: str,
    themes: list[str],
) -> tuple[str, str]:
    """Derive topic_primary and topic_secondary from scene context."""
    primary = ""
    secondary = ""

    # Primary: from the first NPC's role (most relevant NPC)
    if npc_refs:
        role_lower = npc_refs[0].role.lower()
        for keyword, topic in _NPC_ROLE_TOPICS.items():
            if keyword in role_lower:
                primary = topic
                break
        if not primary:
            primary = "trust"  # default social topic

    # Fallback: from scene type
    if not primary:
        primary = _SCENE_TYPE_TOPICS.get(scene_type, "discovery")

    # Secondary: from arc stage or active themes
    if themes:
        secondary = themes[0].lower().replace("_", " ")
    else:
        secondary = _ARC_STAGE_TOPICS.get(arc_stage, "")

    return primary, secondary


def _derive_subtext(topic: str, arc_stage: str) -> str:
    """Derive emotional subtext from topic + arc stage."""
    template = _SUBTEXT_TEMPLATES.get(arc_stage, "The question of {topic} hangs in the air.")
    return template.format(topic=topic)


def _derive_npc_agenda(npc_role: str, arc_stage: str) -> str:
    """What the NPC wants from the player."""
    stage_agendas = _AGENDA_TEMPLATES.get(arc_stage, _AGENDA_TEMPLATES["SETUP"])
    role_lower = npc_role.lower()
    for keyword, agenda in stage_agendas.items():
        if keyword != "default" and keyword in role_lower:
            return agenda
    return stage_agendas.get("default", "Size up the stranger.")


def _derive_style_tags(location_id: str, scene_type: str, npc_refs: list[NPCRef]) -> list[str]:
    """Scene style from location keywords + NPC rhetorical style."""
    tags: list[str] = []
    loc_lower = (location_id or "").lower()
    for keyword, style_tags in _LOCATION_STYLE_TAGS.items():
        if keyword in loc_lower:
            tags.extend(style_tags)
            break

    # Add rhetorical style from first NPC voice_profile
    if npc_refs and npc_refs[0].voice_profile:
        rs = npc_refs[0].voice_profile.get("rhetorical_style", "")
        if rs and rs not in tags:
            tags.append(rs)

    return tags[:3]  # cap at 3


def _derive_pressure(world_state: dict) -> dict:
    """Alert/heat descriptors from world_state_json."""
    pressure: dict[str, str] = {}
    if not world_state or not isinstance(world_state, dict):
        return pressure

    # Check faction reputation for heat
    faction_rep = world_state.get("faction_reputation") or {}
    if isinstance(faction_rep, dict):
        min_rep = min(faction_rep.values()) if faction_rep else 0
        if isinstance(min_rep, (int, float)):
            if min_rep <= -50:
                pressure["heat"] = "Wanted"
            elif min_rep <= -20:
                pressure["heat"] = "Noticed"
            else:
                pressure["heat"] = "Low"

    # Check NPC states or faction memory for alert
    npc_states = world_state.get("npc_states") or {}
    hostile_count = sum(
        1 for ns in npc_states.values()
        if isinstance(ns, dict) and ns.get("disposition", "").lower() in ("hostile", "suspicious")
    )
    if hostile_count >= 3:
        pressure["alert"] = "Lockdown"
    elif hostile_count >= 1:
        pressure["alert"] = "Watchful"
    else:
        pressure["alert"] = "Quiet"

    return pressure


def _build_gm_context(
    player_objective: str,
    immediate_situation: str,
    arc_guidance: dict,
    world_state: dict,
    party_state: dict | None,
) -> str:
    """Build a compact GM context summary injected into Director and ChoiceCrafter.

    Produces a 5-6 line text block with what a real GM would keep in mind this turn:
    scene goal, arc stage, active threads, pending consequences, and companion tensions.
    """
    lines = ["== GM CONTEXT (this turn) =="]

    if immediate_situation:
        lines.append(f"Situation: {immediate_situation}")
    if player_objective:
        lines.append(f"Goal: {player_objective}")

    # Arc stage and active threads
    arc_stage = arc_guidance.get("arc_stage", "SETUP")
    tension = arc_guidance.get("tension_level", "CALM")
    priority_threads = arc_guidance.get("priority_threads") or []
    if priority_threads:
        threads_str = " | ".join(str(t) for t in priority_threads[:2])
        lines.append(f"Arc: {arc_stage} ({tension}) — {threads_str}")
    else:
        lines.append(f"Arc: {arc_stage} / Tension: {tension}")

    # Pending consequences from ledger
    ledger = world_state.get("ledger") or {} if isinstance(world_state, dict) else {}
    consequence_hints = (ledger.get("consequence_hints") or []) if isinstance(ledger, dict) else []
    if consequence_hints:
        hints_str = "; ".join(str(h) for h in consequence_hints[:2])
        lines.append(f"Pending: {hints_str}")

    # Companion tensions (low-influence companions are volatile)
    if party_state and isinstance(party_state, dict):
        companion_states = party_state.get("companion_states") or {}
        tense_comps = []
        if isinstance(companion_states, dict):
            for cid, cstate in companion_states.items():
                if isinstance(cstate, dict):
                    influence = int(cstate.get("influence", 0) or 0)
                    if influence < -10:
                        tense_comps.append(f"{cid} (hostile)")
                    elif influence < 20:
                        tense_comps.append(f"{cid} (wary)")
        if tense_comps:
            lines.append(f"Companion tension: {', '.join(tense_comps[:2])}")

    return "\n".join(lines)


def _build_voice_profile(npc: dict) -> dict:
    """Build a compact voice_profile dict from NPC data (era pack / companion).

    Keys: belief, wound, taboo, rhetorical_style, tell.
    """
    profile: dict[str, str] = {}

    motivation = npc.get("motivation") or ""
    secret = npc.get("secret") or ""
    voice_tags: list[str] = npc.get("voice_tags") or []
    traits: list[str] = npc.get("traits") or []

    if motivation:
        profile["belief"] = str(motivation)[:120]
    if secret:
        profile["wound"] = str(secret)[:120]

    # Taboo: infer from traits
    taboo_traits = {"secretive", "vengeful", "deceptive", "fanatical", "ruthless"}
    for t in traits:
        if t.lower().strip() in taboo_traits:
            profile["taboo"] = t.lower().strip()
            break

    # Rhetorical style from first voice_tag
    if voice_tags:
        first_tag = voice_tags[0].lower().strip()
        profile["rhetorical_style"] = _VOICE_TAG_RHETORICAL.get(first_tag, "direct")

        # Tell from voice_tag
        for tag in voice_tags:
            tell = _VOICE_TAG_TELLS.get(tag.lower().strip())
            if tell:
                profile["tell"] = tell
                break

    return profile

# Location humanizer (shared with narrator.py)
_LOCATION_NAMES: dict[str, str] = {
    "loc-cantina": "the cantina",
    "loc-tavern": "the cantina",
    "loc-marketplace": "the marketplace",
    "loc-market": "the marketplace",
    "loc-docking-bay": "the docking bay",
    "loc-docks": "the docking bay",
    "loc-lower-streets": "the lower streets",
    "loc-street": "the lower streets",
    "loc-hangar": "the hangar bay",
    "loc-spaceport": "the spaceport",
    "loc-command-center": "the command center",
    "loc-med-bay": "the med bay",
    "loc-jedi-temple": "the Jedi Temple",
}


def _humanize_location(loc_id: str) -> str:
    """Convert loc-id to readable name (e.g. loc-cantina → the cantina)."""
    if not loc_id:
        return "an unknown location"
    display = _LOCATION_NAMES.get(loc_id.lower().strip())
    if display:
        return display
    cleaned = loc_id
    for prefix in ("loc-", "loc_", "location-", "location_"):
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    cleaned = cleaned.replace("-", " ").replace("_", " ").strip()
    if not cleaned:
        return loc_id
    # Proper nouns (no prefix stripped + starts upper) get no article
    if not any(loc_id.lower().startswith(p) for p in ("loc-", "loc_")) and cleaned[0].isupper():
        return cleaned
    return f"the {cleaned}"


def _derive_scene_type(action_type: str) -> str:
    """Map mechanic action_type to scene_type."""
    upper = (action_type or "").upper()
    if upper in ("ATTACK", "COMBAT"):
        return "combat"
    if upper in ("STEALTH", "SNEAK"):
        return "stealth"
    if upper == "TRAVEL":
        return "travel"
    if upper in ("TALK", "DIALOGUE"):
        return "dialogue"
    return "exploration"


def _derive_situation(mechanic_result: dict | None, user_input: str) -> str:
    """Derive a 1-sentence immediate_situation from mechanic result."""
    if not mechanic_result:
        return user_input[:120].strip() if user_input else "Arriving at the scene."

    outcome = (mechanic_result.get("outcome_summary") or "").strip()
    facts = mechanic_result.get("narrative_facts") or []
    first_fact = facts[0].strip() if facts else ""

    if outcome and first_fact:
        return f"{outcome}. {first_fact}"[:200]
    if outcome:
        return outcome[:200]
    if first_fact:
        return first_fact[:200]
    return user_input[:120].strip() if user_input else "The scene unfolds."


def _derive_objective(user_input: str, action_class: str | None) -> str:
    """Derive player_objective from user_input."""
    if not user_input or user_input.startswith("["):
        # System-generated input (e.g. [OPENING_SCENE])
        return "Explore the surroundings and assess the situation."
    # Truncate to a single sentence
    text = user_input.strip()
    if len(text) > 120:
        text = text[:117].rstrip() + "..."
    return text


def _compute_scene_weight(
    *,
    arc_stage: str,
    world_state: dict[str, Any],
    mechanic_result: dict[str, Any] | None,
    state: dict[str, Any],
) -> str:
    """Classify scene weight used by narrator pacing and truncation limits."""
    beat = str(world_state.get("current_beat") or "").upper()
    stage = (arc_stage or "SETUP").upper()
    has_companion_event = bool(state.get("companion_event"))

    events = (mechanic_result or {}).get("events") or []
    has_combat = False
    for event in events:
        if isinstance(event, dict):
            etype = str(event.get("event_type") or event.get("type") or "").upper()
        else:
            etype = str(getattr(event, "event_type", "") or getattr(event, "type", "")).upper()
        if etype in {"COMBAT", "ATTACK", "DAMAGE"}:
            has_combat = True
            break

    if beat in {"ORDEAL", "RESURRECTION"} or stage == "CLIMAX":
        return "CLIMAX"
    if has_companion_event or has_combat or beat in {"APPROACH_INMOST_CAVE", "REWARD"}:
        return "ELEVATED"
    return "STANDARD"


def scene_frame_node(state: dict[str, Any]) -> dict[str, Any]:
    """Build SceneFrame from accumulated state. Pure Python, no side effects."""
    location_id = state.get("current_location") or ""
    location_name = _humanize_location(location_id)

    # Prefer authored location names and constraints from the era pack when available.
    try:
        campaign = state.get("campaign") or {}
        era_id = (campaign.get("time_period") or campaign.get("era") or state.get("era") or "REBELLION")
        pack = CONTENT_REPOSITORY.get_pack(str(era_id)) if era_id else None
        if pack and location_id:
            loc = pack.location_by_id(location_id)
            if loc and getattr(loc, "name", None):
                location_name = str(loc.name)
    except Exception:
        # SceneFrame must never fail due to pack load issues.
        pass

    # Build NPCRef list from present_npcs (V2.18: with voice_profile)
    raw_npcs = state.get("present_npcs") or []
    # Try to build era NPC lookup for voice profile data
    era_npc_lookup: dict[str, dict] = {}
    companion_lookup: dict[str, dict] = {}
    try:
        campaign = state.get("campaign") or {}
        era_id = (campaign.get("time_period") or campaign.get("era") or state.get("era") or "REBELLION")
        pack = CONTENT_REPOSITORY.get_pack(str(era_id)) if era_id else None
        if pack:
            for npc_entry in (getattr(pack, "npcs", None) or []):
                entry_dict = npc_entry.model_dump(mode="json") if hasattr(npc_entry, "model_dump") else (dict(npc_entry) if npc_entry else {})
                npc_id = entry_dict.get("id", "")
                npc_name = entry_dict.get("name", "")
                if npc_id:
                    era_npc_lookup[npc_id] = entry_dict
                if npc_name:
                    era_npc_lookup[npc_name] = entry_dict
        # Companion lookup
        try:
            from backend.app.core.companions import get_companion_by_id
            for npc in raw_npcs:
                cid = npc.get("id") or npc.get("character_id") or ""
                if cid.startswith("comp-"):
                    comp_data = get_companion_by_id(cid)
                    if comp_data:
                        companion_lookup[cid] = comp_data
                        cname = comp_data.get("name", "")
                        if cname:
                            companion_lookup[cname] = comp_data
        except Exception:
            pass

        # V2.20: Inject active party companions into present_npcs
        try:
            from backend.app.core.party_state import load_party_state
            ws = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
            if isinstance(ws, dict):
                party_st = load_party_state(ws)
                existing_ids = {(n.get("id") or n.get("character_id") or "") for n in raw_npcs}
                for cid in party_st.active_companions:
                    if cid in existing_ids:
                        continue
                    comp_data = get_companion_by_id(cid)
                    if comp_data:
                        companion_lookup[cid] = comp_data
                        cname = comp_data.get("name", "")
                        if cname:
                            companion_lookup[cname] = comp_data
                        raw_npcs.append({
                            "id": cid,
                            "name": cname or cid,
                            "role": comp_data.get("role_in_party", "companion"),
                        })
        except Exception:
            pass
    except Exception:
        pass

    npc_refs: list[NPCRef] = []
    for npc in raw_npcs:
        if isinstance(npc, dict) and npc.get("name"):
            npc_id = npc.get("id") or npc.get("character_id") or npc["name"]
            npc_name = npc["name"]
            # Build voice_profile from era pack or companion data
            enriched = era_npc_lookup.get(npc_id) or era_npc_lookup.get(npc_name) or companion_lookup.get(npc_id) or companion_lookup.get(npc_name) or npc
            voice_profile = _build_voice_profile(enriched)
            npc_refs.append(NPCRef(
                id=npc_id,
                name=npc_name,
                role=npc.get("role", "stranger"),
                voice_profile=voice_profile,
            ))

    # Mechanic context
    mechanic_result = state.get("mechanic_result")
    if mechanic_result and hasattr(mechanic_result, "model_dump"):
        mechanic_result = mechanic_result.model_dump(mode="json")
    elif mechanic_result and not isinstance(mechanic_result, dict):
        mechanic_result = dict(mechanic_result) if mechanic_result else {}

    action_type = (mechanic_result or {}).get("action_type", "") if mechanic_result else ""
    scene_type = _derive_scene_type(action_type)
    try:
        if action_type and str(action_type).upper() == "TRAVEL":
            scene_type = "travel"
        else:
            campaign = state.get("campaign") or {}
            era_id = (campaign.get("time_period") or campaign.get("era") or state.get("era") or "REBELLION")
            pack = CONTENT_REPOSITORY.get_pack(str(era_id)) if era_id else None
            if pack and location_id:
                loc = pack.location_by_id(location_id)
                allowed = list(getattr(loc, "scene_types", []) or [])
                if allowed:
                    # If derived type isn't allowed, fall back to first authored type.
                    if scene_type not in allowed:
                        scene_type = str(allowed[0])
    except Exception:
        logger.debug("Non-fatal: scene type derivation failed", exc_info=True)

    user_input = state.get("user_input") or ""
    action_class = state.get("action_class")

    immediate_situation = _derive_situation(mechanic_result, user_input)
    player_objective = _derive_objective(user_input, action_class)

    npc_ids = [ref.id for ref in npc_refs]
    scene_hash = compute_scene_hash(location_id, npc_ids, action_type)

    # Phase 5.3: Scene loop detection — track last 5 scene hashes
    recent_scene_hashes: list[str] = list(state.get("recent_scene_hashes") or [])
    recent_scene_hashes.append(scene_hash)
    # Keep only the last 5
    if len(recent_scene_hashes) > 5:
        recent_scene_hashes = recent_scene_hashes[-5:]
    # Detect loop: if the same hash appears 3+ times in the window
    scene_loop_detected = recent_scene_hashes.count(scene_hash) >= 3

    if scene_loop_detected:
        logger.info(
            "Scene loop detected: hash=%s appeared %d times in last %d turns",
            scene_hash,
            recent_scene_hashes.count(scene_hash),
            len(recent_scene_hashes),
        )

    # V2.18: KOTOR-soul topic/subtext/agenda derivation
    arc_guidance = state.get("arc_guidance") or {}
    arc_stage = arc_guidance.get("arc_stage", "SETUP")
    active_themes = arc_guidance.get("active_themes") or []

    topic_primary, topic_secondary = _derive_topic(npc_refs, scene_type, arc_stage, active_themes)
    subtext = _derive_subtext(topic_primary, arc_stage)

    npc_agenda = ""
    if npc_refs:
        npc_agenda = _derive_npc_agenda(npc_refs[0].role, arc_stage)

    style_tags = _derive_style_tags(location_id, scene_type, npc_refs)

    # Pressure from world_state
    campaign = state.get("campaign") or {}
    world_state = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
    if not isinstance(world_state, dict):
        world_state = {}
    pressure = _derive_pressure(world_state)

    # GM Context Object — compact unified summary for Director and ChoiceCrafter
    party_state = world_state.get("party_state") if isinstance(world_state, dict) else None
    gm_context = _build_gm_context(
        player_objective=player_objective,
        immediate_situation=immediate_situation,
        arc_guidance=arc_guidance,
        world_state=world_state,
        party_state=party_state if isinstance(party_state, dict) else None,
    )
    scene_weight = _compute_scene_weight(
        arc_stage=arc_stage,
        world_state=world_state,
        mechanic_result=mechanic_result if isinstance(mechanic_result, dict) else None,
        state=state,
    )

    choice_crafter_pre_context = {
        "location": location_id or "here",
        "npc_descriptions": [f"{ref.name} ({ref.role})" for ref in npc_refs],
        "topic_primary": topic_primary,
        "subtext": subtext,
        "npc_agenda": npc_agenda,
        "arc_stage": arc_stage,
        "tension_level": str(arc_guidance.get("tension_level", "")),
        "director_intent": str(state.get("director_instructions") or "")[:300],
        "gm_context": gm_context,
    }

    frame = SceneFrame(
        location_id=location_id,
        location_name=location_name,
        present_npcs=npc_refs,
        immediate_situation=immediate_situation,
        player_objective=player_objective,
        allowed_scene_type=scene_type,
        scene_hash=scene_hash,
        topic_primary=topic_primary,
        topic_secondary=topic_secondary,
        subtext=subtext,
        npc_agenda=npc_agenda,
        scene_style_tags=style_tags,
        pressure=pressure,
    )

    logger.debug(
        "SceneFrame built: location=%s, npcs=%d, type=%s, topic=%s, hash=%s",
        location_id,
        len(npc_refs),
        scene_type,
        topic_primary,
        scene_hash,
    )
    choice_crafter_pre_context["scene_frame"] = frame.model_dump(mode="json")

    updated = {
        **state,
        "scene_frame": frame.model_dump(mode="json"),
        "scene_weight": scene_weight,
        "gm_context": gm_context,
        "choice_crafter_pre_context": choice_crafter_pre_context,
        # Phase 5.3: Scene loop detection state
        "recent_scene_hashes": recent_scene_hashes,
        "scene_loop_detected": scene_loop_detected,
    }

    # V2.20: Attempt banter injection (uses scene_frame pressure for safety check)
    try:
        from backend.app.core.banter_manager import maybe_inject_banter
        updated, banter = maybe_inject_banter(updated)
        if banter:
            logger.debug("Banter injected: %s says: %s", banter.get("speaker"), banter.get("text", "")[:60])
    except Exception:
        logger.debug("Non-fatal: banter injection failed", exc_info=True)

    return updated
