"""Narrator node factory."""
from __future__ import annotations

import logging
from typing import Any

from backend.app.config import ENABLE_CHARACTER_FACETS
from backend.app.core.agents import NarratorAgent
from backend.app.core.agents.base import AgentLLM
from backend.app.core.agents.narrator import _extract_npc_utterance
from backend.app.core.nodes import dict_to_state
from backend.app.rag.character_voice_retriever import get_voice_snippets
from backend.app.rag.kg_retriever import KGRetriever
from backend.app.rag.lore_retriever import retrieve_lore
from backend.app.rag.retrieval_bundles import NARRATOR_DOC_TYPES, NARRATOR_SECTION_KINDS
from backend.app.rag.style_retriever import retrieve_style_layered

logger = logging.getLogger(__name__)


def _is_high_stakes_combat(state: dict[str, Any]) -> bool:
    """True if scene is high-stakes combat (no banter append)."""
    mechanic_result = state.get("mechanic_result") or {}
    action_type = (mechanic_result.get("action_type") or "").upper()
    if action_type in ("ATTACK", "COMBAT"):
        return True
    events = mechanic_result.get("events") or []
    for e in events:
        t = e.get("event_type", "") if isinstance(e, dict) else getattr(e, "event_type", "")
        if (t or "").upper() == "DAMAGE":
            return True
    return False


def make_narrator_node():
    """Build the Narrator node."""
    def lore_retriever(query: str, top_k: int = 6, era: str | None = None, related_npcs: list[str] | None = None):
        return retrieve_lore(
            query,
            top_k=top_k,
            era=era,
            doc_types=NARRATOR_DOC_TYPES,
            section_kinds=NARRATOR_SECTION_KINDS,
            related_npcs=related_npcs,
        )

    voice_retriever = None
    if ENABLE_CHARACTER_FACETS:
        voice_retriever = lambda cids, era, k=6: get_voice_snippets(cids, era, k=k)

    def style_retriever_fn(query: str, top_k: int = 3, era_id=None, genre=None, archetype=None):
        return retrieve_style_layered(query, top_k=top_k, era_id=era_id, genre=genre, archetype=archetype)

    try:
        narrator_llm = AgentLLM("narrator")
    except Exception as e:
        logger.warning(
            "Failed to initialize NarratorAgent with LLM, using fallback: %s",
            e,
            exc_info=True,
        )
        narrator_llm = None

    narrator = NarratorAgent(
        llm=narrator_llm,
        lore_retriever=lore_retriever,
        voice_retriever=voice_retriever,
        style_retriever=style_retriever_fn,
    )
    kg_retriever = KGRetriever()

    def narrator_node(state: dict[str, Any]) -> dict[str, Any]:
        import logging as _logging
        _narrator_logger = _logging.getLogger(__name__)
        gs = dict_to_state(state)

        # --- V2.8: Use shared RAG data from Director if available ---
        shared_char_ctx = state.get("shared_kg_character_context", "")
        shared_event_ctx = state.get("shared_kg_relevant_events", "")
        shared_mem_block = state.get("shared_episodic_memories", "")
        # V2.10: NPC personality context from Director
        shared_personality_ctx = state.get("shared_npc_personality_context", "")

        if shared_char_ctx or shared_event_ctx:
            # Use shared character_context + relevant_events from Director,
            # add Narrator-only location_context
            campaign_dict = getattr(gs, "campaign", None) or {}
            era = (campaign_dict.get("time_period") or campaign_dict.get("era") or "rebellion").strip() or "rebellion"
            loc_ctx = kg_retriever.get_location_context(gs.current_location or "", era)
            kg_parts = [p for p in [shared_char_ctx, loc_ctx, shared_event_ctx] if p]
            kg_context = "## Knowledge Graph Context\n" + "\n\n".join(kg_parts) if kg_parts else ""
            _narrator_logger.debug("Narrator using shared KG data from Director")
        else:
            # Fallback: run own KG retrieval (backward compat if Director didn't run)
            kg_context = kg_retriever.get_context_for_narrator(gs)

        # V2.10: Inject NPC personality context for voice/mannerism guidance
        if shared_personality_ctx:
            kg_context = (kg_context + "\n\n## NPC Personalities\n" + shared_personality_ctx) if kg_context else ("## NPC Personalities\n" + shared_personality_ctx)
            _narrator_logger.debug("Narrator using shared NPC personality context from Director")

        # Episodic memory: use shared from Director if available
        if shared_mem_block:
            if shared_mem_block:
                kg_context = (kg_context + "\n\n" + shared_mem_block) if kg_context else shared_mem_block
            _narrator_logger.debug("Narrator using shared episodic memory from Director")
        else:
            # Fallback: run own episodic memory retrieval
            try:
                conn = state.get("__runtime_conn")
                if conn:
                    from backend.app.core.episodic_memory import EpisodicMemory
                    epi = EpisodicMemory(conn, gs.campaign_id or "")
                    query_text = (gs.user_input or "") + " " + (gs.current_location or "")
                    npc_names = [n.get("name", "") for n in (gs.present_npcs or []) if n.get("name")]
                    memories = epi.recall(
                        query_text=query_text,
                        current_turn=int(gs.turn_number or 0),
                        location_id=gs.current_location,
                        npcs=npc_names,
                        max_results=4,
                    )
                    mem_block = epi.format_for_prompt(memories, max_chars=500)
                    if mem_block:
                        kg_context = (kg_context + "\n\n" + mem_block) if kg_context else mem_block
            except Exception as _epi_err:
                _narrator_logger.debug("Episodic memory recall failed for Narrator (non-fatal): %s", _epi_err)
        output = narrator.generate(gs, kg_context=kg_context)
        final_text = output.text

        # Phase 7: Narrator feedback loop — retry once on mechanic consistency failure
        from backend.app.core.nodes.narrative_validator import _check_mechanic_consistency
        mechanic_result = state.get("mechanic_result") or {}
        consistency_warnings = _check_mechanic_consistency(final_text, mechanic_result)
        if consistency_warnings and narrator._llm is not None:
            correction = "; ".join(consistency_warnings)
            _narrator_logger.info("Narrator retry: mechanic consistency issue detected, retrying once.")
            try:
                retry_output = narrator.generate_with_correction(gs, correction, kg_context=kg_context)
                retry_warnings = _check_mechanic_consistency(retry_output.text, mechanic_result)
                if not retry_warnings:
                    final_text = retry_output.text
                    output = retry_output
                    _narrator_logger.info("Narrator retry succeeded — consistency resolved.")
                else:
                    _narrator_logger.warning("Narrator retry still has issues; using original text.")
            except Exception as _retry_err:
                _narrator_logger.warning("Narrator retry failed (non-fatal): %s", _retry_err)
        campaign = dict(state.get("campaign") or {})
        banter_queue = list(campaign.get("banter_queue") or [])
        if banter_queue and not _is_high_stakes_combat(state):
            first = banter_queue[0]
            speaker = first.get("speaker", "") if isinstance(first, dict) else ""
            line = first.get("text", first) if isinstance(first, dict) else first
            if line:
                # Strip wrapping quotes if present (banter is stored pre-quoted)
                clean_line = line.strip().strip('"').strip("'").strip()
                if clean_line:
                    # Integrate companion banter as a narrative beat, not floating text
                    final_text = f"{final_text}\n\n---\n\n*{clean_line}*"
            campaign = {**campaign, "banter_queue": banter_queue[1:]}
        # V2.15: Narrator produces prose only. Suggestions come from Director node
        # via generate_suggestions(). embedded_suggestions is always None.

        # V2.17: Extract NPC utterance from ---NPC_LINE--- separator
        present_npcs = gs.present_npcs or []
        prose, npc_utt = _extract_npc_utterance(final_text, present_npcs)
        final_text = prose

        # Safety net: strip any residual NPC_LINE / SPEAKER markers that
        # survived extraction (LLM format variations, mid-paragraph injection).
        import re as _re
        final_text = _re.sub(
            r"-{2,3}\s*NPC[_\s-]?LINE\s*-{2,3}", "", final_text, flags=_re.IGNORECASE
        ).strip()
        final_text = _re.sub(
            r"^\s*SPEAKER:\s*.+$", "", final_text, flags=_re.MULTILINE
        ).strip()
        # Collapse any resulting blank-line runs
        final_text = _re.sub(r"\n{3,}", "\n\n", final_text).strip()

        return {
            **state,
            "final_text": final_text,
            "lore_citations": [c.model_dump(mode="json") for c in output.citations],
            "embedded_suggestions": None,
            "npc_utterance": npc_utt.model_dump(mode="json"),
            "campaign": campaign,
            "warnings": gs.warnings,
        }

    return narrator_node
