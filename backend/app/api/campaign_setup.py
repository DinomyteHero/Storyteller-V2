"""Campaign setup helpers: NPC creation, location pools, arc seeding, content resolution."""
from __future__ import annotations

import json
import logging
import os
import random
import re
import uuid
from typing import Any

from fastapi import HTTPException

from backend.app.content.repository import CONTENT_REPOSITORY
from backend.app.core.text_utils import normalize_identifier

logger = logging.getLogger(__name__)

# Default location pool (starting_location is always included)
DEFAULT_LOCATIONS = [
    "loc-cantina",
    "loc-marketplace",
    "loc-docking-bay",
    "loc-lower-streets",
    "loc-hangar",
    "loc-spaceport",
]

# NPC cast: 1 Villain, 1 Rival, 2 Merchants, 2 Informants, 6 Generic
NPC_CAST = [
    {"name": "Draven Koss", "role": "Villain", "secret_agenda": "Seeks to dominate the sector through ruthless control."},
    {"name": "Vekk Tano", "role": "Rival", "secret_agenda": "Wants to beat you to the prize — ambitious and relentless."},
    {"name": "Nura Besh", "role": "Merchant", "secret_agenda": "Deals in black market goods through Twi'lek trade networks."},
    {"name": "Gorrak Mun", "role": "Merchant", "secret_agenda": "Holds a grudge against the syndicate — Sullustan never forgets."},
    {"name": "Whisper", "role": "Informant", "secret_agenda": "Bothan spymaster — sells secrets to the highest bidder."},
    {"name": "Zeel Kaat", "role": "Informant", "secret_agenda": "Devaronian who works for multiple factions."},
    {"name": "TK-4471", "role": "Guard", "secret_agenda": "Bribable but loyal to the post."},
    {"name": "Hera Solus", "role": "Local", "secret_agenda": "Mirialan who knows more than she lets on."},
    {"name": "Renn Voss", "role": "Pilot", "secret_agenda": "Smuggles on the side — fast hands, faster ship."},
    {"name": "Grumthar", "role": "Barkeep", "secret_agenda": "Ithorian barkeep — eavesdrops for the right price."},
    {"name": "Pix", "role": "Mechanic", "secret_agenda": "Jawa tinkerer — sells intel on ship traffic."},
    {"name": "Sarik Vey", "role": "Stranger", "secret_agenda": "Chiss operative — just passing through, or so they claim."},
]


def _location_pool(starting_location: str) -> list[str]:
    """Return a small set of locations including starting_location."""
    pool = list(dict.fromkeys([starting_location] + DEFAULT_LOCATIONS))
    return pool

def _create_npc_cast(conn, campaign_id: str, starting_location: str) -> None:
    """Insert 12 NPCs: 1 Villain, 1 Rival, 2 Merchants, 2 Informants, 6 Generic. Do not leak secret_agenda."""
    pool = _location_pool(starting_location)
    for i, npc_def in enumerate(NPC_CAST):
        nid = str(uuid.uuid4())
        location_id = random.choice(pool)
        role = npc_def["role"]
        if role == "Villain":
            rel = random.randint(0, 20)
        elif role == "Rival":
            rel = random.randint(10, 30)
        else:
            rel = random.randint(0, 50)
        conn.execute(
            """INSERT INTO characters (id, campaign_id, name, role, location_id, stats_json, hp_current, relationship_score, secret_agenda, credits, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, datetime('now'), datetime('now'))""",
            (
                nid,
                campaign_id,
                npc_def["name"],
                role,
                location_id,
                "{}",
                10,
                rel,
                npc_def["secret_agenda"],
            ),
        )

def _create_npc_cast_from_skeleton(conn, campaign_id: str, skeleton: dict, starting_location: str) -> None:
    """Insert NPCs from skeleton.npc_cast; locations from skeleton.locations or DEFAULT_LOCATIONS."""
    pool = list(dict.fromkeys([starting_location] + (skeleton.get("locations") or DEFAULT_LOCATIONS)))
    npc_cast = skeleton.get("npc_cast") or NPC_CAST
    for npc_def in npc_cast[:12]:
        nid = str(uuid.uuid4())
        location_id = random.choice(pool)
        role = npc_def.get("role", "NPC")
        if role == "Villain":
            rel = random.randint(0, 20)
        elif role == "Rival":
            rel = random.randint(10, 30)
        else:
            rel = random.randint(0, 50)
        conn.execute(
            """INSERT INTO characters (id, campaign_id, name, role, location_id, stats_json, hp_current, relationship_score, secret_agenda, credits, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, datetime('now'), datetime('now'))""",
            (
                nid,
                campaign_id,
                npc_def.get("name", "NPC"),
                role,
                location_id,
                "{}",
                10,
                rel,
                npc_def.get("secret_agenda"),
            ),
        )

def _catalog_items() -> list[dict]:
    return CONTENT_REPOSITORY.list_catalog()


def _resolve_requested_period(*, setting_id: str | None, period_id: str | None, time_period: str | None) -> tuple[str, str, str]:
    """Resolve request into canonical (setting_id, period_id, legacy_era_id)."""
    items = _catalog_items()
    if setting_id and period_id:
        s = normalize_identifier(setting_id)
        p = normalize_identifier(period_id)
        for item in items:
            if item["setting_id"] == s and item["period_id"] == p:
                return s, p, item["legacy_era_id"]
        available = ", ".join(sorted({f"{i['setting_id']}/{i['period_id']}" for i in items})) or "none"
        raise HTTPException(status_code=400, detail=f"Unknown period '{s}/{p}'. Available: {available}")

    if time_period:
        era = normalize_identifier(time_period)
        for item in items:
            if item["period_id"] == era or item["legacy_era_id"].strip().lower() == era:
                return item["setting_id"], item["period_id"], item["legacy_era_id"]
        # Legacy compatibility: unknown time_period falls back to default instead of hard-failing.
        # Canonical callers should use setting_id/period_id for strict validation.
        if items:
            fallback = items[0]
            return fallback["setting_id"], fallback["period_id"], fallback["legacy_era_id"]

    # Default resolver
    default_setting = normalize_identifier(os.environ.get("DEFAULT_SETTING_ID") or "star_wars_legends")
    default_period = normalize_identifier(os.environ.get("DEFAULT_PERIOD_ID") or "rebellion")
    for item in items:
        if item["setting_id"] == default_setting and item["period_id"] == default_period:
            return default_setting, default_period, item["legacy_era_id"]
    if items:
        first = items[0]
        return first["setting_id"], first["period_id"], first["legacy_era_id"]
    raise HTTPException(status_code=500, detail="No content packs discovered")


def apply_quick_start_defaults(body: Any) -> Any:
    """Normalize SetupAutoRequest values for quick-start setup.

    This only fills missing values and does not override explicit user input.
    """
    if not bool(getattr(body, "quick_start", False)):
        return body

    if not getattr(body, "setting_id", None) and not getattr(body, "period_id", None) and not getattr(body, "time_period", None):
        body.setting_id = "star_wars_legends"
        body.period_id = "rebellion"
        body.time_period = "REBELLION"

    player_concept = str(getattr(body, "player_concept", "") or "").strip()
    if not player_concept:
        body.player_concept = "A capable drifter trying to survive and do some good."

    if not getattr(body, "player_gender", None):
        body.player_gender = random.choice(["male", "female"])

    themes = list(getattr(body, "themes", None) or [])
    if not themes:
        body.themes = ["duty", "survival", "trust"]

    if not getattr(body, "campaign_mode", None):
        body.campaign_mode = "historical"
    if not getattr(body, "campaign_scale", None):
        body.campaign_scale = "medium"
    if not getattr(body, "difficulty", None):
        body.difficulty = "normal"

    if not getattr(body, "starting_location", None):
        body.randomize_starting_location = True

    return body

def _is_safe_start_location(tags: list[str] | None, threat_level: str | None) -> bool:
    tags_lower = {str(t).strip().lower() for t in (tags or []) if str(t).strip()}
    if "prison" in tags_lower:
        return False
    if "dangerous" in tags_lower:
        return False
    if (threat_level or "").strip().lower() in {"high", "extreme"}:
        return False
    return True


def _pick_start_location_from_pack(pack, player_concept: str, *, safe_only: bool = True) -> str:
    """Pick a reasonable starting location from an EraPack (deterministic, concept-biased)."""
    locs = list(pack.locations or [])
    if safe_only:
        safe = [loc for loc in locs if _is_safe_start_location(loc.tags, loc.threat_level)]
        if safe:
            locs = safe
    if not locs:
        return "loc-cantina"

    concept_tokens = set(re.findall(r"[a-z0-9]+", (player_concept or "").lower()))
    if not concept_tokens:
        return locs[0].id

    def _score(loc) -> int:
        tokens = set(re.findall(r"[a-z0-9]+", (loc.name or "").lower()))
        tokens |= set(re.findall(r"[a-z0-9]+", (loc.description or "").lower()))
        tokens |= {str(t).strip().lower() for t in (loc.tags or []) if str(t).strip()}
        if loc.planet:
            tokens.add(str(loc.planet).strip().lower())
        if loc.region:
            tokens.add(str(loc.region).strip().lower())
        return len(concept_tokens & tokens)

    best = max(locs, key=_score)
    return best.id


def _deterministic_arc_seed(
    *,
    time_period: str | None,
    genre: str | None,
    themes: list[str],
    player_concept: str,
    starting_location: str,
) -> dict:
    """Build a deterministic arc scaffold used when LLM seeding is unavailable.

    This seed is setup-time only. Runtime arc progression remains deterministic in
    arc_planner_node using ledger + turn progression.
    """
    cleaned_themes = [str(t).strip() for t in (themes or []) if str(t).strip()][:3]
    loc = (starting_location or "here").replace("loc-", "").replace("-", " ").replace("_", " ").strip() or "here"
    genre_text = (genre or "adventure").strip() or "adventure"
    period_text = (time_period or "unknown era").strip() or "unknown era"
    concept = (player_concept or "A capable drifter").strip() or "A capable drifter"

    if not cleaned_themes:
        cleaned_themes = ["duty", "trust", "survival"]

    opening_threads = [
        f"Rumors in {loc} point to a deeper {genre_text} conspiracy.",
        f"A personal stake emerges from the hero's past: {concept[:100]}",
        f"Power blocs in {period_text} force a choice between safety and principle.",
    ]
    climax_question = "Will the hero sacrifice leverage to protect people they now trust?"
    return {
        "source": "deterministic_fallback",
        "active_themes": cleaned_themes,
        "opening_threads": opening_threads,
        "climax_question": climax_question,
        "arc_intent": "three-act moral pressure curve",
    }



def _generate_arc_seed(
    *,
    time_period: str | None,
    genre: str | None,
    themes: list[str],
    player_concept: str,
    starting_location: str,
) -> dict:
    """Generate setup-time arc seed via LLM, with deterministic fallback.

    Runtime arc behavior remains deterministic. This only provides initial
    campaign-specific scaffolding for ArcPlanner/Director context.
    """
    fallback = _deterministic_arc_seed(
        time_period=time_period,
        genre=genre,
        themes=themes,
        player_concept=player_concept,
        starting_location=starting_location,
    )

    try:
        from backend.app.core.agents.base import AgentLLM  # noqa: E402

        llm = AgentLLM("architect")
        system_prompt = (
            "You create compact campaign arc scaffolds. Output valid JSON only. "
            "Do not include markdown."
        )
        user_prompt = (
            "Create a setup-time arc scaffold for a narrative RPG campaign.\n"
            "Return EXACTLY one JSON object with keys:\n"
            "active_themes: string[] (1-3 items),\n"
            "opening_threads: string[] (2-3 items),\n"
            "climax_question: string,\n"
            "arc_intent: string.\n\n"
            f"era={time_period or 'unknown'}\n"
            f"genre={genre or 'unspecified'}\n"
            f"themes={themes or []}\n"
            f"starting_location={starting_location or 'here'}\n"
            f"player_concept={player_concept or ''}\n"
        )
        raw = llm.complete(system_prompt, user_prompt, json_mode=True)
        parsed = json.loads(str(raw)) if raw else {}
        if not isinstance(parsed, dict):
            return fallback

        active_themes = [str(t).strip() for t in (parsed.get("active_themes") or []) if str(t).strip()][:3]
        opening_threads = [str(t).strip() for t in (parsed.get("opening_threads") or []) if str(t).strip()][:3]
        climax_question = str(parsed.get("climax_question") or "").strip()
        arc_intent = str(parsed.get("arc_intent") or "").strip()

        if not active_themes:
            active_themes = fallback["active_themes"]
        if len(opening_threads) < 2:
            opening_threads = fallback["opening_threads"]
        if not climax_question:
            climax_question = fallback["climax_question"]
        if not arc_intent:
            arc_intent = fallback["arc_intent"]

        return {
            "source": "llm_setup_seed",
            "active_themes": active_themes,
            "opening_threads": opening_threads,
            "climax_question": climax_question,
            "arc_intent": arc_intent,
        }
    except Exception:
        logger.exception("setup_auto arc seed generation failed; using deterministic fallback")
        return fallback


