"""CloudMetadataEnricher: adds narrative_role, spoiler_tier, canon_weight to LanceDB chunks.

Phase 3 — Cloud enrichment pipeline.  Reads chunks from LanceDB, calls a cloud
LLM to classify each chunk's narrative metadata, then updates the rows in-place.

Designed to run *after* standard ingestion (`--cloud-enrich` flag on ingest_lore.py)
or standalone as a post-processing step.

Usage::

    from ingestion.cloud_enricher import CloudMetadataEnricher
    enricher = CloudMetadataEnricher(db_path="./data/lancedb")
    count = enricher.enrich_chunks(filter_context={"setting_id": "star_wars_legends"})
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# How many chunks to process per LLM batch
_BATCH_SIZE = int(os.environ.get("CLOUD_ENRICHER_BATCH_SIZE", "20"))

# Narrative roles assigned by the enricher
NARRATIVE_ROLES = [
    "lore_exposition",    # world-building, setting description
    "character_moment",   # character dialogue, development, backstory
    "action_beat",        # combat, chase, action sequences
    "mystery_hook",       # questions raised, secrets hinted at
    "faction_politics",   # political maneuvering, alliances, conflict
    "historical_record",  # canonical events, timeline entries
    "worldbuilding",      # geography, culture, technology descriptions
    "quest_hook",         # adventure seeds, mission briefings
    "other",              # catch-all
]

# Spoiler tiers: 0=always safe, 1=minor, 2=moderate, 3=major spoiler
SPOILER_TIERS = [0, 1, 2, 3]


def _classify_chunk(text: str, llm: Any) -> dict[str, Any]:
    """Call LLM to classify a single chunk's narrative metadata.

    Returns a dict with: narrative_role, spoiler_tier, canon_weight
    Falls back to safe defaults on error.
    """
    prompt = (
        "Classify this lore chunk for a narrative RPG database. "
        "Return ONLY valid JSON with exactly these fields:\n"
        '{"narrative_role": "<one of: ' + "|".join(NARRATIVE_ROLES) + '>",'
        ' "spoiler_tier": <0-3, where 0=always_shown 3=major_spoiler>,'
        ' "canon_weight": <0.0-1.0, confidence this is canonical lore>}\n\n'
        f"Chunk:\n{text[:600]}"
    )
    try:
        response = llm.call(system="You are a lore classifier. Output only valid JSON.", user=prompt)
        if isinstance(response, str):
            data = json.loads(response)
        elif hasattr(response, "content"):
            data = json.loads(response.content)
        else:
            data = json.loads(str(response))

        narrative_role = str(data.get("narrative_role", "other"))
        if narrative_role not in NARRATIVE_ROLES:
            narrative_role = "other"
        spoiler_tier = int(data.get("spoiler_tier", 0))
        if spoiler_tier not in SPOILER_TIERS:
            spoiler_tier = 0
        canon_weight = float(data.get("canon_weight", 1.0))
        canon_weight = max(0.0, min(1.0, canon_weight))

        return {
            "narrative_role": narrative_role,
            "spoiler_tier": spoiler_tier,
            "canon_weight": canon_weight,
        }
    except Exception as e:
        logger.debug("Chunk classification failed (using defaults): %s", e)
        return {"narrative_role": "other", "spoiler_tier": 0, "canon_weight": 1.0}


class CloudMetadataEnricher:
    """Enriches LanceDB lore chunks with narrative metadata via cloud LLM.

    Adds three fields to each chunk:
    - ``narrative_role``: Categorical label for the chunk's narrative function.
    - ``spoiler_tier``: Integer 0-3 indicating spoiler sensitivity.
    - ``canon_weight``: Float 0-1 indicating canonical reliability.

    These fields are used by:
    - ``CodexDiscovery`` (Phase 4.2) to filter codex unlocks by spoiler tier.
    - The Director (Phase 4.1) to prioritize high-canon chunks in hub mode.
    - RAG retrieval to down-rank non-canonical chunks.
    """

    def __init__(self, db_path: str = "./data/lancedb") -> None:
        self._db_path = str(db_path)
        self._llm: Any | None = None

    def _get_llm(self) -> Any:
        """Lazy-load the cloud LLM via AgentLLM."""
        if self._llm is None:
            try:
                from backend.app.core.agents.base import AgentLLM
                self._llm = AgentLLM("arc_screenplay")  # reuse cloud-capable role
            except Exception as e:
                logger.warning("CloudMetadataEnricher: LLM unavailable (%s), using heuristics", e)
                self._llm = None
        return self._llm

    def _heuristic_classify(self, text: str, doc_type: str = "") -> dict[str, Any]:
        """Deterministic fallback classification based on text features."""
        text_lower = text.lower()
        narrative_role = "lore_exposition"
        if any(w in text_lower for w in ["said", "replied", "shouted", "whispered", "\"", "'"]):
            narrative_role = "character_moment"
        elif any(w in text_lower for w in ["battle", "fight", "attack", "weapon", "combat"]):
            narrative_role = "action_beat"
        elif any(w in text_lower for w in ["faction", "senate", "council", "alliance", "empire"]):
            narrative_role = "faction_politics"
        elif any(w in text_lower for w in ["year", "bby", "aby", "event", "war", "treaty"]):
            narrative_role = "historical_record"
        elif any(w in text_lower for w in ["planet", "system", "sector", "region", "galaxy"]):
            narrative_role = "worldbuilding"
        elif any(w in text_lower for w in ["mission", "job", "quest", "task", "objective"]):
            narrative_role = "quest_hook"
        elif "?" in text and any(w in text_lower for w in ["secret", "mystery", "unknown", "hidden"]):
            narrative_role = "mystery_hook"

        # Spoiler tier: higher for character deaths and major reveals
        spoiler_tier = 0
        if any(w in text_lower for w in ["death", "destroyed", "betrayed", "revealed"]):
            spoiler_tier = 1
        if any(w in text_lower for w in ["order 66", "darth", "palpatine", "anakin skywalker"]):
            spoiler_tier = 2

        # Canon weight: rules/reference books are more canonical
        canon_weight = 1.0
        if doc_type in ("novel", "fanfiction"):
            canon_weight = 0.8
        elif doc_type == "reference":
            canon_weight = 1.0

        return {
            "narrative_role": narrative_role,
            "spoiler_tier": spoiler_tier,
            "canon_weight": canon_weight,
        }

    def enrich_chunks(
        self,
        filter_context: dict[str, str] | None = None,
        use_llm: bool | None = None,
    ) -> int:
        """Enrich LanceDB chunks with narrative_role, spoiler_tier, canon_weight.

        Args:
            filter_context: Dict of field→value filters to scope enrichment
                            (e.g. {"setting_id": "star_wars_legends", "period_id": "rebellion"}).
            use_llm: If True, use cloud LLM. If False, use heuristics. If None,
                     auto-detect based on LLM availability.

        Returns:
            Number of chunks enriched.
        """
        try:
            import lancedb
        except ImportError:
            logger.error("lancedb not installed; cannot run CloudMetadataEnricher")
            return 0

        try:
            db = lancedb.connect(self._db_path)
            table = db.open_table("lore_chunks")
        except Exception as e:
            logger.error("CloudMetadataEnricher: cannot open LanceDB at %s: %s", self._db_path, e)
            return 0

        # Build filter query
        try:
            df = table.to_pandas()
        except Exception as e:
            logger.error("CloudMetadataEnricher: cannot read table: %s", e)
            return 0

        if filter_context:
            for field, value in filter_context.items():
                if field in df.columns and value:
                    df = df[df[field] == value]

        if df.empty:
            logger.info("CloudMetadataEnricher: no chunks match filter %s", filter_context)
            return 0

        logger.info("CloudMetadataEnricher: enriching %d chunks", len(df))

        # Determine enrichment method
        llm = None
        if use_llm is True or (use_llm is None and os.environ.get("ENABLE_CLOUD_BLUEPRINT", "false").lower() in ("true", "1")):
            llm = self._get_llm()

        enriched_count = 0
        updates: list[dict[str, Any]] = []

        for _, row in df.iterrows():
            chunk_id = row.get("id", "")
            text = str(row.get("text", ""))
            doc_type = str(row.get("doc_type", ""))

            if llm is not None:
                metadata = _classify_chunk(text, llm)
            else:
                metadata = self._heuristic_classify(text, doc_type)

            updates.append({
                "id": chunk_id,
                **metadata,
            })
            enriched_count += 1

            if len(updates) >= _BATCH_SIZE:
                self._apply_updates(table, updates)
                updates = []
                logger.debug("CloudMetadataEnricher: batch of %d applied", _BATCH_SIZE)

        if updates:
            self._apply_updates(table, updates)

        logger.info("CloudMetadataEnricher: %d chunks enriched", enriched_count)
        return enriched_count

    def _apply_updates(self, table: Any, updates: list[dict[str, Any]]) -> None:
        """Apply narrative metadata updates to LanceDB chunks.

        Uses merge_insert (upsert) if available; falls back to individual updates.
        The three enrichment fields are stored as metadata columns. If they don't
        exist in the schema yet, the update is silently skipped (schema-safe).
        """
        if not updates:
            return
        try:
            import pandas as pd
            update_df = pd.DataFrame(updates)
            schema_cols = {f.name for f in table.schema}
            enrichment_fields = ["narrative_role", "spoiler_tier", "canon_weight"]
            missing_fields = [f for f in enrichment_fields if f not in schema_cols]
            if missing_fields:
                # Fields not yet in schema — log and skip (requires --rebuild to add columns)
                logger.debug(
                    "CloudMetadataEnricher: enrichment fields %s not in LanceDB schema. "
                    "Run ingestion with --rebuild to add columns.",
                    missing_fields,
                )
                return
            # Update each row by ID
            for _, row in update_df.iterrows():
                chunk_id = row["id"]
                if not chunk_id:
                    continue
                for field in enrichment_fields:
                    if field in row:
                        table.update(
                            where=f"id = '{chunk_id}'",
                            values={field: row[field]},
                        )
        except Exception as e:
            logger.warning("CloudMetadataEnricher: update batch failed: %s", e)


def main() -> int:
    """CLI entry point for standalone cloud enrichment."""
    import argparse
    ap = argparse.ArgumentParser(
        description="Enrich LanceDB lore chunks with narrative_role, spoiler_tier, canon_weight."
    )
    ap.add_argument("--db", type=str, default="./data/lancedb", help="LanceDB path")
    ap.add_argument("--setting-id", type=str, default="", help="Filter by setting_id")
    ap.add_argument("--period-id", type=str, default="", help="Filter by period_id")
    ap.add_argument("--use-llm", action="store_true", default=False, help="Use cloud LLM (requires ENABLE_CLOUD_BLUEPRINT=true)")
    ap.add_argument("--heuristics", action="store_true", default=False, help="Force heuristic classification (no LLM)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    enricher = CloudMetadataEnricher(db_path=args.db)
    filter_ctx: dict[str, str] = {}
    if args.setting_id:
        filter_ctx["setting_id"] = args.setting_id
    if args.period_id:
        filter_ctx["period_id"] = args.period_id

    use_llm: bool | None = None
    if args.use_llm:
        use_llm = True
    elif args.heuristics:
        use_llm = False

    count = enricher.enrich_chunks(filter_context=filter_ctx or None, use_llm=use_llm)
    print(f"Enriched {count} chunks.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
