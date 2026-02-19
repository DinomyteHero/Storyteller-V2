"""Narrator prompt construction helpers.

Functions that build the system/user prompts for the Narrator agent.
"""
from __future__ import annotations

import re
import logging

from backend.app.models.state import GameState
from backend.app.config import (
    get_role_max_input_tokens,
    get_role_reserved_output_tokens,
)
from backend.app.core.context_budget import BudgetReport, build_context
from backend.app.core.ledger import format_ledger_for_prompt
from backend.app.core.agent_utils import (
    format_lore_bullets,
    format_voice_snippets,
)

logger = logging.getLogger(__name__)

# Type aliases (duplicated here for self-containment; canonical definitions in narrator.py)
LoreChunk = dict
VoiceSnippet = dict


_GENERIC_LOCATION_NAMES: dict[str, str] = {
    "loc-cantina": "the tavern",
    "loc-tavern": "the tavern",
    "loc-marketplace": "the marketplace",
    "loc-market": "the marketplace",
    "loc-docking-bay": "the docks",
    "loc-docks": "the docks",
    "loc-lower-streets": "the lower streets",
    "loc-street": "the lower streets",
    "loc-hangar": "the hangar",
    "loc-spaceport": "the transit hub",
    "loc-command-center": "the command center",
    "loc-med-bay": "the infirmary",
}

_GENERIC_ATMOSPHERE_FRAGMENTS: dict[str, str] = {
    "opening": "The air{planet_str} carried the weight of recent events.",
    "ambient": "Background noise filled the space - voices, machinery, and the rhythm of daily life.",
    "tension": "Something felt wrong. The atmosphere tightened.",
    "calm": "For a moment, everything was still.",
    "hook": "The next chapter waited, just beyond the threshold.",
}

_SCENE_SENTENCE_GUIDANCE: dict[str, str] = {
    "STANDARD": "Write 5-8 vivid sentences.",
    "ELEVATED": "Write 6-10 vivid sentences. This is an important moment.",
    "CLIMAX": "Write 8-12 immersive, dramatic sentences. This is a pivotal moment in the story.",
}


def _get_era_pack(state: GameState):
    """Load the active era pack when possible."""
    from backend.app.content.repository import CONTENT_REPOSITORY

    campaign = getattr(state, "campaign", None) or {}
    era_id = (campaign.get("time_period") or campaign.get("era") or "").strip()
    if not era_id:
        return None
    try:
        return CONTENT_REPOSITORY.get_pack(era_id)
    except Exception:
        return None


def _resolve_location_name(loc_id: str, state: GameState | None = None) -> str:
    """Resolve a location ID to display text, preferring era-pack locations."""
    if state is not None:
        era_pack = _get_era_pack(state)
        if era_pack is not None:
            for loc in getattr(era_pack, "locations", []) or []:
                loc_ref = getattr(loc, "id", None) if not isinstance(loc, dict) else loc.get("id")
                if loc_ref == loc_id:
                    loc_name = getattr(loc, "name", None) if not isinstance(loc, dict) else loc.get("name")
                    if loc_name:
                        return str(loc_name)
    return _GENERIC_LOCATION_NAMES.get(loc_id.lower(), loc_id.replace("loc-", "").replace("-", " "))


def _get_atmosphere(state: GameState) -> dict[str, str]:
    """Load atmosphere fragments from era pack, with generic fallback."""
    era_pack = _get_era_pack(state)
    if era_pack is not None:
        fragments = getattr(era_pack, "atmosphere_fragments", None)
        if isinstance(fragments, dict) and fragments:
            return {**_GENERIC_ATMOSPHERE_FRAGMENTS, **fragments}
        if hasattr(fragments, "model_dump"):
            data = fragments.model_dump(mode="json")
            if isinstance(data, dict):
                return {**_GENERIC_ATMOSPHERE_FRAGMENTS, **data}
    return dict(_GENERIC_ATMOSPHERE_FRAGMENTS)


def _humanize_location(loc_id: str | None, state: GameState | None = None) -> str:
    """Convert a raw location ID into a narrative-friendly location name."""
    if not loc_id:
        return ""
    raw = loc_id.strip()
    if not raw:
        return ""
    display = _resolve_location_name(raw, state)
    if display and display != raw:
        return display
    cleaned = raw
    for prefix in ("loc-", "loc_", "location-", "location_"):
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    cleaned = cleaned.replace("-", " ").replace("_", " ").strip()
    if not cleaned:
        return raw
    words = cleaned.split()
    if len(words) == 1:
        return f"the {cleaned}"
    return cleaned.title()


def _scene_sentence_guidance(state: GameState) -> str:
    """Return scene-weight-sensitive sentence guidance for the narrator prompt."""
    weight = str(getattr(state, "scene_weight", None) or "STANDARD").upper()
    return _SCENE_SENTENCE_GUIDANCE.get(weight, _SCENE_SENTENCE_GUIDANCE["STANDARD"])

def _build_lore_query(state: GameState) -> str:
    """Build a lore retrieval query from location, user input, and mechanic summary."""
    parts = []
    loc = state.current_location
    if loc:
        parts.append(loc)
    user = (state.user_input or "").strip()
    if user:
        parts.append(user)
    if state.mechanic_result:
        parts.append(state.mechanic_result.action_type)
        for fact in (state.mechanic_result.narrative_facts or [])[:3]:
            parts.append(fact)
    return " ".join(parts) if parts else "setting scene"


def _summarize_mechanic_events(state: GameState) -> str:
    """Summarize mechanic_result events as facts for the narrator (no invention)."""
    if not state.mechanic_result or not state.mechanic_result.events:
        return "(No mechanical events this turn.)"
    lines = []
    for ev in state.mechanic_result.events:
        t = getattr(ev, "event_type", None) or (ev.get("event_type") if isinstance(ev, dict) else "")
        p = getattr(ev, "payload", None) or (ev.get("payload") if isinstance(ev, dict) else {}) or {}
        if t == "DAMAGE":
            amt = p.get("amount", 0)
            lines.append(f"You take {amt} damage.")
        elif t == "HEAL":
            amt = p.get("amount", 0)
            lines.append(f"You are healed for {amt}.")
        elif t == "MOVE" or t == "TRAVEL":
            to_loc = p.get("to_location", "")
            lines.append(f"You travel to {to_loc}.")
        elif t == "DIALOGUE":
            text = p.get("text", "")[:80]
            lines.append(f"Player said: {text}")
        else:
            lines.append(f"[{t}] {p}")
    return "\n".join(lines) if lines else "(No mechanical events this turn.)"


def _collect_character_ids(state: GameState) -> list[str]:
    """Collect character IDs for voice retrieval: present NPCs, party members, optionally player."""
    ids: list[str] = []
    seen: set[str] = set()
    npcs = state.present_npcs or []
    for n in npcs:
        cid = n.get("id")
        if cid and str(cid).strip() and cid not in seen:
            ids.append(str(cid).strip())
            seen.add(cid)
    campaign = state.campaign or {}
    party = campaign.get("party") or []
    for cid in party:
        if cid and str(cid).strip() and cid not in seen:
            ids.append(str(cid).strip())
            seen.add(cid)
    return ids


def _build_story_state_summary(state: GameState) -> str:
    """Build story state summary (never trimmed)."""
    loc = _humanize_location(state.current_location, state) or "the scene"
    campaign_id = state.campaign_id or ""
    npcs = state.present_npcs or []
    npc_names_list = [n.get("name") for n in npcs if n.get("name")]

    # V4.0: Load NPC narrative memory from world_state_json["npc_states"]
    campaign = state.campaign or {}
    ws = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
    npc_states: dict = (ws.get("npc_states") or {}) if isinstance(ws, dict) else {}

    # Build per-NPC lines with narrative memory injected
    from backend.app.core.agents.memory_agent import format_npc_memory_for_narrator
    npc_lines = []
    for n in npcs:
        name = n.get("name")
        if not name:
            continue
        role = n.get("role") or ""
        npc_id = n.get("id") or name.lower().replace(" ", "-")
        line = f"- {name} ({role})"
        # Inject narrative memory if available (try by id, then by name)
        mem_block = format_npc_memory_for_narrator(npc_id, npc_states) or \
                    format_npc_memory_for_narrator(name, npc_states)
        if mem_block:
            line = line + "\n" + mem_block
        npc_lines.append(line)

    if npc_lines:
        allowed_names_str = ", ".join(npc_names_list)
        npc_block = (
            f"ALLOWED NPC NAMES: {allowed_names_str}\n"
            + "\n".join(npc_lines)
            + "\nDo NOT use any character name not in this list. For unnamed background characters, describe them generically (e.g., 'a dock worker', 'the bartender')."
        )
    else:
        npc_block = "(No named NPCs present. Use only generic descriptions for any background characters.)"

    mechanic_summary = _summarize_mechanic_events(state)
    director_instructions = (state.director_instructions or "").strip() or "Keep pacing brisk. End with a decision point."
    # V2.15: Strip ALL suggestion-related guidance from Director instructions.
    # The Narrator writes prose only — it doesn't need suggestion context.
    director_instructions = re.sub(
        r"[^\n]*(?:Include|Consider|At least).*?[Ss]uggested?\s+(?:actions?|options?)[^\n]*\n?",
        "",
        director_instructions,
    )
    director_instructions = re.sub(
        r"\*{0,2}Suggested\s+[Aa]ctions?:?\*{0,2}\s*\n(?:(?!\n\n).)*",
        "",
        director_instructions,
        flags=re.DOTALL,
    )
    # Strip SUGGESTION CONTEXT sections entirely (no longer needed by Narrator)
    director_instructions = re.sub(
        r"## SUGGESTION CONTEXT[^\n]*\n(?:(?!##).)*",
        "",
        director_instructions,
        flags=re.DOTALL,
    )
    director_instructions = re.sub(r"\n{3,}", "\n\n", director_instructions).strip()
    if not director_instructions:
        director_instructions = "Keep pacing brisk. End with a decision point."

    # V2.5: Character psych_profile for tone
    psych = {}
    if state.player and getattr(state.player, "psych_profile", None):
        psych = state.player.psych_profile or {}
    current_mood = psych.get("current_mood", "neutral")
    stress_level = int(psych.get("stress_level", 0) or 0)
    psych_block = (
        f"current_mood: {current_mood}, stress_level: {stress_level}, "
        f"active_trauma: {psych.get('active_trauma') or 'none'}"
    )
    # V4.0: Inject emotional_arc_note from PsychArchivistAgent when available
    _emotional_arc_note = ws.get("emotional_arc_note") if isinstance(ws, dict) else None
    if _emotional_arc_note:
        psych_block += f"\nDirector note: {_emotional_arc_note}"

    # V2.5: Active rumors (last 3 is_public_rumor events)
    active_rumors = getattr(state, "active_rumors", None) or []
    rumors_block = "\n".join(f"- {r}" for r in active_rumors[:3]) if active_rumors else "(No recent public rumors.)"

    ledger = {}
    campaign = state.campaign or {}
    ws = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
    if isinstance(ws, dict):
        ledger = ws.get("ledger") or {}
    ledger_block = format_ledger_for_prompt(ledger)

    # V4.0: Dynamic quest hooks — surface active dynamic quests to Director/Narrator
    dynamic_quests_block = ""
    if isinstance(ws, dict):
        _dq = ws.get("dynamic_quests") or []
        if _dq:
            from backend.app.core.agents.quest_weaver_agent import format_dynamic_quests_for_prompt  # noqa: E402
            dynamic_quests_block = format_dynamic_quests_for_prompt(_dq)

    # V2.5: Open threads for narrative continuity
    open_threads = ledger.get("open_threads") or []
    if open_threads:
        threads_block = "\n".join(f"- {t}" for t in open_threads[:2])
    else:
        threads_block = "(No open threads.)"

    # V2.5: Critical outcome from mechanic
    critical_outcome_block = ""
    if state.mechanic_result:
        co = getattr(state.mechanic_result, "critical_outcome", None)
        if co == "CRITICAL_FAILURE":
            critical_outcome_block = (
                "## Critical Outcome\n"
                "CRITICAL FAILURE. Narrate dramatic consequences, complications, and environmental changes.\n\n"
            )
        elif co == "CRITICAL_SUCCESS":
            critical_outcome_block = (
                "## Critical Outcome\n"
                "CRITICAL SUCCESS. Narrate exceptional success with bonus effects.\n\n"
            )

    # V2.5: Explicit constraints and established facts
    constraints_list = ledger.get("constraints") or []
    facts_list = (ledger.get("established_facts") or [])[:5]
    constraints_line = ", ".join(constraints_list) if constraints_list else "(none)"
    facts_line = ", ".join(facts_list) if facts_list else "(none)"

    # Build recent narrative recap for continuity
    recent_narrative = getattr(state, "recent_narrative", None) or []
    if recent_narrative:
        narrative_recap = "\n\n".join(recent_narrative[-2:])  # last 2 turns max
    else:
        narrative_recap = "(This is the beginning of the story.)"

    # V2.6: POV character block (identity grounding for narrative perspective)
    pov_block = ""
    if state.player:
        player_name = state.player.name or "the protagonist"
        player_bg = getattr(state.player, "background", None) or ""
        pov_block = f"## POV Character\nName: {player_name}."
        if player_bg:
            pov_block += f" {player_bg}"
        # V2.8: Pronoun injection for gender-correct narration
        player_gender = getattr(state.player, "gender", None)
        if player_gender:
            from backend.app.core.pronouns import pronoun_block as _pronoun_block
            _pblock = _pronoun_block(player_name, player_gender)
            if _pblock:
                pov_block += f"\n{_pblock}"
        pov_block += (
            "\nWrite from this character's perspective — what THEY see, hear, sense, and feel. "
            "Ground every scene in their viewpoint. The reader experiences the world through their eyes."
        )
        # V2.7: Grammar check for confusing character names
        if player_name in ["Hero", "Protagonist", "Player", "Character"]:
            pov_block += (
                f"\n\nGRAMMAR NOTE: The character's name is '{player_name}'. "
                f"When writing dialogue, use it as a proper noun: 'You in, {player_name}?' NOT 'You {player_name}?'. "
                f"In narration, use: '{player_name} noticed...' NOT 'You {player_name}...'"
            )
        # V2.7: Player agency hard rule
        pov_block += (
            "\n\n## PLAYER AGENCY (HARD RULE)\n"
            "NEVER narrate the player character taking actions without player input. "
            "Describe what they PERCEIVE, HEAR, SENSE — not what they DO. "
            "Example GOOD: 'Corran felt the weight of the blaster at his hip.'\n"
            "Example BAD: 'Corran drew his blaster and fired.'\n"
            "End scenes with a MOMENT (sensory detail, NPC reaction, environment change), "
            "not an action the player hasn't chosen."
        )
        pov_block += "\n\n"

    # V2.10: Starship context for transport-aware narration
    _starship = getattr(state, "player_starship", None)
    if _starship and _starship.get("has_starship"):
        _ship_type = _starship.get("ship_type", "their ship")
        starship_block = f"Player's starship: {_ship_type}. They can pilot it and travel freely."
    else:
        starship_block = "Player has NO starship. Off-planet travel requires hiring passage, stowing away, or NPC transport."

    result = (
        f"## Story So Far (CRITICAL — your prose MUST continue from this)\n"
        f"{narrative_recap}\n\n"
        f"{pov_block}"
        f"## Campaign / Location\n"
        f"Campaign: {campaign_id}\n"
        f"Location: {loc}\n"
        f"{starship_block}\n\n"
        f"## Narrative Ledger (HARD CONSTRAINTS -- must obey)\n"
        f"{ledger_block}\n"
        f"CONSTRAINTS (MUST NOT CONTRADICT): {constraints_line}\n"
        f"ESTABLISHED FACTS (treat as canon): {facts_line}\n"
        f"If you are unsure about a fact, phrase it as rumor/speculation. Never contradict established facts.\n\n"
        f"## Open threads (reference 1-2 subtly to maintain continuity)\n"
        f"{threads_block}\n\n"
        + (f"{dynamic_quests_block}\n\n" if dynamic_quests_block else "")
        + f"## Character psych_profile (use for tone)\n"
        f"{psych_block}\n\n"
        f"## Present NPCs (ONLY these characters exist in this scene)\n"
        f"{npc_block}\n\n"
    )
    # 2.5: Background figures for atmosphere
    bg_figures = getattr(state, "background_figures", None) or []
    if bg_figures:
        bg_lines = "\n".join(f"- {f}" for f in bg_figures[:3])
        result += (
            f"## Background Figures (atmosphere only — NOT interactable, do NOT name them)\n"
            f"{bg_lines}\n"
            f"Mention 1-2 of these in passing to make the scene feel populated. They are scenery, not characters.\n\n"
        )
    result += (
        f"## Mechanic outcome (events--treat as facts)\n"
        f"{mechanic_summary}\n\n"
        f"{critical_outcome_block}"
        f"## Director instructions\n"
        f"{director_instructions}\n\n"
    )
    # Companion reactions block (1.2): inject companion emotional state into narration context
    companion_reactions_block = ""
    if isinstance(campaign, dict):
        cr_summary = campaign.get("companion_reactions_summary") or ""
        if cr_summary:
            companion_reactions_block = (
                f"## Companion Reactions This Turn\n"
                f"{cr_summary}\n"
                f"Weave companion reactions naturally into the scene — show them through body language, "
                f"facial expressions, and brief dialogue. Do NOT list them mechanically.\n\n"
            )
    result += companion_reactions_block
    # 3.2: Inter-party tensions block (companions at odds with each other)
    tensions_narrator = ""
    if isinstance(campaign, dict):
        tensions_narrator = campaign.get("inter_party_tensions_narrator") or ""
    if tensions_narrator:
        result += (
            f"## Inter-Party Tensions\n"
            f"{tensions_narrator}\n"
            f"Show this tension through body language or brief exchanges between companions.\n\n"
        )

    result += (
        f"## Active rumors (reference subtly if appropriate; do not derail scene)\n"
        f"{rumors_block}\n\n"
    )
    # Phase 3: Active themes for thematic resonance
    active_themes = ledger.get("active_themes") or []
    if active_themes:
        theme_names = ", ".join(t.replace("_", " ") for t in active_themes[:3])
        result += (
            f"## Active themes (weave subtly into prose)\n"
            f"{theme_names}\n\n"
        )

    # V2.18: Scene context for KOTOR-soul depth (topic anchoring, NPC agenda, subtext)
    scene_frame = getattr(state, "scene_frame", None) or {}
    if isinstance(scene_frame, dict):
        topic = scene_frame.get("topic_primary", "")
        topic_secondary = scene_frame.get("topic_secondary", "")
        subtext = scene_frame.get("subtext", "")
        npc_agenda = scene_frame.get("npc_agenda", "")
        style_tags = scene_frame.get("scene_style_tags") or []
        pressure = scene_frame.get("pressure") or {}
        if topic or subtext or npc_agenda:
            result += "## Scene Context (V2.18 — KOTOR-soul depth)\n"
            if topic:
                topic_line = topic
                if topic_secondary:
                    topic_line += f" / {topic_secondary}"
                result += f"- Topic: {topic_line}\n"
            if subtext:
                result += f"- Subtext (what this scene is REALLY about): {subtext}\n"
            if npc_agenda:
                result += f"- NPC Agenda (what the NPC wants from the player): {npc_agenda}\n"
            if style_tags:
                result += f"- Scene Style: {', '.join(style_tags)}\n"
            if pressure:
                alert = pressure.get("alert", "")
                heat = pressure.get("heat", "")
                if alert or heat:
                    parts = []
                    if alert:
                        parts.append(f"Alert: {alert}")
                    if heat:
                        parts.append(f"Heat: {heat}")
                    result += f"- Pressure: {' | '.join(parts)}\n"
            result += (
                "Use this context to guide NPC dialogue tone and topic. "
                "The NPC's spoken line (after ---NPC_LINE---) MUST relate to the topic above.\n\n"
            )

        # V2.18: Voice profile for present NPCs
        present_npcs = scene_frame.get("present_npcs") or []
        voice_profiles = []
        for npc in present_npcs:
            vp = npc.get("voice_profile") or {}
            if vp:
                name = npc.get("name", "Unknown")
                vp_parts = []
                if vp.get("belief"):
                    vp_parts.append(f"Belief: {vp['belief']}")
                if vp.get("wound"):
                    vp_parts.append(f"Wound: {vp['wound']}")
                if vp.get("taboo"):
                    vp_parts.append(f"Taboo: {vp['taboo']}")
                if vp.get("rhetorical_style"):
                    vp_parts.append(f"Style: {vp['rhetorical_style']}")
                if vp.get("tell"):
                    vp_parts.append(f"Tell: {vp['tell']}")
                if vp_parts:
                    voice_profiles.append(f"- {name}: {'; '.join(vp_parts)}")
        if voice_profiles:
            result += "## NPC Voice Profiles (use to shape NPC dialogue)\n"
            result += "\n".join(voice_profiles) + "\n"
            result += "When writing the NPC's spoken line, use their 'Tell' as a physical mannerism and their 'Style' for rhetorical approach.\n\n"

    result += "Write the narrative."
    return result


def _build_prompt(
    state: GameState,
    lore_chunks: list[LoreChunk] | str,
    voice_snippets_by_char: dict[str, list] | str,
    include_budget: bool = False,
    kg_context: str = "",
    style_chunks: list[dict] | None = None,
) -> tuple[str, str] | tuple[str, str, BudgetReport]:
    """Build system and user prompt sections using ContextBudget."""
    # Detect opening scene: first turn with no/minimal history
    is_opening = not (state.history or []) or len(state.history or []) <= 1
    opening_tag = "[OPENING_SCENE]" in (state.user_input or "")
    is_opening_scene = is_opening or opening_tag

    # V3.2: Extract setting_rules for universe-aware faction examples
    from backend.app.core.setting_context import get_setting_rules
    _sr = get_setting_rules(state.model_dump(mode="json") if hasattr(state, "model_dump") else (state if isinstance(state, dict) else {}))
    _faction_examples = ", ".join(_sr.example_factions) if _sr.example_factions else "various factions"
    _genre = (_sr.setting_genre or "speculative").strip()
    if _genre.lower() == "science fantasy":
        _voice_reference = "Channel Kreia, Atton, Jolee Bindo."
    else:
        _voice_reference = f"Channel the narrative voice of classic {_genre} fiction."

    sentence_guidance = _scene_sentence_guidance(state)

    # V2.15: Narrator writes ONLY prose. Suggestions are generated deterministically
    # by the Director node using generate_suggestions() — no LLM involvement.
    _prose_stop_rule = (
        "\n\n--- CRITICAL OUTPUT RULES ---\n"
        "STOP RULE: Write ONLY narrative prose. Your output is COMPLETE when the last sentence ends.\n"
        "- Do NOT add numbered lists, bullet points, or player options after the prose.\n"
        "- Do NOT continue past the current moment. NEVER write 'Scene Continuation' or 'Next Steps'.\n"
        "- Do NOT include character sheets, personality descriptions, voice descriptions, or stat blocks.\n"
        "- Do NOT write 'Regardless of player choice', 'Potential Complications', or meta-game analysis.\n"
        "- Do NOT embed options like 'Option 1:' or decision questions like 'Do you accept?'\n"
        "- Do NOT address the player as 'Hero' or end with 'What will you do?' or 'The choice is yours.'\n"
        "- Do NOT echo instructions from your system prompt. Never write 'Begin with a sensory-rich description' or similar self-instructions.\n"
        "- End on an evocative sensory moment — a sound, a look, a shift in atmosphere.\n"
        "\n--- NPC DIALOGUE OUTPUT (REQUIRED) ---\n"
        "After your prose, add the separator ---NPC_LINE--- on its own line,\n"
        "then write 1-4 lines of focused NPC dialogue from the most relevant NPC in the scene.\n"
        "This is what the NPC says TO or NEAR the player character — their spoken words.\n"
        "If no NPC is present, write a narrator observation instead.\n\n"
        "KOTOR VOICE RULES:\n"
        "- The NPC speaks with PURPOSE. Every line has an AGENDA (stated in scene context as 'NPC Agenda').\n"
        "- Apply ONE rhetorical move: probe (ask a pointed question), challenge (dispute an assumption),\n"
        "  reframe (offer a different lens), warn (hint at consequences), or reveal (share something personal).\n"
        "- Include ONE 'tell' — a repeated mannerism (a pause, a gesture, a speech pattern) that makes the NPC feel real.\n"
        "  Examples: 'pauses before answering', 'jaw tightens', 'eyes narrow', 'voice drops half a register'.\n"
        f"- The dialogue should make the player THINK, not just react. {_voice_reference}\n"
        "- Philosophical depth comes from SUBTEXT, not length. 1-4 lines max.\n"
        "- The NPC must speak ON TOPIC (the scene's topic from context).\n"
        "- Do NOT repeat information already in the prose — the dialogue should ADD something new.\n\n"
        "FORMAT:\n"
        "[Your prose paragraphs here]\n"
        "---NPC_LINE---\n"
        "SPEAKER: {NPC name from Present NPCs list, or 'Narrator' if no NPCs}\n"
        "\"{What the NPC says aloud — on topic, with subtext}\"\n\n"
        "RULES:\n"
        "- The SPEAKER must be an NPC from the '## Present NPCs' list, or 'Narrator'.\n"
        "- Match the NPC's voice (accent, vocabulary, mannerisms) from voice snippets if available.\n"
        "AFTER THE NPC LINE, STOP. WRITE NOTHING ELSE."
    )

    if is_opening_scene:
        system = (
            "You are the narrator for a story game. THIS IS THE OPENING SCENE — the very first moment the player experiences.\n\n"
            "PERSPECTIVE: Write in close third-person POV through the player character (see 'POV Character' in context). "
            "Everything is filtered through THEIR senses and emotions. Use their name. "
            "Example: 'Tycho felt the heat of the room hit him as he stepped inside.' NOT 'The room was hot.'\n\n"
            "Your job is to write a CINEMATIC INTRODUCTION that:\n"
            "1. ORIENTS THE PLAYER FIRST: Before anything happens, ground them. Where are they? What do they see and feel? "
            "Start with atmosphere and location — the player needs to know where they are before things happen.\n"
            "2. INTRODUCES NPCS NATURALLY: When an NPC appears, briefly describe them visually. "
            "Example: 'A scarred figure in a worn jacket leaned against the bar - an officer, by the look of the insignia.' "
            "Do NOT reference NPCs by name as if the player already knows them, unless the backstory says they do.\n"
            "3. CREATES A HOOK: Something happens that invites the player to act. Keep it simple — a conversation overheard, "
            "a figure approaching, a problem visible in the scene.\n"
            "4. DOES NOT ASSUME PLAYER ACTIONS: Describe what they perceive, not what they do. End with a moment that invites a choice. "
            "NEVER narrate the player character taking actions without player input — describe what they sense, not what they decide.\n"
            f"5. {sentence_guidance} Keep it grounded - this is the BEGINNING, not the middle of an action sequence.\n"
            "6. Write as flowing prose paragraphs (2-3 paragraphs, separated by blank lines). "
            "Do NOT split the narrative into labeled sections like "
            "'Scene Description:' or 'Suggested Actions:'. Blend setting, atmosphere, character motivation, "
            "NPC introductions, and tension into ONE flowing narrative. Think: the opening page of a novel, "
            "not a game manual with headers.\n\n"
            "PLAYER BACKGROUND: The POV Character section contains the character's background. "
            "Reference it subtly: if they come from the underworld, the opening should feel like THEIR "
            "underworld. If they lost someone, hint at that weight. Don't state it outright — "
            "let the atmosphere reflect their past.\n\n"
            "--- HARD RULES ---\n"
            "- OUTPUT FORMAT: Write ONLY narrative prose. Plain text paragraphs separated by blank lines.\n"
            "  Do NOT use markdown headers (**, ##), JSON, code blocks, section labels, or any structural formatting.\n"
            "  Do NOT write 'Scene:', 'Narrative:', 'Next Turn:', 'Opening:', or any labels.\n"
            "  Just write the story as flowing prose paragraphs.\n"
            "- NPC NAMES: You may ONLY use NPC names listed in '## Present NPCs'. "
            "Do NOT invent, hallucinate, or reference ANY character names not in that list. "
            "If you need an unnamed background character, describe them by appearance or role "
            "(e.g., 'a dock worker', 'the bartender', 'a passing spacer').\n"
            "- FACTION NEUTRALITY: Do NOT assume the player's allegiance. The player may choose to side "
            f"with ANY faction ({_faction_examples}, independent). Narrate the world "
            "as presenting opportunities from multiple sides. Do not frame one faction as 'the good guys'.\n"
            "  * BAD: 'Captain Vale, from wanted posters' (assumes hostility)\n"
            "  * GOOD: 'an officer - Captain Vale, by the rank insignia'\n"
            "  * BAD: 'the freedom fighter Hero trusted' (assumes sympathy)\n"
            "  * GOOD: 'a smuggler Hero had crossed paths with before'\n"
            "- LORE: Use the provided lore context to enrich the scene. If lore context is empty, do NOT claim canon facts; use atmosphere and sensory detail instead.\n"
            "- VOICE: When characters speak, match their voice to provided voice snippets if available.\n"
            "- Do NOT mention game mechanics, dice rolls, or mechanical outcomes in the opening.\n"
            "- STYLE: If style directives are provided, use them to shape prose rhythm, atmosphere, and sensory detail.\n\n"
            "--- CYOA PROSE STYLE ---\n"
            "Write as if this is a page in a Choose Your Own Adventure novel. "
            "Use vivid second-person-adjacent close-third POV — the reader IS the character. "
            "End the scene on a beat of tension or mystery — an evocative IMAGE, not a decision menu. "
            "A door creaking open, a shadow moving at the edge of vision, a hand drifting to a weapon. "
            "NEVER present numbered options, lettered choices, or dialogue menus inside the prose. "
            "The reader should FEEL the tension, not be handed a list."
        ) + _prose_stop_rule
    else:
        system = (
            "You are the narrator for an ongoing story game. You are writing the NEXT CHAPTER of a continuous narrative.\n\n"
            "PERSPECTIVE: Write in close third-person POV through the player character (see 'POV Character' in context). "
            "Everything is filtered through THEIR senses — what they see, hear, smell, feel. Use their name. "
            "The reader experiences the world as this character. Never break POV.\n\n"
            "NARRATIVE CONTINUITY (CRITICAL):\n"
            "- The 'Story So Far' section contains the actual prose from recent turns. Your text MUST read as a natural continuation.\n"
            "- Reference what happened before: if the player talked to someone, acknowledge the conversation. If they moved, describe arriving.\n"
            "- Maintain consistent tone, setting details, and character behavior across turns.\n"
            "- The player should feel like they're reading a novel, not a series of disconnected scenes.\n\n"
            "RULES:\n"
            "1. GROUNDING (STRICT): You MUST only narrate based on MechanicResult and the event log. Do NOT invent success/failure or outcomes.\n"
            "2. If the mechanic outcome indicates the action was invalid or unclear, ask the player to rephrase.\n"
            "3. PLAYER AGENCY (CRITICAL): NEVER narrate the player character taking actions they didn't choose. "
            "Describe what they perceive, sense, feel — not what they decide or do next. "
            "End with a MOMENT (sensory detail, NPC reaction, environment change), not an action the player hasn't chosen.\n"
            "4. LORE: Use the provided lore context to enrich the scene. If lore context is empty or missing, do NOT claim canon facts.\n"
            "5. TONE: Adjust tone based on character's current_mood and stress_level. High stress (>7) = shorter sentences, sensory overload. Low stress = more reflective prose.\n"
            "6. RUMORS: Subtly reference background rumors if appropriate, but do not derail the scene.\n"
            "7. VOICE: When characters speak, match their voice to provided voice snippets if available.\n"
            f"8. {sentence_guidance} End with an evocative moment.\n"
            "9. Write as flowing prose paragraphs (2-3 paragraphs, separated by blank lines). "
            "Never split output into sections, headers, or labeled blocks. "
            "The narrative should read like a page from a novel: setting, consequences, NPC reactions, and tension "
            "woven into flowing prose. No 'Scene Description:', no 'Suggested Actions:', no structural labels.\n\n"
            "PARAGRAPH STRUCTURE (follow this rhythm):\n"
            "- Lead with a sensory hook (what the character perceives FIRST — a sound, a smell, a visual detail)\n"
            "- Develop the scene (NPC reactions, environmental details, consequences unfolding)\n"
            "- End with forward momentum (a question raised, tension introduced, or a change in the situation)\n"
            "Do NOT end with a summary or restatement. End on something that makes the player want to act.\n\n"
            "NPC REACTIONS (CRITICAL):\n"
            "- NPCs are NOT robots. When something significant happens, show their EMOTIONAL response.\n"
            "- Use body language, facial expressions, voice tone: 'Her jaw tightened', 'His hand drifted to his weapon', "
            "'A nearby ally let out a low growl', 'A confident smile faltered for just a moment'.\n"
            "- If the player confronts someone, show them reacting — flinching, going pale, getting angry, stepping back.\n"
            "- If an NPC offers a deal, show investment: leaning forward, lowering voice, glancing around nervously.\n"
            "- If surprised, show SURPRISE — widened eyes, a sharp intake of breath, stumbling over words.\n\n"
            "MECHANIC ACTION NARRATION (CRITICAL):\n"
            "- When the MechanicResult reports an action (attack, sneak, persuade, intimidate), you MUST narrate the action itself.\n"
            "- COMBAT: describe the fight - weapon fire, ducking behind cover, the crack of impact, adrenaline.\n"
            "- STEALTH failure: describe getting caught — a guard turns, a spotlight catches them, a door alarm triggers.\n"
            "- INTIMIDATION: describe the confrontation — getting in someone's face, slamming a fist on a table, the room going quiet.\n"
            "- Do NOT skip the action and jump to aftermath. Show the MOMENT of action as it unfolds.\n\n"
            "--- HARD RULES ---\n"
            "- OUTPUT FORMAT: Write ONLY narrative prose. Plain text paragraphs separated by blank lines.\n"
            "  Do NOT use markdown headers (**, ##), JSON, code blocks, section labels, or any structural formatting.\n"
            "  Do NOT write 'Scene:', 'Narrative:', 'Next Turn:', 'Opening:', or any labels.\n"
            "  Just write the story as flowing prose paragraphs.\n"
            "- NPC NAMES: You may ONLY use NPC names listed in '## Present NPCs'. "
            "Do NOT invent, hallucinate, or reference ANY character names not in that list. "
            "If you need an unnamed background character, describe them by appearance or role "
            "(e.g., 'a dock worker', 'the bartender', 'a passing spacer').\n"
            "- FACTION NEUTRALITY: Do NOT assume the player's allegiance. The player may choose to side "
            f"with ANY faction ({_faction_examples}, independent). Narrate the world "
            "as presenting opportunities from multiple sides. Do not frame one faction as 'the good guys'.\n"
            "  * BAD: 'Captain Vale, from wanted posters' (assumes hostility)\n"
            "  * GOOD: 'an officer - Captain Vale, by the rank insignia'\n"
            "  * BAD: 'the freedom fighter Hero trusted' (assumes sympathy)\n"
            "  * GOOD: 'a smuggler Hero had crossed paths with before'\n"
            "- Only describe outcomes from Mechanic as facts. Do not invent mechanical results.\n"
            "- Only state character-history specifics if those facts appear in retrieved voice/lore citations. Otherwise, phrase uncertainty.\n"
            "- Prefer era-specific phrasing and voice guidance from voice snippets when available.\n"
            "- STYLE: If style directives are provided, use them to shape prose rhythm, atmosphere, and sensory detail.\n\n"
            "--- CYOA PROSE STYLE ---\n"
            "Write as if this is a page in a Choose Your Own Adventure novel. "
            "Use vivid second-person-adjacent close-third POV — the reader IS the character. "
            "End the scene on a beat of tension or mystery — an evocative IMAGE, not a decision menu. "
            "A door creaking open, a shadow moving at the edge of vision, a hand drifting to a weapon. "
            "NEVER present numbered options, lettered choices, or dialogue menus inside the prose. "
            "The reader should FEEL the tension, not be handed a list."
        ) + _prose_stop_rule

    story_state_summary = _build_story_state_summary(state)
    recent_history = state.history or []

    empty_voice_text = format_voice_snippets({}, "(No character voice samples available.)")
    empty_lore_text = format_lore_bullets([], "(No lore context--phrase uncertain information as rumor or possibility.)")
    if isinstance(lore_chunks, str):
        empty_lore_text = lore_chunks
        lore_chunks = []
    if isinstance(voice_snippets_by_char, str):
        empty_voice_text = voice_snippets_by_char
        voice_snippets_by_char = {}

    max_input_tokens = get_role_max_input_tokens("narrator")
    reserve_output_tokens = get_role_reserved_output_tokens("narrator")
    parts = {
        "system": system,
        "state": story_state_summary,
        "history": recent_history,
        "era_summaries": state.era_summaries or [],
        "lore_chunks": lore_chunks,
        "style_chunks": style_chunks or [],
        "voice_snippets": voice_snippets_by_char,
        "kg_context": kg_context,
        "user_input": state.user_input or "",
    }
    messages, budget_report = build_context(
        parts,
        max_input_tokens=max_input_tokens,
        reserve_output_tokens=reserve_output_tokens,
        role="narrator",
        max_voice_snippets_per_char=2,
        min_lore_chunks=1,
        user_input_label="User input:",
        empty_voice_text=empty_voice_text,
        empty_lore_text=empty_lore_text,
    )
    system_prompt_final = messages[0]["content"]
    user_prompt = messages[1]["content"]

    if include_budget:
        return system_prompt_final, user_prompt, budget_report
    return system_prompt_final, user_prompt

