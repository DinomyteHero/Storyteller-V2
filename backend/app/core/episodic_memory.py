"""Episodic memory system for long-term recall across turns.

V3.0: Hybrid retrieval — vector similarity (when embeddings available) blended
with keyword-overlap + recency weighting. Graceful fallback to keyword-only
if sentence-transformers is not installed.
"""
from __future__ import annotations

import json
import logging
import math
import re
import sqlite3
from typing import Any

from backend.app.constants import (
    MEMORY_CRYSTALLIZED_MAX,
    MEMORY_HOT_TURNS,
    MEMORY_WARM_TURNS,
)

logger = logging.getLogger(__name__)

# Words too common to be useful keywords
_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "before", "after", "above", "below", "between", "under", "again",
    "further", "then", "once", "here", "there", "when", "where", "why",
    "how", "all", "each", "every", "both", "few", "more", "most", "other",
    "some", "such", "no", "nor", "not", "only", "own", "same", "so",
    "than", "too", "very", "just", "because", "but", "and", "or", "if",
    "while", "about", "up", "out", "off", "over", "down", "this", "that",
    "it", "its", "they", "them", "their", "he", "she", "his", "her",
    "him", "you", "your", "we", "our", "i", "my", "me",
})

# ── Embedding helpers ────────────────────────────────────────────────

_EMBEDDINGS_AVAILABLE: bool | None = None


def _check_embeddings() -> bool:
    """Check if embedding support is available (lazy, cached)."""
    global _EMBEDDINGS_AVAILABLE
    if _EMBEDDINGS_AVAILABLE is not None:
        return _EMBEDDINGS_AVAILABLE
    try:
        from ingestion.embedding import encode  # noqa: F401
        _EMBEDDINGS_AVAILABLE = True
    except (ImportError, Exception):
        _EMBEDDINGS_AVAILABLE = False
        logger.debug("Episodic memory: embeddings unavailable, using keyword-only recall")
    return _EMBEDDINGS_AVAILABLE


def _embed_text(text: str) -> list[float] | None:
    """Embed text to a vector. Returns None if embeddings unavailable."""
    if not _check_embeddings():
        return None
    try:
        from ingestion.embedding import encode
        vectors = encode(text)
        return vectors[0] if vectors else None
    except Exception as e:
        logger.debug("Episodic memory: embedding failed (non-fatal): %s", e)
        return None


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _summarize_narrative(text: str, max_len: int = 200) -> str:
    """Create a compressed summary of narrative text for storage.

    Phase 3.3: Enhanced to capture richer context — prioritizes sentences
    containing character names, dialogue indicators, emotional language,
    and action verbs over generic description.
    """
    if not text:
        return ""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    if len(sentences) <= 2:
        summary = text.strip()
    else:
        # Phase 3.3: Score sentences by narrative richness
        # Prioritize sentences with dialogue, character interaction,
        # emotional content, or action
        _rich_indicators = re.compile(
            r'(said|asked|replied|whispered|growled|demanded|promised|warned'
            r'|trust|betray|hostile|friendly|afraid|angry|relieved|desperate'
            r'|discovered|revealed|learned|realized|understood|decided'
            r'|killed|died|attacked|fled|escaped|surrendered'
            r'|quest|mission|objective|artifact|secret)',
            re.IGNORECASE,
        )
        scored = []
        for i, sent in enumerate(sentences):
            score = 0
            # Dialogue or character speech
            if '"' in sent or '\u201c' in sent:
                score += 3
            # Rich narrative indicators
            score += len(_rich_indicators.findall(sent))
            # Proper nouns (likely character names)
            proper_nouns = re.findall(r'\b[A-Z][a-z]{2,}', sent)
            score += min(len(proper_nouns), 2)
            # Slight recency bias — later sentences often carry resolution
            score += i * 0.1
            scored.append((score, i, sent))

        scored.sort(key=lambda x: x[0], reverse=True)
        # Take the top 2-3 most informative sentences, in original order
        top_indices = sorted([s[1] for s in scored[:3]])
        selected = [sentences[i] for i in top_indices]
        summary = " ".join(selected)

    return summary[:max_len]


# ── Keyword extraction ───────────────────────────────────────────────

# Phase 3.3: High-value narrative terms get priority in keyword extraction
_NARRATIVE_PRIORITY_TERMS = frozenset({
    "killed", "died", "death", "betrayed", "betrayal", "trust", "hostile",
    "allied", "discovered", "revealed", "secret", "quest", "mission",
    "artifact", "escaped", "captured", "surrendered", "promised", "warned",
    "attacked", "ambush", "defeated", "victory", "failed", "critical",
    "faction", "reputation", "influence", "loyalty", "companion",
})


def _extract_keywords(text: str, max_keywords: int = 20) -> list[str]:
    """Extract meaningful keywords from text, filtering stop words.

    Phase 3.3: Enhanced to prioritize narrative-significant terms (relationship
    words, quest terms, emotional language) over generic descriptors.
    """
    words = re.findall(r"[a-zA-Z']{3,}", text.lower())
    seen: set[str] = set()
    priority_keywords: list[str] = []
    regular_keywords: list[str] = []
    # Also capture proper nouns (character/place names) from original text
    proper_nouns = re.findall(r'\b[A-Z][a-z]{2,}(?:\s[A-Z][a-z]{2,})?', text)
    for pn in proper_nouns:
        pn_lower = pn.lower()
        if pn_lower not in _STOP_WORDS and pn_lower not in seen:
            seen.add(pn_lower)
            priority_keywords.append(pn_lower)

    for w in words:
        if w in _STOP_WORDS or w in seen:
            continue
        seen.add(w)
        if w in _NARRATIVE_PRIORITY_TERMS:
            priority_keywords.append(w)
        else:
            regular_keywords.append(w)

    # Merge: priority terms first, then regular, up to max
    keywords = priority_keywords[:max_keywords]
    remaining = max_keywords - len(keywords)
    if remaining > 0:
        keywords.extend(regular_keywords[:remaining])
    return keywords[:max_keywords]


def _is_pivotal(
    events: list[dict],
    arc_stage: str | None,
    prev_arc_stage: str | None,
    stress_level: int,
) -> bool:
    """Determine if a turn is a pivotal moment worth long-term retention.

    Pivotal moments: critical successes/failures, arc transitions,
    high stress, significant events.
    """
    # Arc stage transition
    if arc_stage and prev_arc_stage and arc_stage != prev_arc_stage:
        return True

    # High stress
    if stress_level >= 8:
        return True

    # Check for critical outcomes or significant events
    for ev in events:
        etype = ev.get("event_type", "")
        payload = ev.get("payload") or {}
        if etype == "CRITICAL_SUCCESS" or etype == "CRITICAL_FAILURE":
            return True
        if payload.get("critical_outcome") in ("CRITICAL_SUCCESS", "CRITICAL_FAILURE"):
            return True
        # Relationship milestones
        if etype in ("COMPANION_LOYAL", "COMPANION_BETRAYAL", "FACTION_SHIFT"):
            return True
        # Death or major loss
        if etype in ("NPC_DEATH", "PLAYER_DEATH", "ITEM_LOST_MAJOR"):
            return True

    return False


def _tier_limits(max_results: int) -> tuple[int, int, int]:
    """Allocate retrieval slots across crystallized/warm/cold tiers."""
    total = max(1, int(max_results or 1))
    crystallized = max(1, round(total * 0.4))
    warm = max(1, round(total * 0.4))
    cold = max(0, total - crystallized - warm)
    while crystallized + warm + cold > total:
        if warm > 1:
            warm -= 1
        elif crystallized > 1:
            crystallized -= 1
        elif cold > 0:
            cold -= 1
        else:
            break
    while crystallized + warm + cold < total:
        warm += 1
    return crystallized, warm, cold


class EpisodicMemory:
    """Store and recall episodic memories for a campaign.

    V3.0: Hybrid retrieval — vector similarity blended with keyword overlap
    + recency weighting. Falls back to keyword-only if embeddings unavailable.
    """

    def __init__(self, conn: sqlite3.Connection, campaign_id: str) -> None:
        self._conn = conn
        self._campaign_id = campaign_id

    def _has_embedding_column(self) -> bool:
        """Check if the embedding_json column exists (migration may not have run)."""
        try:
            cursor = self._conn.execute("PRAGMA table_info(episodic_memories)")
            columns = {row[1] for row in cursor.fetchall()}
            return "embedding_json" in columns
        except (OSError, Exception):
            return False

    def _has_crystallized_table(self) -> bool:
        """Check if crystallized_memories table exists."""
        try:
            row = self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='crystallized_memories'"
            ).fetchone()
            return bool(row)
        except (OSError, Exception):
            return False

    def add_crystallized_memory(
        self,
        turn_number: int,
        memory_type: str,
        summary: str,
        full_text: str = "",
        npcs_involved: list[str] | None = None,
        location: str | None = None,
        emotional_tag: str | None = None,
    ) -> None:
        """Persist a high-signal memory that should survive long campaigns."""
        if not self._has_crystallized_table():
            return
        trimmed_summary = (summary or "").strip()
        if not trimmed_summary:
            return
        npcs = [str(n).strip() for n in (npcs_involved or []) if str(n).strip()]
        try:
            self._conn.execute(
                """INSERT INTO crystallized_memories
                   (campaign_id, turn_number, memory_type, summary, full_text, npcs_involved, location, emotional_tag)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    self._campaign_id,
                    int(turn_number),
                    str(memory_type or "system"),
                    trimmed_summary[:400],
                    (full_text or "")[:2000],
                    json.dumps(npcs[:10]),
                    (location or "")[:120] or None,
                    (emotional_tag or "")[:40] or None,
                ),
            )
            # Keep most recent N crystallized memories per campaign.
            self._conn.execute(
                """DELETE FROM crystallized_memories
                   WHERE campaign_id = ?
                     AND id NOT IN (
                       SELECT id
                       FROM crystallized_memories
                       WHERE campaign_id = ?
                       ORDER BY turn_number DESC, id DESC
                       LIMIT ?
                     )""",
                (self._campaign_id, self._campaign_id, MEMORY_CRYSTALLIZED_MAX),
            )
        except Exception as e:
            logger.warning("Failed to store crystallized memory (non-fatal): %s", e)

    def store(
        self,
        turn_number: int,
        location_id: str | None,
        npcs_present: list[str],
        key_events: list[dict],
        stress_level: int = 0,
        arc_stage: str | None = None,
        hero_beat: str | None = None,
        narrative_text: str = "",
        prev_arc_stage: str | None = None,
    ) -> None:
        """Store an episodic memory entry for a turn."""
        # Extract keywords from narrative + events
        event_texts = []
        for ev in key_events:
            etype = ev.get("event_type", "")
            payload = ev.get("payload") or {}
            event_texts.append(etype)
            for v in payload.values():
                if isinstance(v, str):
                    event_texts.append(v)

        combined_text = " ".join([narrative_text] + event_texts + npcs_present)
        keywords = _extract_keywords(combined_text)
        keywords_str = " ".join(keywords)

        pivotal = _is_pivotal(key_events, arc_stage, prev_arc_stage, stress_level)

        # V3.0: Compute embedding and summary
        has_emb_col = self._has_embedding_column()
        embedding = _embed_text(combined_text) if has_emb_col else None
        summary = _summarize_narrative(narrative_text) if has_emb_col else ""

        try:
            if has_emb_col:
                self._conn.execute(
                    """INSERT INTO episodic_memories
                       (campaign_id, turn_number, location_id, npcs_present_json,
                        key_events_json, stress_level, arc_stage, hero_beat,
                        keywords, is_pivotal, embedding_json, narrative_summary)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        self._campaign_id,
                        turn_number,
                        location_id,
                        json.dumps(npcs_present),
                        json.dumps(key_events[:10]),  # Cap stored events
                        stress_level,
                        arc_stage,
                        hero_beat,
                        keywords_str,
                        1 if pivotal else 0,
                        json.dumps(embedding) if embedding else None,
                        summary,
                    ),
                )
            else:
                self._conn.execute(
                    """INSERT INTO episodic_memories
                       (campaign_id, turn_number, location_id, npcs_present_json,
                        key_events_json, stress_level, arc_stage, hero_beat,
                        keywords, is_pivotal)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        self._campaign_id,
                        turn_number,
                        location_id,
                        json.dumps(npcs_present),
                        json.dumps(key_events[:10]),
                        stress_level,
                        arc_stage,
                        hero_beat,
                        keywords_str,
                        1 if pivotal else 0,
                    ),
                )
        except Exception as e:
            logger.warning("Failed to store episodic memory (non-fatal): %s", e)

    def recall(
        self,
        query_text: str = "",
        current_turn: int = 0,
        location_id: str | None = None,
        npcs: list[str] | None = None,
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Recall relevant episodic memories using hybrid + tiered scoring."""
        has_emb_col = self._has_embedding_column()
        select_cols = (
            "turn_number, location_id, npcs_present_json, "
            "key_events_json, stress_level, arc_stage, "
            "hero_beat, keywords, is_pivotal"
        )
        if has_emb_col:
            select_cols += ", embedding_json, narrative_summary"

        try:
            rows = self._conn.execute(
                f"""SELECT {select_cols}
                   FROM episodic_memories
                   WHERE campaign_id = ?
                   ORDER BY turn_number DESC
                   LIMIT 100""",
                (self._campaign_id,),
            ).fetchall()
        except Exception as e:
            logger.warning("Failed to recall episodic memories (non-fatal): %s", e)
            return []

        if not rows:
            return []

        query_keywords = set(_extract_keywords(query_text))
        npc_set = set(n.lower() for n in (npcs or []))

        # Compute query embedding for vector similarity.
        query_embedding: list[float] | None = None
        if has_emb_col and query_text:
            query_embedding = _embed_text(query_text)

        scored: list[tuple[float, dict]] = []
        for row in rows:
            if has_emb_col:
                turn_num, loc, npcs_json, events_json, stress, arc, beat, kw_str, pivotal, emb_json, summary = row
            else:
                turn_num, loc, npcs_json, events_json, stress, arc, beat, kw_str, pivotal = row
                emb_json = None
                summary = ""

            mem_keywords = set(kw_str.split()) if kw_str else set()
            mem_npcs = set()
            try:
                mem_npcs = set(n.lower() for n in json.loads(npcs_json or "[]"))
            except (json.JSONDecodeError, TypeError, ValueError):
                pass

            score = 0.0

            # Vector similarity is the dominant retrieval signal when present.
            if query_embedding and emb_json:
                try:
                    mem_embedding = json.loads(emb_json)
                    sim = _cosine_similarity(query_embedding, mem_embedding)
                    score += max(0.0, sim) * 5.0
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass

            # Keyword overlap (secondary signal).
            if query_keywords:
                overlap = len(query_keywords & mem_keywords)
                score += overlap

            if pivotal:
                score += 3.0

            if location_id and loc and location_id.lower() == loc.lower():
                score += 2.0

            if npc_set:
                npc_overlap = len(npc_set & mem_npcs)
                score += npc_overlap

            distance = abs(current_turn - turn_num)
            recency_factor = 1.0 / (1.0 + distance * 0.05)
            score *= recency_factor

            if score < 0.5:
                continue

            try:
                events = json.loads(events_json or "[]")
            except (json.JSONDecodeError, TypeError, ValueError):
                events = []

            scored.append((score, {
                "turn_number": turn_num,
                "location_id": loc,
                "npcs_present": list(mem_npcs),
                "key_events": events,
                "stress_level": stress,
                "arc_stage": arc,
                "hero_beat": beat,
                "keywords": list(mem_keywords),
                "is_pivotal": bool(pivotal),
                "relevance_score": round(score, 2),
                "narrative_summary": summary or "",
                "memory_tier": (
                    "hot" if distance <= MEMORY_HOT_TURNS
                    else ("warm" if distance <= MEMORY_WARM_TURNS else "cold")
                ),
            }))

        # Retrieve crystallized memories and blend by tier budget.
        crystallized_scored: list[tuple[float, dict[str, Any]]] = []
        if self._has_crystallized_table():
            try:
                c_rows = self._conn.execute(
                    """SELECT turn_number, memory_type, summary, full_text, npcs_involved, location, emotional_tag
                       FROM crystallized_memories
                       WHERE campaign_id = ?
                       ORDER BY turn_number DESC
                       LIMIT 200""",
                    (self._campaign_id,),
                ).fetchall()
                for row in c_rows:
                    c_turn = int(row["turn_number"])
                    c_summary = str(row["summary"] or "").strip()
                    c_full = str(row["full_text"] or "").strip()
                    c_loc = str(row["location"] or "").strip()
                    c_tag = str(row["emotional_tag"] or "").strip()
                    c_text = f"{c_summary} {c_full}".strip()
                    c_keywords = set(_extract_keywords(c_text))
                    try:
                        c_npcs = [str(x).strip().lower() for x in json.loads(row["npcs_involved"] or "[]") if str(x).strip()]
                    except (json.JSONDecodeError, TypeError, ValueError):
                        c_npcs = []
                    c_score = 2.5  # Base priority for crystallized memories.
                    if query_keywords:
                        c_score += len(query_keywords & c_keywords)
                    if location_id and c_loc and location_id.lower() == c_loc.lower():
                        c_score += 2.0
                    if npc_set:
                        c_score += len(npc_set & set(c_npcs))
                    if c_tag:
                        c_score += 0.5
                    distance = abs(current_turn - c_turn)
                    c_score *= 1.0 / (1.0 + distance * 0.03)
                    if c_score < 0.5:
                        continue
                    crystallized_scored.append((
                        c_score,
                        {
                            "turn_number": c_turn,
                            "location_id": c_loc or None,
                            "npcs_present": c_npcs,
                            "key_events": [],
                            "stress_level": 0,
                            "arc_stage": None,
                            "hero_beat": None,
                            "keywords": list(c_keywords),
                            "is_pivotal": True,
                            "is_crystallized": True,
                            "memory_type": str(row["memory_type"] or "system"),
                            "relevance_score": round(c_score, 2),
                            "narrative_summary": c_summary or c_full[:220],
                        },
                    ))
            except Exception as e:
                logger.warning("Failed to recall crystallized memories (non-fatal): %s", e)

        scored.sort(key=lambda x: x[0], reverse=True)
        crystallized_scored.sort(key=lambda x: x[0], reverse=True)

        crystallized_limit, warm_limit, cold_limit = _tier_limits(max_results)
        hot_or_warm = [item for item in scored if item[1].get("memory_tier") in {"hot", "warm"}]
        cold = [item for item in scored if item[1].get("memory_tier") == "cold"]

        out: list[dict[str, Any]] = []
        out.extend([item[1] for item in crystallized_scored[:crystallized_limit]])
        out.extend([item[1] for item in hot_or_warm[:warm_limit]])
        out.extend([item[1] for item in cold[:cold_limit]])

        if len(out) < max_results:
            # Backfill from remaining non-selected memories by score.
            used_turns = {(m.get("turn_number"), m.get("memory_type"), bool(m.get("is_crystallized"))) for m in out}
            for _, mem in scored:
                key = (mem.get("turn_number"), mem.get("memory_type"), bool(mem.get("is_crystallized")))
                if key in used_turns:
                    continue
                out.append(mem)
                used_turns.add(key)
                if len(out) >= max_results:
                    break
            if len(out) < max_results:
                for _, mem in crystallized_scored:
                    key = (mem.get("turn_number"), mem.get("memory_type"), bool(mem.get("is_crystallized")))
                    if key in used_turns:
                        continue
                    out.append(mem)
                    used_turns.add(key)
                    if len(out) >= max_results:
                        break

        return out[:max_results]

    def format_for_prompt(self, memories: list[dict], max_chars: int = 600) -> str:
        """Format recalled memories as a context block for LLM prompts.

        Phase 3.3: Enhanced to surface relationship changes, dialogue topics,
        quest progress, and emotional beats alongside narrative summaries.
        """
        if not memories:
            return ""

        lines = ["## Relevant Past Episodes"]
        char_count = len(lines[0])

        for mem in memories:
            turn = mem.get("turn_number", "?")
            loc = mem.get("location_id") or "unknown"
            npcs = mem.get("npcs_present") or []
            events = mem.get("key_events") or []
            pivotal = mem.get("is_pivotal", False)
            beat = mem.get("hero_beat") or ""
            summary = mem.get("narrative_summary") or ""
            is_crystallized = bool(mem.get("is_crystallized"))

            line_parts = [f"Turn {turn}"]
            if loc:
                line_parts.append(f"at {loc}")
            if npcs:
                line_parts.append(f"with {', '.join(npcs[:3])}")
            if beat:
                line_parts.append(f"[{beat}]")
            if is_crystallized:
                line_parts.append("(CRYSTALLIZED)")
            if pivotal:
                line_parts.append("(PIVOTAL)")

            # Phase 3.3: Extract rich event context
            event_details: list[str] = []
            for ev in events[:5]:
                if not isinstance(ev, dict):
                    continue
                etype = (ev.get("event_type") or "").upper()
                payload = ev.get("payload") or {}
                if not isinstance(payload, dict):
                    payload = {}

                # Relationship changes
                if etype in ("RELATIONSHIP", "RELATIONSHIP_CHANGE", "COMPANION_AFFINITY"):
                    npc = payload.get("npc_id") or payload.get("npc_name") or ""
                    delta = payload.get("delta", 0)
                    reason = payload.get("reason") or ""
                    if npc and delta:
                        sign = "+" if int(delta) > 0 else ""
                        detail = f"{npc} {sign}{delta} influence"
                        if reason:
                            detail += f" ({reason[:30]})"
                        event_details.append(detail)

                # Dialogue topics
                elif etype in ("DIALOGUE", "TALK"):
                    topic = payload.get("topic") or payload.get("text") or ""
                    if topic:
                        event_details.append(f"discussed: {str(topic)[:40]}")

                # Quest progress
                elif etype.startswith("QUEST_") or etype.startswith("OBJECTIVE_"):
                    quest = payload.get("quest") or payload.get("quest_name") or payload.get("title") or ""
                    if quest:
                        status = etype.replace("QUEST_", "").replace("OBJECTIVE_", "").lower()
                        event_details.append(f"quest {status}: {quest[:30]}")

                # Emotional beats
                elif etype in ("CRITICAL_SUCCESS", "CRITICAL_FAILURE"):
                    action = payload.get("action_type") or ""
                    event_details.append(f"{'triumph' if 'SUCCESS' in etype else 'disaster'}{f' on {action}' if action else ''}")

                # Deaths
                elif etype in ("NPC_DEATH", "DEATH"):
                    name = payload.get("npc_name") or payload.get("name") or ""
                    if name:
                        event_details.append(f"{name} killed")

                # Fallback to generic summary
                else:
                    text = payload.get("text") or payload.get("description") or ""
                    if text:
                        event_details.append(f"{etype}: {text[:50]}")
                    elif etype:
                        event_details.append(etype)

            # V3.0 + Phase 3.3: Build the line with enriched context
            if summary and event_details:
                line = "- " + ", ".join(line_parts) + " | " + summary + " [" + "; ".join(event_details[:3]) + "]"
            elif summary:
                line = "- " + ", ".join(line_parts) + " | " + summary
            elif event_details:
                line = "- " + ", ".join(line_parts) + " | " + "; ".join(event_details[:4])
            else:
                line = "- " + ", ".join(line_parts)

            if char_count + len(line) + 1 > max_chars:
                break
            lines.append(line)
            char_count += len(line) + 1

        return "\n".join(lines) if len(lines) > 1 else ""


def _extract_open_threads(world_state: dict[str, Any]) -> list[str]:
    """Extract open narrative threads from common world-state ledger locations."""
    candidates: list[str] = []
    for key in ("narrative_ledger", "ledger"):
        ledger = world_state.get(key)
        if not isinstance(ledger, dict):
            continue
        threads = ledger.get("open_threads") or ledger.get("active_threads")
        if isinstance(threads, list):
            for item in threads:
                if isinstance(item, str) and item.strip():
                    candidates.append(item.strip())
                elif isinstance(item, dict):
                    text = item.get("title") or item.get("text") or item.get("summary")
                    if isinstance(text, str) and text.strip():
                        candidates.append(text.strip())
    seen: set[str] = set()
    deduped: list[str] = []
    for thread in candidates:
        key = thread.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(thread)
    return deduped[:5]


def _extract_active_quests(world_state: dict[str, Any]) -> list[str]:
    """Extract active quest names from quest_log variants."""
    quest_log = world_state.get("quest_log")
    if not isinstance(quest_log, dict):
        return []

    names: list[str] = []
    active = quest_log.get("active")
    if isinstance(active, list):
        for item in active:
            if isinstance(item, str) and item.strip():
                names.append(item.strip())
            elif isinstance(item, dict):
                title = item.get("title") or item.get("name") or item.get("quest")
                if isinstance(title, str) and title.strip():
                    names.append(title.strip())

    if not names:
        for _, item in quest_log.items():
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "").lower()
            if status not in {"active", "in_progress", "ongoing"}:
                continue
            title = item.get("title") or item.get("name") or item.get("quest")
            if isinstance(title, str) and title.strip():
                names.append(title.strip())

    seen: set[str] = set()
    deduped: list[str] = []
    for name in names:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(name)
    return deduped[:5]


def _event_to_summary(events_json: str | None) -> str:
    """Best-effort narrative summary from key events JSON."""
    if not events_json:
        return ""
    try:
        events = json.loads(events_json)
    except (json.JSONDecodeError, TypeError, ValueError):
        return ""
    if not isinstance(events, list):
        return ""
    for event in events:
        if not isinstance(event, dict):
            continue
        payload = event.get("payload") or {}
        for field in ("text", "description", "summary"):
            value = payload.get(field) if isinstance(payload, dict) else None
            if isinstance(value, str) and value.strip():
                return value.strip()[:220]
        etype = event.get("event_type")
        if isinstance(etype, str) and etype.strip():
            return etype.replace("_", " ").title()
    return ""


def generate_story_summary(
    conn: sqlite3.Connection,
    campaign_id: str,
    world_state: dict[str, Any] | None = None,
    max_recent_memories: int = 5,
) -> dict[str, Any]:
    """Build a lightweight campaign recap for the play screen."""
    ws = world_state if isinstance(world_state, dict) else {}
    arc_stage = str(ws.get("arc_stage") or "SETUP").upper()
    current_beat = str(ws.get("current_beat") or "")

    open_threads = _extract_open_threads(ws)
    active_quests = _extract_active_quests(ws)

    recent_memories: list[str] = []
    try:
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(episodic_memories)").fetchall()
        }
        has_summary_col = "narrative_summary" in cols
        if has_summary_col:
            rows = conn.execute(
                """SELECT turn_number, narrative_summary, key_events_json
                   FROM episodic_memories
                   WHERE campaign_id = ?
                   ORDER BY turn_number DESC
                   LIMIT ?""",
                (campaign_id, max_recent_memories),
            ).fetchall()
            for row in rows:
                summary = str(row["narrative_summary"] or "").strip()
                if not summary:
                    summary = _event_to_summary(row["key_events_json"])
                if summary:
                    recent_memories.append(summary)
        else:
            rows = conn.execute(
                """SELECT turn_number, key_events_json
                   FROM episodic_memories
                   WHERE campaign_id = ?
                   ORDER BY turn_number DESC
                   LIMIT ?""",
                (campaign_id, max_recent_memories),
            ).fetchall()
            for row in rows:
                summary = _event_to_summary(row["key_events_json"])
                if summary:
                    recent_memories.append(summary)
    except Exception as e:
        logger.warning("Failed to build story summary memories (non-fatal): %s", e)

    return {
        "arc_stage": arc_stage,
        "current_beat": current_beat,
        "open_threads": open_threads,
        "recent_memories": recent_memories[:max_recent_memories],
        "active_quests": active_quests,
    }
