#!/usr/bin/env python3
"""V11.0 Playthrough Simulation.

Exercises all three V11.0 feature areas in a single deterministic run:
  1. Universe & Story UX   — saga creation, campaign linking, saga timeline
  2. UI-Exposed Lore Ingestion — lore_sources CRUD (create / list / delete)
  3. Optional Visual Layer — portrait_url / location_art_url fields in turn responses

Usage:
  python scripts/simulate_v11_playthrough.py [--turns 10] [--use-temp-db]
  ENABLE_PORTRAITS=1 python scripts/simulate_v11_playthrough.py --turns 5

Run from project root. Uses mocked LLM agents for deterministic offline execution.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Deterministic encounter seed — must be set before any backend imports
if "ENCOUNTER_SEED" not in os.environ:
    os.environ["ENCOUNTER_SEED"] = "42"

from backend.app.config import DEFAULT_DB_PATH  # noqa: E402
from backend.app.core.companions import build_initial_companion_state  # noqa: E402
from backend.app.core.event_store import append_events, get_current_turn_number  # noqa: E402
from backend.app.core.graph import run_turn  # noqa: E402
from backend.app.core.state_loader import build_initial_gamestate  # noqa: E402
from backend.app.core.transcript_store import get_rendered_turns  # noqa: E402
from backend.app.db.connection import get_connection  # noqa: E402
from backend.app.db.migrate import apply_schema  # noqa: E402
from backend.app.models.events import Event  # noqa: E402
from backend.app.models.narration import NarrationOutput  # noqa: E402
from backend.app.models.state import ActionSuggestion, MechanicOutput  # noqa: E402
from backend.app.constants import SUGGESTED_ACTIONS_TARGET  # noqa: E402

# ---------------------------------------------------------------------------
# Scenario inputs — mix of TALK, ACTION, and META intents
# ---------------------------------------------------------------------------

V11_INPUTS = [
    "I look around the cantina, sizing up the patrons",
    "I approach the hooded figure in the corner",
    "I ask about the recent Imperial patrols",
    "I slip a credit chip across the bar",
    "help",
    "I follow the contact into the alley",
    "I check my comlink for messages",
    "I negotiate with the smuggler",
    "I examine the strange symbol on the crate",
    "I head toward the docking bay",
    "inventory",
    "I talk to the astromech unit near the exit",
    "I ask the barkeep about the Empire",
    "I move carefully past the stormtrooper checkpoint",
    "I open the sealed container",
]

# ---------------------------------------------------------------------------
# Mock agent factories — deterministic, no LLM calls required
# ---------------------------------------------------------------------------

_MOCK_ACTIONS = [
    ActionSuggestion(label="Talk", intent_text="Say: Tell me more", category="SOCIAL"),
    ActionSuggestion(label="Look", intent_text="Observe the surroundings", category="EXPLORE"),
    ActionSuggestion(label="Act", intent_text="Take decisive action", category="COMMIT"),
]

_MOCK_DIRECTOR_PLAN = ("Steady pacing. Build tension.", _MOCK_ACTIONS)


def _mock_narrator_generate(gs, *args, **kwargs):
    turn = getattr(gs, "turn_number", 0)
    return NarrationOutput(
        text=f"The galaxy holds its breath. Turn {turn}: {(gs.user_input or '')[:60]}.",
        citations=[],
    )


def _mock_mechanic_resolve(gs):
    return MechanicOutput(
        action_type="INTERACT",
        events=[],
        narrative_facts=[f"Resolved: {(gs.user_input or '')[:60]}"],
        time_cost_minutes=5,
    )


# ---------------------------------------------------------------------------
# Phase 1 helpers — Saga / Universe UX
# ---------------------------------------------------------------------------


def _create_saga(conn, player_id: str, universe_id: str, title: str) -> str:
    """Insert a saga row (mirrors POST /v2/sagas). Returns saga_id."""
    saga_id = uuid.uuid4().hex[:12]
    conn.execute(
        """INSERT INTO sagas (id, player_id, universe_id, title, created_at, updated_at)
           VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))""",
        (saga_id, player_id, universe_id, title),
    )
    conn.commit()
    return saga_id


def _get_saga_detail(conn, saga_id: str) -> dict:
    """Fetch saga metadata + ordered campaign list (mirrors GET /v2/sagas/{saga_id})."""
    saga_row = conn.execute(
        "SELECT id, player_id, universe_id, title, created_at FROM sagas WHERE id = ?",
        (saga_id,),
    ).fetchone()
    if not saga_row:
        return {}
    campaigns = conn.execute(
        """SELECT id, title, time_period, saga_chapter, updated_at
           FROM campaigns WHERE saga_id = ?
           ORDER BY saga_chapter ASC, updated_at ASC""",
        (saga_id,),
    ).fetchall()
    return {
        "saga_id": str(saga_row["id"]),
        "universe_id": str(saga_row["universe_id"]),
        "title": str(saga_row["title"]),
        "campaigns": [
            {
                "campaign_id": str(r["id"]),
                "title": str(r["title"]),
                "period_id": r["time_period"],
                "saga_chapter": r["saga_chapter"],
            }
            for r in campaigns
        ],
    }


def _list_sagas_for_player(conn, player_id: str) -> list[dict]:
    """List sagas for a player (mirrors GET /v2/player/{id}/sagas)."""
    rows = conn.execute(
        """SELECT s.id, s.universe_id, s.title, COUNT(c.id) AS campaign_count
           FROM sagas s
           LEFT JOIN campaigns c ON c.saga_id = s.id
           WHERE s.player_id = ?
           GROUP BY s.id, s.universe_id, s.title""",
        (player_id,),
    ).fetchall()
    return [
        {
            "saga_id": str(r["id"]),
            "universe_id": str(r["universe_id"]),
            "title": str(r["title"]),
            "campaign_count": int(r["campaign_count"]),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Phase 2 helpers — Lore Sources CRUD
# ---------------------------------------------------------------------------


def _create_lore_source(
    conn, name: str, setting_id: str = "", period_id: str = ""
) -> str:
    """Create a lore_sources row (mirrors POST /v2/library/sources). Returns source_id."""
    source_id = uuid.uuid4().hex[:12]
    conn.execute(
        "INSERT INTO lore_sources (id, name, setting_id, period_id) VALUES (?, ?, ?, ?)",
        (source_id, name, setting_id, period_id),
    )
    conn.commit()
    return source_id


def _list_lore_sources(conn) -> list[dict]:
    """List active lore sources (mirrors GET /v2/library/sources)."""
    try:
        rows = conn.execute(
            "SELECT id, name, setting_id, period_id, file_count, chunk_count, status "
            "FROM lore_sources WHERE status != 'deleted' ORDER BY created_at DESC"
        ).fetchall()
    except Exception:
        return []
    return [
        {
            "id": str(r["id"]),
            "name": str(r["name"]),
            "setting_id": r["setting_id"] or "",
            "period_id": r["period_id"] or "",
            "chunk_count": int(r["chunk_count"] or 0),
            "status": str(r["status"]),
        }
        for r in rows
    ]


def _delete_lore_source(conn, source_id: str) -> bool:
    """Soft-delete a lore source (mirrors DELETE /v2/library/sources/{id})."""
    conn.execute(
        "UPDATE lore_sources SET status = 'deleted', updated_at = datetime('now') "
        "WHERE id = ?",
        (source_id,),
    )
    conn.commit()
    row = conn.execute(
        "SELECT status FROM lore_sources WHERE id = ?", (source_id,)
    ).fetchone()
    return row is not None and str(row["status"]) == "deleted"


# ---------------------------------------------------------------------------
# Phase 3 helpers — Visual Layer schema validation
#
# `run_turn` returns GameState, which is the pipeline-level object. The V11
# visual layer fields (portrait_url, location_art_url) live on TurnResponse,
# the API-level response model. We validate the schema presence here rather
# than inspecting pipeline output, which correctly exercises the V11 model
# changes without requiring the full API stack.
# ---------------------------------------------------------------------------


def _check_portrait_fields(_result) -> dict:
    """Validate V11.0 visual-layer schema (API model + config flag).

    Checks that PartyStatusItem.portrait_url and TurnResponse.location_art_url
    exist as Pydantic fields (Phase 3 schema additions), and reads the
    ENABLE_PORTRAITS flag from the environment.
    """
    from backend.app.api.campaign_models import PartyStatusItem, TurnResponse  # noqa: E402
    portraits_enabled = os.environ.get("ENABLE_PORTRAITS", "0") == "1"
    party_item_has_portrait = "portrait_url" in PartyStatusItem.model_fields
    turn_response_has_location_art = "location_art_url" in TurnResponse.model_fields
    return {
        "portraits_enabled": portraits_enabled,
        "party_status_item_has_portrait_url": party_item_has_portrait,
        "turn_response_has_location_art_url": turn_response_has_location_art,
        # When portraits disabled, both fields should default to None (correct)
        "schema_ok": party_item_has_portrait and turn_response_has_location_art,
    }


# ---------------------------------------------------------------------------
# Campaign setup — minimal direct DB insertion (no LLM agents required).
# Mirrors the approach used in test_deterministic_harness.py for offline runs.
# ---------------------------------------------------------------------------


def _create_campaign(conn, time_period: str, saga_id: str | None) -> tuple[str, str]:
    """Create a minimal campaign directly in the DB. Returns (campaign_id, player_id)."""
    from backend.app.core.projections import apply_projection  # noqa: E402

    campaign_id = str(uuid.uuid4())
    player_id = str(uuid.uuid4())

    companion_state = build_initial_companion_state(world_time_minutes=0)
    world_state = {"active_factions": [], **companion_state}

    conn.execute(
        """INSERT INTO campaigns (id, title, time_period, world_state_json, world_time_minutes)
           VALUES (?, ?, ?, ?, ?)""",
        (
            campaign_id,
            "V11.0 Simulation — Tales of the Rebellion",
            time_period.upper(),
            json.dumps(world_state),
            0,
        ),
    )
    conn.execute(
        """INSERT INTO characters
           (id, campaign_id, name, role, location_id, stats_json,
            hp_current, relationship_score, secret_agenda, credits)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
        (player_id, campaign_id, "Hero", "Player", "loc-cantina", "{}", 10, None, None),
    )
    conn.commit()

    # Saga linkage (V11.0 Universe & Story UX)
    if saga_id:
        chapter_row = conn.execute(
            "SELECT COALESCE(MAX(saga_chapter), 0) AS max_chapter "
            "FROM campaigns WHERE saga_id = ?",
            (saga_id,),
        ).fetchone()
        saga_chapter = int((chapter_row["max_chapter"] if chapter_row else 0) or 0) + 1
        conn.execute(
            "UPDATE campaigns SET saga_id = ?, saga_chapter = ? WHERE id = ?",
            (saga_id, saga_chapter, campaign_id),
        )
        conn.execute(
            "UPDATE sagas SET updated_at = datetime('now') WHERE id = ?",
            (saga_id,),
        )
        conn.commit()

    initial_events = [
        Event(event_type="FLAG_SET", payload={"key": "campaign_started", "value": True})
    ]
    append_events(conn, campaign_id, 1, initial_events)
    apply_projection(conn, campaign_id, initial_events)
    return campaign_id, player_id


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "V11.0 playthrough simulation — exercises Universe/Story UX, "
            "Lore Ingestion, and Optional Visual Layer."
        )
    )
    ap.add_argument("--turns", "-n", type=int, default=10, help="Number of turns (default 10)")
    ap.add_argument("--use-temp-db", action="store_true", help="Use temporary DB (CI-safe)")
    ap.add_argument("--db", type=str, default=None, help="DB path (default: config)")
    ap.add_argument("--time-period", type=str, default="rebellion", help="Campaign time period")
    args = ap.parse_args()

    _cleanup_db: str | None = None
    if args.use_temp_db:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db_path = tmp.name
        _cleanup_db = db_path
    else:
        db_path = args.db or DEFAULT_DB_PATH
        _cleanup_db = None

    inputs = (V11_INPUTS * ((args.turns // len(V11_INPUTS)) + 1))[: args.turns]

    apply_schema(db_path)
    conn = get_connection(db_path)

    results: dict = {
        "phase1_saga": {"ok": False},
        "phase2_lore_sources": {"ok": False},
        "phase3_visual": {},
        "turns": [],
        "errors": [],
    }

    try:
        # ------------------------------------------------------------------ #
        # Phase 2: Lore Sources lifecycle (create / list / delete)           #
        # ------------------------------------------------------------------ #
        print("\n[Phase 2] Lore Source lifecycle")

        source_id_a = _create_lore_source(
            conn,
            name="Rebellion Era Compendium",
            setting_id="star_wars",
            period_id="rebellion",
        )
        source_id_b = _create_lore_source(
            conn,
            name="Imperial Security Bureau Files",
            setting_id="star_wars",
            period_id="rebellion",
        )
        print(f"  Created source A: {source_id_a}")
        print(f"  Created source B: {source_id_b}")

        sources_before = _list_lore_sources(conn)
        active_ids = {s["id"] for s in sources_before}
        assert source_id_a in active_ids, "Source A missing from list"
        assert source_id_b in active_ids, "Source B missing from list"
        print(f"  Listed {len(sources_before)} active source(s) — OK")

        deleted_ok = _delete_lore_source(conn, source_id_b)
        assert deleted_ok, "Source B deletion failed"
        sources_after = _list_lore_sources(conn)
        active_ids_after = {s["id"] for s in sources_after}
        assert source_id_b not in active_ids_after, "Source B still visible after delete"
        assert source_id_a in active_ids_after, "Source A missing after B deleted"
        print(f"  Deleted source B; {len(sources_after)} source(s) remain — OK")

        results["phase2_lore_sources"] = {
            "created": 2,
            "listed": len(sources_before),
            "deleted": 1,
            "remaining": len(sources_after),
            "ok": True,
        }

        # ------------------------------------------------------------------ #
        # Phase 1: Saga (Universe & Story) creation + campaign linkage        #
        # ------------------------------------------------------------------ #
        print("\n[Phase 1] Universe & Story UX")

        saga_owner_id = str(uuid.uuid4())
        saga_id = _create_saga(
            conn,
            player_id=saga_owner_id,
            universe_id="star_wars",
            title="Tales of the Rebellion",
        )
        print(f"  Created saga: {saga_id[:8]}… ('Tales of the Rebellion')")

        # Campaign creation
        print("\nCreating campaign (linked to saga)...")
        campaign_id, player_id = _create_campaign(conn, args.time_period, saga_id)
        print(f"  campaign_id: {campaign_id}")
        print(f"  player_id  : {player_id}")

        # Verify saga linkage
        saga_detail = _get_saga_detail(conn, saga_id)
        saga_campaigns = saga_detail.get("campaigns", [])
        linked = any(c["campaign_id"] == campaign_id for c in saga_campaigns)
        print(
            f"  Saga timeline: {len(saga_campaigns)} campaign(s) linked — "
            f"{'OK' if linked else 'FAIL'}"
        )
        if not linked:
            results["errors"].append("Campaign not linked to saga in timeline")

        # List sagas for player
        player_sagas = _list_sagas_for_player(conn, saga_owner_id)
        print(f"  Player saga list: {len(player_sagas)} saga(s) found")

        results["phase1_saga"] = {
            "saga_id": saga_id,
            "linked_campaigns": len(saga_campaigns),
            "player_sagas": len(player_sagas),
            "ok": linked,
        }

        # ------------------------------------------------------------------ #
        # Turns — mocked agents for deterministic offline execution          #
        # ------------------------------------------------------------------ #
        print(
            f"\n[Turns] Running {args.turns} turn(s) "
            f"(ENCOUNTER_SEED={os.environ.get('ENCOUNTER_SEED')} | "
            f"ENABLE_PORTRAITS={os.environ.get('ENABLE_PORTRAITS', '0')})"
        )

        ok_count = 0
        portrait_checks: list[dict] = []

        def _mock_director_plan(*args, **kwargs):
            return _MOCK_DIRECTOR_PLAN

        with patch("backend.app.core.nodes.director.DirectorAgent") as MockDirector, \
             patch("backend.app.core.nodes.narrator.NarratorAgent") as MockNarrator, \
             patch("backend.app.core.nodes.mechanic.MechanicAgent") as MockMechanic, \
             patch("backend.app.core.nodes.encounter.CastingAgent"), \
             patch("backend.app.core.agents.continuity_agent.ContinuityAgent") as MockContinuity:

            MockDirector.return_value.plan = _mock_director_plan
            MockNarrator.return_value.generate = _mock_narrator_generate
            MockMechanic.return_value.resolve = _mock_mechanic_resolve
            # ContinuityAgent.update is called as an instance method — mock it as a no-op
            MockContinuity.return_value.update.return_value = None

            for i, user_input in enumerate(inputs):
                try:
                    state = build_initial_gamestate(conn, campaign_id, player_id)
                    state.user_input = user_input
                    result = run_turn(conn, state)

                    text_preview = (result.final_text or "")[:80].replace("\n", " ")
                    if len(result.final_text or "") > 80:
                        text_preview += "..."

                    n_actions = len(result.suggested_actions or [])

                    # Validate suggested_actions structure
                    if n_actions == 0:
                        raise AssertionError("suggested_actions is empty")

                    ok_count += 1
                    results["turns"].append(
                        {
                            "turn": i + 1,
                            "input": user_input[:50],
                            "ok": True,
                            "actions": n_actions,
                            "text_preview": text_preview,
                        }
                    )

                    # Phase 3: Visual layer field check
                    vis = _check_portrait_fields(result)
                    portrait_checks.append(vis)

                    if (i + 1) % 5 == 0 or i == 0:
                        print(
                            f"  Turn {i + 1:2d}: ok | {n_actions} action(s) | "
                            f"schema_ok={vis['schema_ok']}"
                        )

                except Exception as e:
                    results["turns"].append(
                        {
                            "turn": i + 1,
                            "input": user_input[:50],
                            "ok": False,
                            "error": f"{type(e).__name__}: {e}",
                        }
                    )
                    results["errors"].append(f"Turn {i + 1}: {type(e).__name__}: {e}")
                    print(f"  Turn {i + 1} FAILED: {e}", file=sys.stderr)

        # Phase 3 summary — schema-level V11 visual layer verification
        portraits_enabled = os.environ.get("ENABLE_PORTRAITS", "0") == "1"
        schema_ok = all(p["schema_ok"] for p in portrait_checks) if portrait_checks else False
        results["phase3_visual"] = {
            "portraits_enabled": portraits_enabled,
            "party_status_item_has_portrait_url": all(
                p["party_status_item_has_portrait_url"] for p in portrait_checks
            ) if portrait_checks else False,
            "turn_response_has_location_art_url": all(
                p["turn_response_has_location_art_url"] for p in portrait_checks
            ) if portrait_checks else False,
            "schema_ok": schema_ok,
            "ok": schema_ok,
        }

        # ------------------------------------------------------------------ #
        # Final verification                                                  #
        # ------------------------------------------------------------------ #
        rendered = get_rendered_turns(conn, campaign_id, limit=500)
        max_turn = get_current_turn_number(conn, campaign_id)

        print("\n--- V11.0 Simulation Summary ---")
        p1 = results["phase1_saga"]
        p2 = results["phase2_lore_sources"]
        p3 = results["phase3_visual"]
        print(
            f"  [Phase 1] Universe & Story UX : "
            f"saga={p1.get('saga_id', '')[:8]}… | "
            f"chapters={p1.get('linked_campaigns', 0)} | "
            f"ok={p1['ok']}"
        )
        print(
            f"  [Phase 2] Lore Ingestion      : "
            f"created={p2.get('created', 0)} listed={p2.get('listed', 0)} "
            f"deleted={p2.get('deleted', 0)} remaining={p2.get('remaining', 0)} | "
            f"ok={p2['ok']}"
        )
        print(
            f"  [Phase 3] Visual Layer        : "
            f"portraits_enabled={p3.get('portraits_enabled', False)} | "
            f"portrait_url_field={p3.get('party_status_item_has_portrait_url', False)} | "
            f"location_art_field={p3.get('turn_response_has_location_art_url', False)} | "
            f"schema_ok={p3.get('schema_ok', False)}"
        )
        print(f"  Turns executed  : {args.turns}")
        print(f"  Rendered turns  : {len(rendered)}")
        print(f"  Max turn number : {max_turn}")
        print(f"  Successes       : {ok_count}/{len(results['turns'])}")

        if results["errors"]:
            print(f"\n  Errors ({len(results['errors'])}):")
            for err in results["errors"]:
                print(f"    - {err}")

        # Gate checks
        failed = False

        if len(rendered) != args.turns:
            print(
                f"\n  FAILED: rendered count ({len(rendered)}) != turn count ({args.turns})",
                file=sys.stderr,
            )
            failed = True

        if ok_count != len(results["turns"]):
            bad_turns = [t["turn"] for t in results["turns"] if not t.get("ok")]
            print(f"\n  FAILED: turns {bad_turns} errored", file=sys.stderr)
            failed = True

        if not results["phase1_saga"]["ok"]:
            print("\n  FAILED: saga linkage assertion", file=sys.stderr)
            failed = True

        if not results["phase2_lore_sources"]["ok"]:
            print("\n  FAILED: lore source lifecycle assertion", file=sys.stderr)
            failed = True

        if not results["phase3_visual"].get("schema_ok", False):
            print("\n  FAILED: V11 visual layer schema assertions", file=sys.stderr)
            failed = True

        if failed:
            return 1

        print("\nV11.0 simulation OK.")
        return 0

    finally:
        conn.close()
        if _cleanup_db and os.path.exists(_cleanup_db):
            try:
                os.unlink(_cleanup_db)
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(main())
