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
    """Create a compressed summary of narrative text for storage."""
    if not text:
        return ""
    # Take first and last sentences for a compressed summary
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    if len(sentences) <= 2:
        summary = text.strip()
    else:
        summary = sentences[0] + " ... " + sentences[-1]
    return summary[:max_len]


# ── Keyword extraction ───────────────────────────────────────────────

def _extract_keywords(text: str, max_keywords: int = 20) -> list[str]:
    """Extract meaningful keywords from text, filtering stop words."""
    words = re.findall(r"[a-zA-Z']{3,}", text.lower())
    seen: set[str] = set()
    keywords: list[str] = []
    for w in words:
        if w not in _STOP_WORDS and w not in seen:
            seen.add(w)
            keywords.append(w)
            if len(keywords) >= max_keywords:
                break
    return keywords


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
        except Exception:
            return False

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
        """Recall relevant episodic memories using hybrid scoring.

        V3.0 scoring (when embeddings available):
        - Vector similarity: cosine_sim * 5.0 (primary signal)
        - Keyword overlap: +1 per matching keyword (secondary)
        - Pivotal bonus: +3 for pivotal moments
        - Location match: +2 if same location
        - NPC overlap: +1 per shared NPC
        - Recency decay: score * (1 / (1 + distance * 0.05))

        Falls back to keyword-only scoring if embeddings unavailable.
        """
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

        # V3.0: Compute query embedding for vector similarity
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
            except Exception:
                pass

            # Score calculation
            score = 0.0

            # V3.0: Vector similarity (primary signal when available)
            if query_embedding and emb_json:
                try:
                    mem_embedding = json.loads(emb_json)
                    sim = _cosine_similarity(query_embedding, mem_embedding)
                    score += max(0.0, sim) * 5.0  # Scale to make it dominant signal
                except Exception:
                    pass

            # Keyword overlap (secondary signal)
            if query_keywords:
                overlap = len(query_keywords & mem_keywords)
                score += overlap

            # Pivotal bonus
            if pivotal:
                score += 3.0

            # Location match
            if location_id and loc and location_id.lower() == loc.lower():
                score += 2.0

            # NPC overlap
            if npc_set:
                npc_overlap = len(npc_set & mem_npcs)
                score += npc_overlap

            # Recency decay
            distance = abs(current_turn - turn_num)
            recency_factor = 1.0 / (1.0 + distance * 0.05)
            score *= recency_factor

            # Minimum relevance threshold
            if score < 0.5:
                continue

            try:
                events = json.loads(events_json or "[]")
            except Exception:
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
            }))

        # Sort by score descending, return top results
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:max_results]]

    def format_for_prompt(self, memories: list[dict], max_chars: int = 600) -> str:
        """Format recalled memories as a context block for LLM prompts."""
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

            line_parts = [f"Turn {turn}"]
            if loc:
                line_parts.append(f"at {loc}")
            if npcs:
                line_parts.append(f"with {', '.join(npcs[:3])}")
            if beat:
                line_parts.append(f"[{beat}]")
            if pivotal:
                line_parts.append("(PIVOTAL)")

            # V3.0: Prefer narrative summary over raw event types
            if summary:
                line = "- " + ", ".join(line_parts) + " | " + summary
            else:
                # Add key event summaries
                event_summaries = []
                for ev in events[:3]:
                    etype = ev.get("event_type", "")
                    payload = ev.get("payload") or {}
                    text = payload.get("text") or payload.get("description") or ""
                    if text:
                        event_summaries.append(f"{etype}: {text[:60]}")
                    elif etype:
                        event_summaries.append(etype)

                line = "- " + ", ".join(line_parts)
                if event_summaries:
                    line += " | " + "; ".join(event_summaries)

            if char_count + len(line) + 1 > max_chars:
                break
            lines.append(line)
            char_count += len(line) + 1

        return "\n".join(lines) if len(lines) > 1 else ""
