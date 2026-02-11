"""Runtime Knowledge Graph retrieval for Director/Narrator context injection.

Queries the SQLite KG tables for structured entity/relationship/event context
and formats it as text blocks for prompt injection. Gracefully degrades to
empty strings when KG tables are missing or empty.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import TYPE_CHECKING

from backend.app.config import DEFAULT_DB_PATH
from backend.app.constants import (
    KG_MAX_RELATIONSHIPS_PER_CHAR,
    KG_MAX_EVENTS,
    KG_DIRECTOR_MAX_TOKENS,
    KG_NARRATOR_MAX_TOKENS,
)
from backend.app.core.context_budget import estimate_tokens
from backend.app.kg.predicates import PREDICATE_LABELS

if TYPE_CHECKING:
    from backend.app.models.state import GameState

logger = logging.getLogger(__name__)


class KGRetriever:
    """Runtime knowledge graph retrieval for Director/Narrator context injection."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection | None:
        """Lazily connect to SQLite, returning None if KG tables don't exist."""
        if self._conn is not None:
            return self._conn
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            # Check if KG tables exist
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='kg_entities'"
            )
            if cursor.fetchone() is None:
                conn.close()
                return None
            self._conn = conn
            return self._conn
        except Exception:
            logger.debug("KG database not available at %s", self.db_path, exc_info=True)
            return None

    def get_character_context(
        self,
        character_ids: list[str],
        era: str = "rebellion",
        max_relationships: int = KG_MAX_RELATIONSHIPS_PER_CHAR,
    ) -> str:
        """Get formatted character relationship context for prompt injection."""
        conn = self._get_conn()
        if conn is None or not character_ids:
            return ""

        lines = []
        for cid in character_ids[:6]:  # limit to 6 characters
            try:
                row = conn.execute(
                    "SELECT * FROM kg_entities WHERE id=? AND era=?", (cid, era)
                ).fetchone()
                if row is None:
                    continue

                props = json.loads(row["properties_json"] or "{}")
                name = row["canonical_name"]

                # Build character header
                species = props.get("species", "")
                role = props.get("role", "")
                faction = props.get("faction", "")
                header_parts = [name]
                if species:
                    header_parts.append(species)
                if role:
                    header_parts.append(role)
                if faction:
                    header_parts.append(faction)
                header = " (".join([header_parts[0]] + [", ".join(header_parts[1:])]) + ")" if len(header_parts) > 1 else name

                # Get relationships
                triples = conn.execute(
                    "SELECT t.*, e.canonical_name AS other_name FROM kg_triples t "
                    "JOIN kg_entities e ON t.object_id = e.id "
                    "WHERE t.subject_id=? AND t.era=? ORDER BY t.weight DESC LIMIT ?",
                    (cid, era, max_relationships),
                ).fetchall()
                incoming = conn.execute(
                    "SELECT t.*, e.canonical_name AS other_name FROM kg_triples t "
                    "JOIN kg_entities e ON t.subject_id = e.id "
                    "WHERE t.object_id=? AND t.era=? ORDER BY t.weight DESC LIMIT ?",
                    (cid, era, max_relationships),
                ).fetchall()

                rel_parts = []
                for t in triples:
                    label = PREDICATE_LABELS.get(t["predicate"], t["predicate"].lower())
                    rel_parts.append(f"{label} {t['other_name']}")
                for t in incoming:
                    label = PREDICATE_LABELS.get(t["predicate"], t["predicate"].lower())
                    rel_parts.append(f"{t['other_name']} {label} them")

                # Get arc summary if available
                arc = conn.execute(
                    "SELECT summary_text FROM kg_summaries "
                    "WHERE summary_type='CHARACTER_ARC' AND entity_id=? AND era=? LIMIT 1",
                    (cid, era),
                ).fetchone()

                char_block = f"- {header}: {'; '.join(rel_parts[:max_relationships])}"
                if arc:
                    arc_text = arc["summary_text"][:200]
                    char_block += f"\n  Arc: {arc_text}"
                lines.append(char_block)

            except sqlite3.OperationalError:
                logger.debug("KG query failed for character %s", cid, exc_info=True)
                continue

        if not lines:
            return ""
        return "### Character Relationships\n" + "\n".join(lines)

    def get_faction_dynamics(
        self,
        faction_ids: list[str] | None = None,
        era: str = "rebellion",
    ) -> str:
        """Get faction relationships and dynamics."""
        conn = self._get_conn()
        if conn is None:
            return ""

        try:
            if faction_ids:
                placeholders = ",".join("?" for _ in faction_ids)
                rows = conn.execute(
                    f"SELECT t.*, s.canonical_name AS subject_name, o.canonical_name AS object_name "
                    f"FROM kg_triples t "
                    f"JOIN kg_entities s ON t.subject_id = s.id "
                    f"JOIN kg_entities o ON t.object_id = o.id "
                    f"WHERE t.predicate IN ('OPPOSES','ALLIED_WITH','NEUTRAL_TO') "
                    f"AND t.era=? AND (t.subject_id IN ({placeholders}) OR t.object_id IN ({placeholders})) "
                    f"ORDER BY t.weight DESC LIMIT 10",
                    (era, *faction_ids, *faction_ids),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT t.*, s.canonical_name AS subject_name, o.canonical_name AS object_name "
                    "FROM kg_triples t "
                    "JOIN kg_entities s ON t.subject_id = s.id "
                    "JOIN kg_entities o ON t.object_id = o.id "
                    "WHERE t.predicate IN ('OPPOSES','ALLIED_WITH','NEUTRAL_TO') AND t.era=? "
                    "ORDER BY t.weight DESC LIMIT 10",
                    (era,),
                ).fetchall()

            if not rows:
                return ""

            lines = []
            for r in rows:
                label = PREDICATE_LABELS.get(r["predicate"], r["predicate"].lower())
                lines.append(f"- {r['subject_name']} {label} {r['object_name']}")
            return "### Faction Dynamics\n" + "\n".join(lines)
        except sqlite3.OperationalError:
            return ""

    def get_location_context(
        self,
        location_name: str,
        era: str = "rebellion",
    ) -> str:
        """Get location knowledge: type, region, controlling faction, notable characters/events."""
        conn = self._get_conn()
        if conn is None or not location_name:
            return ""

        try:
            # Try exact match, then slug match
            from backend.app.kg.entity_resolution import slugify
            slug = slugify(location_name)
            row = conn.execute(
                "SELECT * FROM kg_entities WHERE (id=? OR LOWER(canonical_name)=?) AND entity_type='LOCATION' AND era=?",
                (slug, location_name.lower(), era),
            ).fetchone()
            if row is None:
                return ""

            props = json.loads(row["properties_json"] or "{}")
            loc_type = props.get("location_type", "")
            region = props.get("region", "")
            controlling = props.get("controlling_faction", "")

            header = f"### Location: {row['canonical_name']}"
            details = []
            if loc_type:
                details.append(f"Type: {loc_type}")
            if region:
                details.append(f"Region: {region}")
            if controlling:
                details.append(f"Controlled by: {controlling}")

            # Get dossier if available
            dossier = conn.execute(
                "SELECT summary_text FROM kg_summaries "
                "WHERE summary_type='LOCATION_DOSSIER' AND entity_id=? AND era=? LIMIT 1",
                (row["id"], era),
            ).fetchone()

            result = header
            if details:
                result += "\n" + ", ".join(details)
            if dossier:
                result += "\n" + dossier["summary_text"][:300]
            return result
        except sqlite3.OperationalError:
            return ""

    def get_relevant_events(
        self,
        character_ids: list[str] | None = None,
        location: str | None = None,
        era: str = "rebellion",
        max_events: int = KG_MAX_EVENTS,
    ) -> str:
        """Get relevant events for current context."""
        conn = self._get_conn()
        if conn is None:
            return ""

        try:
            events = conn.execute(
                "SELECT * FROM kg_entities WHERE entity_type='EVENT' AND era=? "
                "ORDER BY confidence DESC LIMIT ?",
                (era, max_events * 3),  # fetch extra, filter below
            ).fetchall()
            if not events:
                return ""

            relevant = []
            char_set = set(character_ids or [])
            for ev in events:
                props = json.loads(ev["properties_json"] or "{}")
                participants = props.get("participants", [])
                ev_location = props.get("location", "")

                # Score relevance
                score = 0
                for p in participants:
                    from backend.app.kg.entity_resolution import slugify
                    if slugify(p) in char_set:
                        score += 2
                if location and location.lower() in ev_location.lower():
                    score += 1

                if score > 0 or (not character_ids and not location):
                    relevant.append((score, ev, props))

            relevant.sort(key=lambda x: x[0], reverse=True)
            relevant = relevant[:max_events]

            if not relevant:
                return ""

            lines = []
            for _, ev, props in relevant:
                outcome = props.get("outcome", "")
                lines.append(f"- {ev['canonical_name']}: {outcome[:100]}")
            return "### Relevant Events\n" + "\n".join(lines)
        except sqlite3.OperationalError:
            return ""

    def get_context_for_director(
        self,
        state: "GameState",
        max_tokens: int = KG_DIRECTOR_MAX_TOKENS,
    ) -> str:
        """Build KG context block for Director."""
        campaign = getattr(state, "campaign", None) or {}
        era = (campaign.get("time_period") or campaign.get("era") or "rebellion").strip() or "rebellion"

        # Collect character IDs from present NPCs and party
        char_ids = _collect_character_ids_from_state(state)
        faction_ids = _collect_faction_ids_from_state(state)

        parts = []
        char_ctx = self.get_character_context(char_ids, era)
        if char_ctx:
            parts.append(char_ctx)
        faction_ctx = self.get_faction_dynamics(faction_ids, era)
        if faction_ctx:
            parts.append(faction_ctx)
        event_ctx = self.get_relevant_events(char_ids, state.current_location, era)
        if event_ctx:
            parts.append(event_ctx)

        if not parts:
            return ""

        full = "## Knowledge Graph Context\n" + "\n\n".join(parts)
        return _trim_to_tokens(full, max_tokens)

    def get_context_for_narrator(
        self,
        state: "GameState",
        max_tokens: int = KG_NARRATOR_MAX_TOKENS,
    ) -> str:
        """Build KG context block for Narrator."""
        campaign = getattr(state, "campaign", None) or {}
        era = (campaign.get("time_period") or campaign.get("era") or "rebellion").strip() or "rebellion"

        char_ids = _collect_character_ids_from_state(state)

        parts = []
        char_ctx = self.get_character_context(char_ids, era)
        if char_ctx:
            parts.append(char_ctx)
        loc_ctx = self.get_location_context(state.current_location or "", era)
        if loc_ctx:
            parts.append(loc_ctx)
        event_ctx = self.get_relevant_events(char_ids, state.current_location, era)
        if event_ctx:
            parts.append(event_ctx)

        if not parts:
            return ""

        full = "## Knowledge Graph Context\n" + "\n\n".join(parts)
        return _trim_to_tokens(full, max_tokens)


def _collect_character_ids_from_state(state: "GameState") -> list[str]:
    """Collect character IDs from present NPCs and party."""
    ids = []
    seen = set()
    for npc in (state.present_npcs or []):
        cid = npc.get("id", "")
        if cid and cid not in seen:
            ids.append(cid)
            seen.add(cid)
    campaign = getattr(state, "campaign", None) or {}
    for cid in (campaign.get("party") or []):
        if cid and cid not in seen:
            ids.append(str(cid))
            seen.add(str(cid))
    return ids


def _collect_faction_ids_from_state(state: "GameState") -> list[str]:
    """Collect faction IDs from campaign active_factions."""
    campaign = getattr(state, "campaign", None) or {}
    ws = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
    if not isinstance(ws, dict):
        return []
    factions = ws.get("active_factions") or []
    ids = []
    for f in factions:
        if isinstance(f, dict):
            name = f.get("name", "")
            if name:
                from backend.app.kg.entity_resolution import slugify
                ids.append(slugify(name))
    return ids


def _trim_to_tokens(text: str, max_tokens: int) -> str:
    """Trim text to fit within token budget."""
    tokens = estimate_tokens(text)
    if tokens <= max_tokens:
        return text
    # Rough trim by cutting lines from the end
    lines = text.split("\n")
    while lines and estimate_tokens("\n".join(lines)) > max_tokens:
        lines.pop()
    return "\n".join(lines)
