"""Director agent: plans tone, pacing, POV and suggests multiple next actions for the UI."""
from __future__ import annotations

from typing import Callable

import logging

from backend.app.models.state import ActionSuggestion, GameState
from backend.app.core.agents.base import AgentLLM
from backend.app.core.agent_utils import call_retriever, collect_related_npc_ids
from backend.app.core.context_budget import build_context
from backend.app.core.director_validation import (
    LoreChunk,
    StyleChunk,
    adventure_hooks_from_lore,
    build_era_factions_companions_context,
    build_style_query,
    directives_from_style_context,
    sanitize_instructions_for_narrator,
    style_context_from_chunks,
)
from backend.app.core.warnings import add_warning
from backend.app.config import get_role_max_input_tokens, get_role_reserved_output_tokens
from backend.app.content.repository import CONTENT_REPOSITORY

logger = logging.getLogger(__name__)


class DirectorAgent:
    """Produces director_instructions and suggested ActionSuggestion options (padded to UI target)."""

    def __init__(
        self,
        llm: AgentLLM | None = None,
        style_retriever: Callable[[str, int], list[StyleChunk]] | None = None,
        lore_retriever: Callable[..., list[LoreChunk]] | None = None,
    ) -> None:
        self._llm = llm
        self._style_retriever = style_retriever
        self._lore_retriever = lore_retriever

    def _build_instructions(self, state: GameState, arc_guidance: dict | None = None) -> tuple[str, str, list[StyleChunk], list[LoreChunk], set[str]]:
        """Build director instructions and prompt context.

        Returns:
            (director_instructions, story_state_summary, style_chunks, lore_chunks, allowed_entities)
        """
        style_chunks: list[StyleChunk] = []
        style_context = ""
        warnings_list = getattr(state, "warnings", None)
        campaign = getattr(state, "campaign", None) or {}
        era_id = campaign.get("time_period") or campaign.get("era") or None
        genre = campaign.get("genre") or None
        archetype = campaign.get("archetype") or None
        if self._style_retriever is not None:
            query = build_style_query(state)
            style_chunks = call_retriever(self._style_retriever, query, 5, era_id=era_id, genre=genre, archetype=archetype, warnings=warnings_list)
            style_context = style_context_from_chunks(style_chunks, max_chars=1200)

        lore_chunks: list[LoreChunk] = []
        adventure_hooks = ""
        if self._lore_retriever is not None:
            era = (era_id or "REBELLION") or "REBELLION"
            query = build_style_query(state)
            related_ids = collect_related_npc_ids(state)
            lore_chunks = call_retriever(
                self._lore_retriever,
                query,
                4,
                era,
                related_npcs=related_ids if related_ids else None,
                warnings=warnings_list,
            )
            if related_ids and not lore_chunks:
                lore_chunks = call_retriever(self._lore_retriever, query, 4, era, warnings=warnings_list)
            adventure_hooks = adventure_hooks_from_lore(lore_chunks, max_chars=800)

        # Detect opening scene: first turn with no history
        is_opening = not (state.history or []) or len(state.history or []) <= 1
        opening_tag = "[OPENING_SCENE]" in (state.user_input or "")
        is_opening_scene = is_opening or opening_tag

        if is_opening_scene:
            base = (
                "THIS IS THE OPENING SCENE. The player has just entered the world for the first time. "
                "Your job is to SET THE STAGE:\n"
                "- Establish the setting: WHERE are they? What does it look, sound, smell like?\n"
                "- Establish the MOOD and ATMOSPHERE of the era.\n"
                "- Hint at what's happening in the world (political tension, war, opportunity).\n"
                "- Give the player a reason to act: a hook, an NPC approach, an overheard conversation, a complication.\n"
                "- Do NOT reference the player's 'objective' or 'mission' — they just arrived. Let them discover it.\n"
                "- NPC NAMES: The player does NOT know these people yet. Use descriptive labels, "
                "not bare names. Say 'the scarred pilot at the bar' or 'the hooded figure', "
                "not 'Damar'. The NPC name can appear in parentheses for internal tracking.\n"
                "Use cinematic sensory detail. End with a moment that invites the player to engage."
            )
        else:
            base = "Keep pacing brisk. Use cinematic sensory detail. End with a decision point."
        psych = {}
        if state.player and getattr(state.player, "psych_profile", None):
            psych = state.player.psych_profile or {}
        stress_level = int(psych.get("stress_level", 0) or 0)
        active_trauma = psych.get("active_trauma") or "none"
        base += (
            f" Character psych_profile: stress_level={stress_level}, active_trauma={active_trauma}. "
            "Monitor the stress_level. If it is low and the scene is stagnant, introduce a complication that specifically targets the character's active_trauma or hidden_motive."
        )

        # --- Player identity (POV grounding) ---
        if state.player:
            player_name = state.player.name or "the protagonist"
            player_bg = getattr(state.player, "background", None) or ""
            base += f"\n\n## POV Character\nName: {player_name}."
            if player_bg:
                base += f" Background: {player_bg}"
            # V2.8: Pronoun injection for gender-correct narration
            player_gender = getattr(state.player, "gender", None)
            if player_gender:
                from backend.app.core.pronouns import pronoun_block as _pronoun_block
                _pblock = _pronoun_block(player_name, player_gender)
                if _pblock:
                    base += f"\n{_pblock}"
            base += (
                "\nScene instructions must reflect what THIS character would plausibly do in THIS location. "
                "Ground the narrative in the character's identity, skills, and situation."
            )
            # V2.7: Player agency rules
            base += (
                "\n\n## PLAYER AGENCY (CRITICAL)\n"
                "The player character ONLY acts when the player explicitly chooses an action. "
                "Do NOT narrate the character doing things autonomously. "
                "The character is controlled by the player, not the narrative AI."
            )
            # Opening scene: add character motivation context
            if is_opening_scene and player_bg:
                base += (
                    f"\n\n## CHARACTER MOTIVATION\n{player_bg}\n"
                    "The opening scene must reflect WHY the character is at this location. "
                    "Ground the setting in their personal situation. If they're running from something, "
                    "show the tension. If they're searching for someone, hint at leads. "
                    "The narrative should surface opportunities connected to this motivation."
                )

        # --- Location context (scene grounding) ---
        campaign = getattr(state, "campaign", None) or {}
        loc_id = state.current_location
        loc_obj = None
        if loc_id:
            era_id_for_loc = campaign.get("time_period") or campaign.get("era") or None
            era_pack_for_loc = CONTENT_REPOSITORY.get_pack(era_id_for_loc) if era_id_for_loc else None
            loc_obj = era_pack_for_loc.location_by_id(loc_id) if era_pack_for_loc else None
            if loc_obj:
                base += f"\n\n## Current Location\nName: {loc_obj.name}."
                if loc_obj.description:
                    base += f" {loc_obj.description}"
                if loc_obj.tags:
                    base += f"\nLocation tags: {', '.join(loc_obj.tags)}."
                if loc_obj.threat_level:
                    base += f" Threat level: {loc_obj.threat_level}."
                if loc_obj.planet:
                    base += f" Planet: {loc_obj.planet}."

        # --- V2.10: Starship ownership context ---
        _starship = getattr(state, "player_starship", None)
        if _starship and _starship.get("has_starship"):
            _ship_type = _starship.get("ship_type", "unknown vessel")
            base += (
                f"\n\n## PLAYER STARSHIP\n"
                f"The player owns a starship: {_ship_type}.\n"
                "Suggestions can include space travel, ship modifications, using the ship as a mobile base, "
                "or ship-related encounters (boarding, repairs, smuggling compartments)."
            )
        else:
            _no_ship_hint = (
                "\n\n## NO STARSHIP\n"
                "The player does NOT own a starship. They are planet-bound.\n"
                "To leave this planet, they must hire passage, arrange NPC transport, stow away, "
                "or find another means of travel. A starship quest is a natural story milestone — "
                "suggest it when dramatically appropriate (RISING arc stage or later).\n"
                "Do NOT suggest 'fly to' or 'take your ship to' actions."
            )
            # Stronger hint at spaceport/docking locations
            _loc_tags = []
            if loc_obj and getattr(loc_obj, "tags", None):
                _loc_tags = loc_obj.tags
            if any(t in _loc_tags for t in ("spaceport", "docking_bay", "hangar", "shipyard")):
                _no_ship_hint += (
                    "\nThe player is at a location with ships. This is a natural place to "
                    "encounter ship-related opportunities: a pilot offering work, a derelict "
                    "vessel, a smuggler's deal, or a ship for sale."
                )
            base += _no_ship_hint

        # --- Present NPCs (SOCIAL action grounding) ---
        npcs = getattr(state, "present_npcs", None) or []
        known_npcs = set(getattr(state, "known_npcs", None) or [])
        if npcs:
            npc_lines = [f"  - {n.get('name', 'Unknown')} ({n.get('role', 'NPC')})" for n in npcs if n.get("name")]
            if npc_lines:
                base += "\n\n## Present NPCs (physically in this scene)\n" + "\n".join(npc_lines)
                # V2.12: Per-NPC naming — only NPCs the player has met can be named
                unknown_npcs = [n.get("name") for n in npcs if n.get("name") and n["name"] not in known_npcs]
                if unknown_npcs:
                    base += (
                        "\nNPC NAMING: The player has NOT met these NPCs yet: "
                        + ", ".join(unknown_npcs) + ". "
                        "In action labels, describe UNKNOWN NPCs by appearance or role "
                        "(e.g., 'the grizzled pilot', 'the hooded merchant') rather than by name. "
                        "The name is for YOUR reference. The player will learn names through interaction."
                    )
                    # If ALL NPCs are unknown, add stronger guidance
                    known_present = [n.get("name") for n in npcs if n.get("name") and n["name"] in known_npcs]
                    if known_present:
                        base += (
                            "\nKNOWN NPCs (player has met): " + ", ".join(known_present)
                            + ". These NPCs CAN be referenced by name in actions."
                        )
                else:
                    base += (
                        "\nSocial interactions in the scene MUST involve one of these NPCs by name. "
                        "Do NOT reference characters who are not listed here."
                    )
        else:
            base += (
                "\n\n## Present NPCs\n(No named NPCs present in this location.)\n"
                "SOCIAL actions should reference 'someone nearby', an anonymous local, or a companion — not named characters."
            )

        campaign = getattr(state, "campaign", None) or {}
        news_feed = campaign.get("news_feed") or []
        latest_news = news_feed[:3] if isinstance(news_feed, list) else []
        has_high_urgency = False
        if latest_news:
            base += "\n\nComms / Briefing (latest intel; use for pacing and hooks):\n"
            for item in latest_news:
                if isinstance(item, dict):
                    src = item.get("source_tag", "CIVNET")
                    head = item.get("headline", "")[:80]
                    urgency = item.get("urgency", "LOW")
                    if str(urgency).upper() == "HIGH":
                        has_high_urgency = True
                    base += f"- [{src}] {head} (urgency: {urgency})\n"
                    body = (item.get("body") or "").strip()
                    if body:
                        base += f"  {body[:200]}\n"
            if has_high_urgency:
                base += (
                    "\nIf any briefing has urgency HIGH, the narrative should create opportunities to respond "
                    "(investigate, intervene, or follow up)."
                )
        else:
            new_rumors = getattr(state, "new_rumors", None) or []
            if new_rumors:
                base += "\n\nRecent rumors (you may reference if relevant):\n" + "\n".join(
                    f"- {r}" for r in new_rumors[:5]
                )
        era_factions_block, allowed_entities = build_era_factions_companions_context(state)
        if era_factions_block:
            base += "\n\n" + era_factions_block
        base += (
            "\n\nRule: Narrative must NOT reference factions, people, or named entities not present in the above context "
            "(campaign era, active factions, companions, present NPCs). Avoid inventing new names."
        )
        # V2.5: Arc planner guidance (deterministic arc stage + pacing)
        if arc_guidance:
            arc_stage = arc_guidance.get("arc_stage", "SETUP")
            priority_threads = arc_guidance.get("priority_threads") or []
            pacing_hint = arc_guidance.get("pacing_hint", "")
            tension_level = arc_guidance.get("tension_level", "CALM")
            base += f"\n\nARC STAGE: {arc_stage}. Tension: {tension_level}."
            if priority_threads:
                base += f" Priority threads: {'; '.join(str(t) for t in priority_threads[:2])}."
            if pacing_hint:
                base += f" Pacing: {pacing_hint}"
            if arc_stage == "CLIMAX":
                base += " At least one suggestion should advance the primary conflict."
            elif arc_stage == "RESOLUTION":
                base += " Consider aftermath and reflection."
            # Hero's Journey beat context
            hero_beat = arc_guidance.get("hero_beat") or ""
            hero_pacing = arc_guidance.get("hero_pacing") or ""
            archetype_hints = arc_guidance.get("archetype_hints") or []
            if hero_beat:
                base += f"\n\nHERO'S JOURNEY BEAT: {hero_beat}."
                if hero_pacing:
                    base += f" {hero_pacing}"
                if archetype_hints:
                    hint_strs = [f"{h['archetype']}: {h['description']}" for h in archetype_hints[:2]]
                    base += "\nNPC archetype hints for this beat: " + "; ".join(hint_strs)
                # Beat-specific Director nudges
                if hero_beat == "MEETING_THE_MENTOR":
                    base += (
                        "\nConsider introducing a guide or mentor figure if none is present. "
                        "A SOCIAL suggestion involving wisdom or training would fit this beat."
                    )
                elif hero_beat == "ORDEAL":
                    base += (
                        "\nThis is the supreme crisis. At least one suggestion should involve high-stakes "
                        "confrontation. Raise the tension — failure should feel possible."
                    )
                elif hero_beat == "CALL_TO_ADVENTURE":
                    base += (
                        "\nSomething should disrupt the status quo. Include a suggestion that involves "
                        "accepting a mission, responding to a distress call, or investigating a mystery."
                    )
                elif hero_beat == "CROSSING_THE_THRESHOLD":
                    base += (
                        "\nThe character should commit to the journey. Include a bold, irreversible choice. "
                        "Raise stakes: there is no going back after this."
                    )

            # Phase 3: Theme guidance
            active_themes = arc_guidance.get("active_themes") or []
            theme_guidance = arc_guidance.get("theme_guidance") or ""
            if active_themes:
                theme_names = ", ".join(t.replace("_", " ") for t in active_themes[:3])
                base += f"\n\nACTIVE THEMES: {theme_names}."
                base += " Weave these themes into suggestions and narrative direction."
                if theme_guidance:
                    base += f" {theme_guidance}"

        # Phase 5: Companion conflicts (inject into director awareness)
        companion_conflicts = campaign.get("companion_conflicts") or []
        if companion_conflicts:
            base += "\n\nCOMPANION CONFLICTS (address in suggestions):"
            for conflict in companion_conflicts[:2]:
                cid = conflict.get("companion_id", "unknown")
                ctype = conflict.get("conflict_type", "")
                base += f"\n- {cid}: {ctype}"

        # 3.2: Inter-companion tensions (inject into director awareness)
        tensions_director = campaign.get("inter_party_tensions_director") or ""
        if tensions_director:
            base += "\n\nINTER-PARTY TENSIONS (companions disagree — consider addressing):"
            base += f"\n{tensions_director}"

        # V2.5: Companion-aware suggestions (affinity milestones, high loyalty)
        party_affinity = campaign.get("party_affinity") or {}
        for comp_id, affinity in party_affinity.items():
            aff = int(affinity) if affinity else 0
            if aff > 0 and aff % 5 == 0:
                comp_name = comp_id.replace("_", " ").title()
                base += (
                    f"\nCompanion {comp_name} has reached an affinity milestone ({aff}). "
                    "Consider a SOCIAL suggestion involving a companion moment."
                )
            elif aff > 20:
                comp_name = comp_id.replace("_", " ").title()
                base += f"\nCompanion {comp_name} has high loyalty. Consider SOCIAL suggestion involving them."

        # V2.12: Opening beats — structured narrative spine for first 3 turns
        world_state = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
        if isinstance(world_state, str):
            import json as _json
            try:
                world_state = _json.loads(world_state)
            except (ValueError, TypeError):
                world_state = {}
        opening_beats = world_state.get("opening_beats") or [] if isinstance(world_state, dict) else []
        turn_number = int(getattr(state, "turn_number", 0) or 0)
        current_beat = next((b for b in opening_beats if b.get("turn") == turn_number), None)
        if current_beat:
            base += f"\n\n## OPENING BEAT (Turn {turn_number}: {current_beat.get('beat', '')})"
            base += f"\nGoal: {current_beat.get('goal', '')}"
            hook = current_beat.get("hook")
            if hook:
                base += f"\nHook: {hook}"
            base += "\nFollow this beat. Do NOT skip ahead or introduce elements from later beats."

        # V2.12: Act outline — lightweight campaign direction
        act_outline = world_state.get("act_outline") if isinstance(world_state, dict) else None
        if act_outline and isinstance(act_outline, dict):
            base += "\n\n## CAMPAIGN DIRECTION"
            for key in ("act_1_setup", "act_2_rising", "act_3_climax"):
                val = act_outline.get(key)
                if val:
                    label = key.replace("act_", "Act ").replace("_", " ").title()
                    base += f"\n- {label}: {val}"

        directives = directives_from_style_context(style_context, min_count=2)
        if directives:
            story_state_summary = base + "\n" + "\n".join(f"- {d}" for d in directives[:4])
        else:
            story_state_summary = base

        director_instructions = story_state_summary
        if adventure_hooks:
            director_instructions += "\n\nAdventure / scenario hooks (use for pacing):\n" + adventure_hooks

        return director_instructions, story_state_summary, style_chunks, lore_chunks, allowed_entities

    def plan(
        self,
        state: GameState,
        previous_suggestions: list[ActionSuggestion] | list[dict] | None = None,
        fix_instruction: str | None = None,
        kg_context: str = "",
        arc_guidance: dict | None = None,
    ) -> tuple[str, list[ActionSuggestion]]:
        """Return director_instructions + fallback suggestions.

        V2.12: The Director no longer generates structured suggestions via LLM.
        Instead, it produces text-based scene/pacing instructions for the Narrator.
        The Narrator generates action options as part of its prose output, which
        are then classified with deterministic KOTOR metadata.

        Suggestions returned here are deterministic fallbacks used only when
        the Narrator fails to embed its own options.
        """
        director_instructions, story_state_summary, style_chunks, lore_chunks, allowed_entities = self._build_instructions(state, arc_guidance=arc_guidance)

        if self._llm is None:
            return director_instructions, []

        # V2.12: Simplified system prompt — instructions only, no JSON schema
        # V3.2: Use setting_rules for universe-aware prompts
        from backend.app.core.setting_context import get_setting_rules
        _sr = get_setting_rules(state.model_dump(mode="json") if hasattr(state, "model_dump") else (state if isinstance(state, dict) else {}))
        system_prompt = (
            f"You are {_sr.director_role}.\n"
            "Your job is to write SCENE INSTRUCTIONS for the Narrator — guidance on what should happen next.\n\n"
            "Write 3-5 sentences covering:\n"
            "1. SCENE GOAL: What should this scene accomplish? (establish setting, introduce threat, reveal information, etc.)\n"
            "2. PACING: Should this scene be tense, atmospheric, action-packed, or reflective?\n"
            "3. NPC BEHAVIOR: How should present NPCs act? What are their immediate goals?\n"
            "4. HOOKS: What tension or mystery should the scene introduce or advance?\n\n"
            "Rules:\n"
            "- Write plain text instructions, NOT JSON. No code blocks, no structured data.\n"
            "- Do NOT generate suggested actions or dialogue options — the Narrator handles that.\n"
            "- Do NOT assume the player's faction allegiance.\n"
            "- Reference specific NPCs, locations, and plot threads from the context.\n"
            "- Keep instructions concise and actionable."
        )

        max_input_tokens = get_role_max_input_tokens("director")
        reserve_output_tokens = get_role_reserved_output_tokens("director")
        parts = {
            "system": system_prompt,
            "state": story_state_summary,
            "history": state.history or [],
            "era_summaries": state.era_summaries or [],
            "lore_chunks": lore_chunks,
            "style_chunks": style_chunks,
            "voice_snippets": {},
            "kg_context": kg_context,
            "user_input": state.user_input or "",
        }
        messages, budget_report = build_context(
            parts,
            max_input_tokens=max_input_tokens,
            reserve_output_tokens=reserve_output_tokens,
            role="director",
            min_lore_chunks=1,
            user_input_label="User input:",
        )
        system_prompt_final = messages[0]["content"]
        context_prompt = messages[1]["content"]
        warn = budget_report.warning_message()
        if warn:
            add_warning(state, warn)
        user_prompt = (
            "Context:\n"
            f"{context_prompt}\n\n"
            "Write your scene instructions now."
        )

        try:
            raw_instructions = self._llm.generate(
                system_prompt=system_prompt_final,
                user_prompt=user_prompt,
            )
            if raw_instructions and raw_instructions.strip():
                llm_instructions = sanitize_instructions_for_narrator(raw_instructions.strip())
                # Merge LLM instructions with built context instructions
                llm_instructions = director_instructions + "\n\n## Scene Direction\n" + llm_instructions
            else:
                llm_instructions = director_instructions
        except Exception as e:
            logger.warning("Director LLM call failed (using built instructions): %s", e)
            llm_instructions = director_instructions

        return llm_instructions, []
