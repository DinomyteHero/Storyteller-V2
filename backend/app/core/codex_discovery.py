"""CodexDiscovery: auto-unlock codex entries when related lore is cited (Phase 4.2).

When the Director or Narrator retrieves lore chunks tagged with certain lore_chunk_tags,
we cross-reference those tags against EraCodexEntry definitions in the era pack.
Any codex entry whose lore_chunk_tags overlap with the retrieved citations is unlocked.

Unlock conditions:
1. A lore citation (chunk tag) overlaps with ``EraCodexEntry.lore_chunk_tags``.
2. The entry's ``spoiler_tier`` must be <= the current campaign's max revealed tier.
3. Once-only: entries are added to ``world_state_json["unlocked_codex_ids"]`` and
   never re-triggered.

Called by the Commit node after saving lore citations for the turn.

Usage::

    from backend.app.core.codex_discovery import CodexDiscovery
    discovery = CodexDiscovery()
    newly_unlocked = discovery.check_unlocks(
        world_state=ws,
        lore_citations=citations,
        era_pack=era_pack,
    )
    # Persist newly_unlocked to world_state["unlocked_codex_ids"]
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Default max spoiler tier to reveal automatically (0=always safe, 3=major spoilers)
_DEFAULT_MAX_SPOILER_TIER = 1


class CodexDiscovery:
    """Checks lore citations against era pack codex entries to unlock discoveries.

    Stateless — instantiate once, call check_unlocks() per turn.
    """

    def __init__(self, max_spoiler_tier: int = _DEFAULT_MAX_SPOILER_TIER) -> None:
        """Args:
            max_spoiler_tier: Maximum spoiler tier to auto-unlock (0-3).
                              Can be overridden per-campaign via world_state.
        """
        self._default_max_spoiler_tier = max_spoiler_tier

    def check_unlocks(
        self,
        world_state: dict[str, Any],
        lore_citations: list[Any] | None = None,
        era_pack: Any | None = None,
    ) -> list[str]:
        """Check if any lore citations trigger codex entry unlocks.

        Args:
            world_state: The current world_state_json dict (mutable — updated in-place).
            lore_citations: List of lore citation dicts from the current turn. Each may
                            have a ``tags``, ``chunk_tags``, ``doc_tags``, or
                            ``related_npcs`` field.
            era_pack: EraPack instance for the current era (must have .codex list).

        Returns:
            List of newly unlocked codex entry IDs (empty if none).
        """
        if not lore_citations or era_pack is None:
            return []

        codex_entries = getattr(era_pack, "codex", []) or []
        if not codex_entries:
            return []

        # Current unlocked set
        already_unlocked: set[str] = set(world_state.get("unlocked_codex_ids") or [])

        # Determine max spoiler tier for this campaign
        max_tier = int(
            world_state.get("codex_max_spoiler_tier", self._default_max_spoiler_tier)
        )

        # Collect all tag strings from citations
        citation_tags = self._extract_citation_tags(lore_citations)
        if not citation_tags:
            return []

        newly_unlocked: list[str] = []

        for entry in codex_entries:
            entry_id = getattr(entry, "id", None) or (entry.get("id") if isinstance(entry, dict) else None)
            if not entry_id:
                continue
            if entry_id in already_unlocked:
                continue

            # Check spoiler tier
            entry_spoiler_tier = int(
                getattr(entry, "spoiler_tier", 0) if not isinstance(entry, dict)
                else entry.get("spoiler_tier", 0)
            )
            if entry_spoiler_tier > max_tier:
                continue

            # Check unlock_conditions override (if set, skip auto-tag-based unlock)
            unlock_cond = (
                getattr(entry, "unlock_conditions", None) if not isinstance(entry, dict)
                else entry.get("unlock_conditions")
            )
            if unlock_cond:
                # Custom condition present — skip automatic tag-based unlock
                # (manual unlock via explicit quest/event trigger)
                continue

            # Check lore_chunk_tags overlap
            entry_tags: list[str] = (
                list(getattr(entry, "lore_chunk_tags", []) or [])
                if not isinstance(entry, dict)
                else list(entry.get("lore_chunk_tags", []) or [])
            )
            if not entry_tags:
                continue

            # Check for any overlap between citation tags and entry tags
            entry_tag_set = {t.lower().strip() for t in entry_tags if t}
            if citation_tags & entry_tag_set:
                newly_unlocked.append(entry_id)
                logger.info(
                    "Codex unlocked: %s (matched tags: %s)",
                    entry_id,
                    citation_tags & entry_tag_set,
                )

        if newly_unlocked:
            # Persist to world_state
            unlocked_list = list(already_unlocked) + newly_unlocked
            world_state["unlocked_codex_ids"] = unlocked_list

        return newly_unlocked

    def _extract_citation_tags(self, lore_citations: list[Any]) -> set[str]:
        """Extract all tag strings from a list of lore citation dicts."""
        tags: set[str] = set()
        for citation in lore_citations:
            if isinstance(citation, dict):
                # Various tag fields that might be present
                for field in ("tags", "chunk_tags", "doc_tags", "lore_chunk_tags", "era", "time_period"):
                    val = citation.get(field)
                    if isinstance(val, list):
                        tags.update(t.lower().strip() for t in val if t)
                    elif isinstance(val, str) and val:
                        tags.add(val.lower().strip())
                # NPC tags from related_npcs
                npcs = citation.get("related_npcs") or []
                if isinstance(npcs, list):
                    tags.update(n.lower().strip() for n in npcs if isinstance(n, str))
                # Book title / source as a tag (for title-matched codex entries)
                source = citation.get("book_title") or citation.get("source") or ""
                if source:
                    tags.add(source.lower().strip())
        return tags


def get_unlocked_codex_entries(
    world_state: dict[str, Any],
    era_pack: Any | None = None,
) -> list[dict[str, Any]]:
    """Return the full codex entries for all unlocked IDs.

    Args:
        world_state: The current world_state_json dict.
        era_pack: EraPack instance for the current era.

    Returns:
        List of codex entry dicts (model_dump format).
    """
    unlocked_ids: set[str] = set(world_state.get("unlocked_codex_ids") or [])
    if not unlocked_ids or era_pack is None:
        return []

    codex_entries = getattr(era_pack, "codex", []) or []
    result: list[dict[str, Any]] = []
    for entry in codex_entries:
        if isinstance(entry, dict):
            entry_id = entry.get("id")
            if entry_id in unlocked_ids:
                result.append(entry)
        else:
            entry_id = getattr(entry, "id", None)
            if entry_id in unlocked_ids:
                try:
                    result.append(entry.model_dump(mode="json"))
                except Exception:
                    result.append({"id": entry_id, "title": getattr(entry, "title", ""), "body": getattr(entry, "body", "")})
    return result
