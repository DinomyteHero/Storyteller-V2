"""Narrator agent: generates narrative from state, mechanic result, director instructions, lore (grounded).

This module re-exports all public and semi-public symbols from the
``narrator_prompt`` and ``narrator_postprocess`` sub-modules so that
existing imports of the form::

    from backend.app.core.agents.narrator import _build_prompt, NarratorAgent

continue to work without modification.
"""
from __future__ import annotations

import logging
from typing import Callable, Iterator

from backend.app.models.state import GameState
from backend.app.models.narration import NarrationOutput
from backend.app.core.agents.base import AgentLLM
from backend.app.config import DEV_CONTEXT_STATS
from backend.app.core.error_handling import log_error_with_context
from backend.app.core.agent_utils import (
    call_retriever,
    collect_related_npc_ids,
)
from backend.app.core.warnings import add_warning

# ── Sub-module imports (prompt construction) ──────────────────────────────
from backend.app.core.agents.narrator_prompt import (  # noqa: F401
    _GENERIC_LOCATION_NAMES,
    _GENERIC_ATMOSPHERE_FRAGMENTS,
    _get_atmosphere,
    _humanize_location,
    _build_lore_query,
    _summarize_mechanic_events,
    _collect_character_ids,
    _build_story_state_summary,
    _build_prompt,
)

# ── Sub-module imports (post-processing) ──────────────────────────────────
from backend.app.core.agents.narrator_postprocess import (  # noqa: F401
    _quote_excerpt,
    _PATTERN_FIRE_COUNTS,
    _track_sub,
    get_pattern_fire_counts,
    _strip_structural_artifacts,
    _truncate_overlong_prose,
    _strip_embedded_suggestions,
    _NPC_LINE_SEP,
    _NPC_LINE_REGEX,
    _extract_npc_utterance,
    _META_NARRATOR_PATTERNS,
    _enforce_pov_consistency,
    _citations_from_chunks,
    _parse_llm_narration,
    get_word_limit_for_scene_weight,
)

logger = logging.getLogger(__name__)

# ── Type aliases ──────────────────────────────────────────────────────────
# Lore chunk dict: text, source_title, chapter_title, chunk_id, metadata, score
LoreChunk = dict

# Voice snippet for character voice retrieval
VoiceSnippet = dict  # character_id, era, text, chunk_id


class NarratorAgent:
    """Incorporates mechanic_result (show don't tell), director_instructions, lore (grounded), voice snippets."""

    def __init__(
        self,
        llm: AgentLLM | None = None,
        lore_retriever: Callable[..., list[LoreChunk]] | None = None,
        voice_retriever: Callable[[list[str], str, int], dict[str, list]] | None = None,
        style_retriever: Callable[..., list[dict]] | None = None,
    ) -> None:
        self._llm = llm
        self._lore_retriever = lore_retriever
        self._voice_retriever = voice_retriever
        self._style_retriever = style_retriever

    def generate(self, state: GameState, kg_context: str = "") -> NarrationOutput:
        """Produce narrative (grounded in mechanic events + lore); return NarrationOutput with optional citations."""
        warnings_list = getattr(state, "warnings", None)
        # If Mechanic returned invalid_action, do not invent outcomes—ask for rephrase only
        if state.mechanic_result and getattr(state.mechanic_result, "invalid_action", False):
            msg = getattr(state.mechanic_result, "rephrase_message", None) or "That action is unclear—try rephrasing."
            return NarrationOutput(text=msg, citations=[])

        # Retrieve lore
        lore_chunks: list[LoreChunk] = []
        campaign = state.campaign or {}
        era = (campaign.get("time_period") or campaign.get("era") or "REBELLION")
        if isinstance(era, str):
            era = era.strip() or "REBELLION"
        else:
            era = "REBELLION"

        if self._lore_retriever is not None:
            query = _build_lore_query(state)
            related_ids = collect_related_npc_ids(state)
            lore_chunks = call_retriever(
                self._lore_retriever,
                query,
                top_k=6,
                era=era,
                related_npcs=related_ids if related_ids else None,
                warnings=warnings_list,
            )
            if related_ids and not lore_chunks:
                lore_chunks = call_retriever(
                    self._lore_retriever,
                    query,
                    top_k=6,
                    era=era,
                    warnings=warnings_list,
                )

        # Retrieve voice snippets for present NPCs and party
        # Phase 3.4: Pass NPC emotional context so vector search prefers
        # snippets matching the NPC's current disposition (angry, suspicious, etc.)
        voice_snippets_by_char: dict[str, list] = {}
        if self._voice_retriever is not None:
            char_ids = _collect_character_ids(state)
            if char_ids:
                ws = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
                npc_states = (ws.get("npc_states") or {}) if isinstance(ws, dict) else {}
                emotional_context: dict[str, str] = {}
                for cid in char_ids:
                    npc_st = npc_states.get(cid) or {}
                    emo = npc_st.get("emotional_state", "") if isinstance(npc_st, dict) else ""
                    if emo:
                        emotional_context[cid] = str(emo)
                raw = call_retriever(
                    self._voice_retriever, char_ids, era, k=6,
                    emotional_context=emotional_context if emotional_context else None,
                    warnings=warnings_list,
                )
                for cid, snips in raw.items():
                    voice_snippets_by_char[cid] = [
                        {"character_id": s.character_id, "era": s.era, "text": s.text, "chunk_id": s.chunk_id}
                        if hasattr(s, "text") else s
                        for s in snips
                    ]

        # Retrieve style chunks for narrative shaping
        style_chunks: list[dict] = []
        if self._style_retriever is not None:
            from backend.app.core.director_validation import build_style_query
            style_query = build_style_query(state)
            campaign = getattr(state, "campaign", None) or {}
            _era_id = campaign.get("time_period") or campaign.get("era") or None
            _genre = campaign.get("genre") or None
            _archetype = campaign.get("archetype") or None
            style_chunks = call_retriever(self._style_retriever, style_query, 3, era_id=_era_id, genre=_genre, archetype=_archetype, warnings=warnings_list)

        system, user, budget_report = _build_prompt(
            state,
            lore_chunks,
            voice_snippets_by_char,
            include_budget=True,
            kg_context=kg_context,
            style_chunks=style_chunks,
        )

        warn = budget_report.warning_message()
        if warn:
            add_warning(state, warn)

        # Store context_stats in state for later retrieval (if DEV_CONTEXT_STATS enabled)
        if DEV_CONTEXT_STATS:
            state.context_stats = budget_report.to_context_stats()

        bool(lore_chunks)
        bool(voice_snippets_by_char and any(voice_snippets_by_char.values()))

        if self._llm is not None:
            try:
                raw = self._llm.generate(system_prompt=system, user_prompt=user)
                output = _parse_llm_narration(raw, lore_chunks)
                cleaned_text = _strip_structural_artifacts(output.text)

                # V2.15: Narrator writes prose only. Strip any suggestions the LLM
                # may still inject despite the simplified prompt (safety net).
                cleaned_text = _strip_embedded_suggestions(cleaned_text)

                cleaned_text = _enforce_pov_consistency(cleaned_text)
                max_words = get_word_limit_for_scene_weight(
                    getattr(state, "scene_weight", None),
                    narrator_mode=getattr(state, "narrator_mode", None),
                )
                cleaned_text = _truncate_overlong_prose(cleaned_text, max_words=max_words)
                output = NarrationOutput(
                    text=cleaned_text,
                    citations=output.citations,
                    embedded_suggestions=None,
                )
                return output
            except Exception as e:
                log_error_with_context(
                    error=e,
                    node_name="narrator",
                    campaign_id=state.campaign_id,
                    turn_number=state.turn_number,
                    agent_name="NarratorAgent.generate",
                    extra_context={"location": state.current_location},
                )
                logger.warning("NarratorAgent LLM generation failed, using fallback")
                add_warning(state, "LLM error: Narrator used fallback output.")
        # No LLM or LLM failed: deterministic fallback
        # Build a readable narrative fallback (not raw pipeline data)
        mechanic_summary = _summarize_mechanic_events(state)
        loc = _humanize_location(state.current_location, state) or "your surroundings"
        npcs = state.present_npcs or []

        # Check if this is the opening scene
        is_opening_fb = not (state.history or []) or len(state.history or []) <= 1
        opening_tag_fb = "[OPENING_SCENE]" in (state.user_input or "")

        # Resolve POV character name for third-person fallback
        pov_name = "the protagonist"
        if state.player and getattr(state.player, "name", None):
            pov_name = state.player.name

        # Era-aware atmosphere from era pack (generic fallback if missing)
        campaign = state.campaign or {}
        ws = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
        era_atmosphere = _get_atmosphere(state)

        if is_opening_fb or opening_tag_fb:
            # Opening scene fallback: more atmospheric
            planet = ""
            if isinstance(ws, dict):
                planet = ws.get("starting_planet") or ""
            planet_str = f" on {planet}" if planet else ""

            parts = [era_atmosphere["opening"].format(planet_str=planet_str)]
            parts.append(f"{pov_name} stepped into {loc}, taking in the scene.")

            # Mention present NPCs atmospherically
            npc_names = [n.get("name") for n in npcs if n.get("name")]
            if npc_names:
                if len(npc_names) == 1:
                    parts.append(f"A figure caught {pov_name}'s eye — {npc_names[0]}, watching from across the room.")
                else:
                    parts.append(f"Several figures populated the space: {', '.join(npc_names[:-1])} and {npc_names[-1]}.")

            parts.append(era_atmosphere["hook"])
            paragraph = " ".join(parts)
            text = paragraph
        else:
            # Normal fallback
            parts = [f"{pov_name} surveyed {loc}. {era_atmosphere['ambient']}"]

            # Add mechanic outcomes as narrative (not raw labels)
            if mechanic_summary and mechanic_summary != "(No mechanical events this turn.)":
                parts.append(mechanic_summary)

            # Mention present NPCs
            npc_names = [n.get("name") for n in npcs if n.get("name")]
            if npc_names:
                if len(npc_names) == 1:
                    parts.append(f"{npc_names[0]} is nearby.")
                else:
                    parts.append(f"{', '.join(npc_names[:-1])} and {npc_names[-1]} are nearby.")

            # Add atmosphere based on stress level
            psych = {}
            if state.player and getattr(state.player, "psych_profile", None):
                psych = state.player.psych_profile or {}
            stress_level = int(psych.get("stress_level", 0) or 0)
            if stress_level > 7:
                parts.append(era_atmosphere["tension"])
            elif stress_level < 3:
                parts.append(era_atmosphere["calm"])

            paragraph = " ".join(parts)
            text = paragraph
        text = _strip_embedded_suggestions(text)
        text = _enforce_pov_consistency(text)
        citations = _citations_from_chunks(lore_chunks)
        return NarrationOutput(text=text, citations=citations)

    def generate_stream(self, state: GameState, kg_context: str = "") -> Iterator[str]:
        """Stream narrative tokens. Yields individual token strings.

        Builds the same prompt as generate() but uses complete_stream() for
        incremental token delivery. Post-processing (_strip_structural_artifacts,
        etc.) must be applied on the accumulated text by the caller after the
        stream completes.

        Falls back to yielding the full deterministic fallback text if no LLM
        is available.
        """
        warnings_list = getattr(state, "warnings", None)

        # If Mechanic returned invalid_action, yield the rephrase message
        if state.mechanic_result and getattr(state.mechanic_result, "invalid_action", False):
            msg = getattr(state.mechanic_result, "rephrase_message", None) or "That action is unclear—try rephrasing."
            yield msg
            return

        # Retrieve lore
        lore_chunks: list[LoreChunk] = []
        campaign = state.campaign or {}
        era = (campaign.get("time_period") or campaign.get("era") or "REBELLION")
        if isinstance(era, str):
            era = era.strip() or "REBELLION"
        else:
            era = "REBELLION"

        if self._lore_retriever is not None:
            query = _build_lore_query(state)
            related_ids = collect_related_npc_ids(state)
            lore_chunks = call_retriever(
                self._lore_retriever,
                query,
                top_k=6,
                era=era,
                related_npcs=related_ids if related_ids else None,
                warnings=warnings_list,
            )
            if related_ids and not lore_chunks:
                lore_chunks = call_retriever(
                    self._lore_retriever,
                    query,
                    top_k=6,
                    era=era,
                    warnings=warnings_list,
                )

        # Retrieve voice snippets (Phase 3.4: with emotional context)
        voice_snippets_by_char: dict[str, list] = {}
        if self._voice_retriever is not None:
            char_ids = _collect_character_ids(state)
            if char_ids:
                ws = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
                npc_states = (ws.get("npc_states") or {}) if isinstance(ws, dict) else {}
                emotional_context: dict[str, str] = {}
                for cid in char_ids:
                    npc_st = npc_states.get(cid) or {}
                    emo = npc_st.get("emotional_state", "") if isinstance(npc_st, dict) else ""
                    if emo:
                        emotional_context[cid] = str(emo)
                raw = call_retriever(
                    self._voice_retriever, char_ids, era, k=6,
                    emotional_context=emotional_context if emotional_context else None,
                    warnings=warnings_list,
                )
                for cid, snips in raw.items():
                    voice_snippets_by_char[cid] = [
                        {"character_id": s.character_id, "era": s.era, "text": s.text, "chunk_id": s.chunk_id}
                        if hasattr(s, "text") else s
                        for s in snips
                    ]

        # Retrieve style chunks
        style_chunks: list[dict] = []
        if self._style_retriever is not None:
            from backend.app.core.director_validation import build_style_query
            style_query = build_style_query(state)
            campaign = getattr(state, "campaign", None) or {}
            _era_id = campaign.get("time_period") or campaign.get("era") or None
            _genre = campaign.get("genre") or None
            _archetype = campaign.get("archetype") or None
            style_chunks = call_retriever(self._style_retriever, style_query, 3, era_id=_era_id, genre=_genre, archetype=_archetype, warnings=warnings_list)

        system, user = _build_prompt(
            state,
            lore_chunks,
            voice_snippets_by_char,
            include_budget=False,
            kg_context=kg_context,
            style_chunks=style_chunks,
        )

        if self._llm is not None:
            try:
                yield from self._llm.complete_stream(system_prompt=system, user_prompt=user)
                return
            except Exception as e:
                log_error_with_context(
                    error=e,
                    node_name="narrator",
                    campaign_id=state.campaign_id,
                    turn_number=state.turn_number,
                    agent_name="NarratorAgent.generate_stream",
                    extra_context={"location": state.current_location},
                )
                logger.warning("NarratorAgent streaming failed, using fallback")
                add_warning(state, "LLM error: Narrator streaming used fallback output.")

        # Fallback: yield the full deterministic text from generate()
        output = self.generate(state, kg_context=kg_context)
        yield output.text

    def generate_with_correction(self, state: GameState, correction: str, kg_context: str = "") -> NarrationOutput:
        """Re-generate narrative with a correction prompt appended. Used for narrator feedback loop (max 1 retry)."""
        warnings_list = getattr(state, "warnings", None)
        lore_chunks: list[LoreChunk] = []
        campaign = state.campaign or {}
        era = (campaign.get("time_period") or campaign.get("era") or "REBELLION")
        if isinstance(era, str):
            era = era.strip() or "REBELLION"
        else:
            era = "REBELLION"

        if self._lore_retriever is not None:
            query = _build_lore_query(state)
            related_ids = collect_related_npc_ids(state)
            lore_chunks = call_retriever(
                self._lore_retriever, query, top_k=6, era=era,
                related_npcs=related_ids if related_ids else None,
                warnings=warnings_list,
            )

        voice_snippets_by_char: dict[str, list] = {}
        if self._voice_retriever is not None:
            char_ids = _collect_character_ids(state)
            if char_ids:
                ws_corr = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
                npc_states_corr = (ws_corr.get("npc_states") or {}) if isinstance(ws_corr, dict) else {}
                emotional_context: dict[str, str] = {}
                for cid in char_ids:
                    npc_st = npc_states_corr.get(cid) or {}
                    emo = npc_st.get("emotional_state", "") if isinstance(npc_st, dict) else ""
                    if emo:
                        emotional_context[cid] = str(emo)
                raw = call_retriever(
                    self._voice_retriever, char_ids, era, k=6,
                    emotional_context=emotional_context if emotional_context else None,
                    warnings=warnings_list,
                )
                for cid, snips in raw.items():
                    voice_snippets_by_char[cid] = [
                        {"character_id": s.character_id, "era": s.era, "text": s.text, "chunk_id": s.chunk_id}
                        if hasattr(s, "text") else s
                        for s in snips
                    ]

        style_chunks: list[dict] = []
        if self._style_retriever is not None:
            from backend.app.core.director_validation import build_style_query
            style_query = build_style_query(state)
            campaign = getattr(state, "campaign", None) or {}
            _era_id = campaign.get("time_period") or campaign.get("era") or None
            _genre = campaign.get("genre") or None
            _archetype = campaign.get("archetype") or None
            style_chunks = call_retriever(self._style_retriever, style_query, 3, era_id=_era_id, genre=_genre, archetype=_archetype, warnings=warnings_list)

        system, user, budget_report = _build_prompt(
            state, lore_chunks, voice_snippets_by_char,
            include_budget=True, kg_context=kg_context, style_chunks=style_chunks,
        )
        # Append correction instruction to user prompt
        user = user + f"\n\nCORRECTION REQUIRED: {correction}\nRewrite the narrative to fix the above issue."

        bool(lore_chunks)
        bool(voice_snippets_by_char and any(voice_snippets_by_char.values()))

        if self._llm is not None:
            raw = self._llm.generate(system_prompt=system, user_prompt=user)
            output = _parse_llm_narration(raw, lore_chunks)
            cleaned_text = _strip_structural_artifacts(output.text)
            cleaned_text = _strip_embedded_suggestions(cleaned_text)
            cleaned_text = _enforce_pov_consistency(cleaned_text)
            max_words = get_word_limit_for_scene_weight(
                getattr(state, "scene_weight", None),
                narrator_mode=getattr(state, "narrator_mode", None),
            )
            cleaned_text = _truncate_overlong_prose(cleaned_text, max_words=max_words)
            output = NarrationOutput(
                text=cleaned_text,
                citations=output.citations,
            )
            return output
        # Fallback: no LLM available for correction
        return NarrationOutput(text="(Correction unavailable — no LLM.)", citations=[])


# ── Backward-compatible re-exports ────────────────────────────────────────
# All previously importable symbols are available directly from this module
# via the imports at the top of this file (narrator_prompt.* and
# narrator_postprocess.*).  The __all__ below lists the *public* API
# explicitly; private helpers (prefixed with _) are still importable.

__all__ = [
    # Type aliases
    "LoreChunk",
    "VoiceSnippet",
    # Agent class
    "NarratorAgent",
    # Public helpers
    "get_pattern_fire_counts",
]
