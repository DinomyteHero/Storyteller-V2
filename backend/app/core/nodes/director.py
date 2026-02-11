"""Director node factory."""
from __future__ import annotations

import logging
from typing import Any

from backend.app.core.agents import DirectorAgent
from backend.app.core.agents.base import AgentLLM
from backend.app.core.nodes import dict_to_state
from backend.app.core.personality_profile import build_scene_personality_context
from backend.app.rag.kg_retriever import KGRetriever
from backend.app.rag.lore_retriever import retrieve_lore
from backend.app.rag.style_retriever import retrieve_style_layered
from backend.app.rag.retrieval_bundles import DIRECTOR_DOC_TYPE, DIRECTOR_SECTION_KIND

logger = logging.getLogger(__name__)


def make_director_node():
    """Build the Director node."""
    def style_retriever(q, k, era_id=None, genre=None, archetype=None):
        return retrieve_style_layered(q, top_k=k, era_id=era_id, genre=genre, archetype=archetype)

    def lore_retriever(query: str, top_k: int = 4, era: str | None = None, related_npcs: list[str] | None = None):
        return retrieve_lore(
            query,
            top_k=top_k,
            era=era,
            doc_type=DIRECTOR_DOC_TYPE,
            section_kind=DIRECTOR_SECTION_KIND,
            related_npcs=related_npcs,
        )

    try:
        director = DirectorAgent(
            llm=AgentLLM("director"),
            style_retriever=style_retriever,
            lore_retriever=lore_retriever,
        )
    except Exception as e:
        logger.warning(
            "Failed to initialize DirectorAgent with LLM, using fallback: %s",
            e,
            exc_info=True,
        )
        director = DirectorAgent(style_retriever=style_retriever, lore_retriever=lore_retriever)

    kg_retriever = KGRetriever()

    def director_node(state: dict[str, Any]) -> dict[str, Any]:
        gs = dict_to_state(state)

        campaign = getattr(gs, "campaign", None) or {}
        campaign_ws = campaign.get("world_state_json") if isinstance(campaign, dict) else None
        if not isinstance(campaign_ws, dict):
            campaign_ws = {}

        # --- V2.8: Shared RAG retrieval (compute once, pass to Narrator via state) ---
        era = (campaign.get("time_period") or campaign.get("era") or "rebellion").strip() or "rebellion"

        # KG: character_context + relevant_events (shared with Narrator)
        # faction_dynamics is Director-only
        from backend.app.rag.kg_retriever import _collect_character_ids_from_state, _collect_faction_ids_from_state
        char_ids = _collect_character_ids_from_state(gs)
        faction_ids = _collect_faction_ids_from_state(gs)

        shared_char_ctx = kg_retriever.get_character_context(char_ids, era)
        shared_event_ctx = kg_retriever.get_relevant_events(char_ids, gs.current_location, era)
        director_faction_ctx = kg_retriever.get_faction_dynamics(faction_ids, era)

        # Build Director-specific KG context (character + faction + events)
        kg_parts = [p for p in [shared_char_ctx, director_faction_ctx, shared_event_ctx] if p]
        kg_context = "## Knowledge Graph Context\n" + "\n\n".join(kg_parts) if kg_parts else ""

        # Episodic memory recall (shared with Narrator — retrieve 4, Director uses first 3)
        shared_mem_block = ""
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
                    max_results=4,  # retrieve max(3,4)=4 for Narrator; Director uses first 3
                )
                shared_mem_block = epi.format_for_prompt(memories, max_chars=500)
                # Director uses a shorter version
                director_mem_block = epi.format_for_prompt(memories[:3], max_chars=400)
                if director_mem_block:
                    kg_context = (kg_context + "\n\n" + director_mem_block) if kg_context else director_mem_block
        except Exception as _epi_err:
            logger.debug("Episodic memory recall failed for Director (non-fatal): %s", _epi_err)

        # --- V2.10: Dynamic genre detection ---
        try:
            from backend.app.core.genre_triggers import detect_genre_shift
            from backend.app.world.era_pack_loader import get_era_pack as _get_era_pack_for_genre
            current_genre = campaign_ws.get("genre")
            genre_last_turn = int(campaign_ws.get("genre_last_changed_turn", 0))
            cache_turn = int(gs.turn_number or 0)
            cache_arc_stage = (state.get("arc_guidance") or {}).get("arc_stage", "SETUP")
            turns_since = max(0, cache_turn - genre_last_turn)
            loc_tags_for_genre: list[str] = []
            _genre_pack = _get_era_pack_for_genre(era)
            if _genre_pack:
                _genre_loc = _genre_pack.location_by_id(gs.current_location or "")
                if _genre_loc:
                    loc_tags_for_genre = _genre_loc.tags or []
            new_genre = detect_genre_shift(current_genre, loc_tags_for_genre, cache_arc_stage, turns_since)
            if new_genre:
                # Update genre in campaign state for this turn (persisted by Commit node)
                if isinstance(state.get("campaign"), dict):
                    ws = state["campaign"].get("world_state_json")
                    if isinstance(ws, dict):
                        ws["genre"] = new_genre
                        ws["genre_last_changed_turn"] = cache_turn
                logger.info("Genre shifted: %s -> %s (location: %s)", current_genre, new_genre, gs.current_location)
        except Exception as _genre_err:
            logger.debug("Dynamic genre detection failed (non-fatal): %s", _genre_err)

        # --- V2.10: Build NPC personality context for scene ---
        npc_personality_ctx = ""
        try:
            from backend.app.world.era_pack_loader import get_era_pack
            from backend.app.core.companions import get_companion_by_id
            era_npc_lookup: dict[str, Any] = {}
            pack = get_era_pack(era)
            if pack:
                for npc_entry in pack.all_npcs():
                    era_npc_lookup[npc_entry.id] = npc_entry.model_dump(mode="json")
                    era_npc_lookup[npc_entry.name] = npc_entry.model_dump(mode="json")
            # Build companion lookup from party members for personality injection
            companion_lookup: dict[str, Any] = {}
            party_ids = (campaign.get("party") or []) if isinstance(campaign, dict) else []
            party_state = campaign_ws.get("party_state") if isinstance(campaign_ws, dict) else {}
            companion_states = party_state.get("companion_states") if isinstance(party_state, dict) else {}
            companion_state_lookup: dict[str, Any] = {}
            for cid in party_ids:
                comp_data = get_companion_by_id(cid)
                if comp_data:
                    companion_lookup[cid] = comp_data
                    cname = comp_data.get("name", "")
                    if cname:
                        companion_lookup[cname] = comp_data
                        if isinstance(companion_states, dict) and cid in companion_states:
                            companion_state_lookup[cname] = companion_states.get(cid) or {}
                if isinstance(companion_states, dict) and cid in companion_states:
                    companion_state_lookup[cid] = companion_states.get(cid) or {}
            npc_personality_ctx = build_scene_personality_context(
                present_npcs=gs.present_npcs or [],
                era_npc_lookup=era_npc_lookup,
                companion_lookup=companion_lookup,
                companion_state_lookup=companion_state_lookup,
            )
            if npc_personality_ctx:
                kg_context = (kg_context + "\n\n## NPC Personalities\n" + npc_personality_ctx) if kg_context else ("## NPC Personalities\n" + npc_personality_ctx)
        except Exception as _pers_err:
            logger.debug("Personality profile build failed (non-fatal): %s", _pers_err)

        arc_guidance = state.get("arc_guidance") or {}
        instructions, _plan_suggestions = director.plan(gs, kg_context=kg_context, arc_guidance=arc_guidance)

        logger.debug("Director node: passing shared RAG data to Narrator via state")
        return {
            **state,
            "director_instructions": instructions,
            "suggested_actions": [],  # LLM-only suggestions via SuggestionRefiner
            "warnings": gs.warnings,
            # V2.8: Shared RAG data for Narrator (eliminates duplicate KG + episodic retrieval)
            "shared_kg_character_context": shared_char_ctx,
            "shared_kg_relevant_events": shared_event_ctx,
            "shared_episodic_memories": shared_mem_block,
            # V2.10: NPC personality context for Narrator voice guidance
            "shared_npc_personality_context": npc_personality_ctx,
        }

    return director_node
