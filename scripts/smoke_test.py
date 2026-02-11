#!/usr/bin/env python3
"""Smoke-test CLI: create campaign (auto setup), run N turns, print summary.

Deterministic: uses ENCOUNTER_SEED for spawns. Prints outcomes and trimming flags.

Usage:
  python scripts/smoke_test.py [--turns 10] [--inputs "I look around,I ask the barkeep,..."]
  python scripts/smoke_test.py --turns 5 --use-temp-db    # safe for CI (no main DB)
  ENCOUNTER_SEED=42 python scripts/smoke_test.py --turns 5
  DEV_CONTEXT_STATS=1 python scripts/smoke_test.py --turns 3  # include trimming flags

Run from project root. Requires LLMs (Ollama or openai_compat) for real agents.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Ensure ENCOUNTER_SEED for deterministic spawns
if "ENCOUNTER_SEED" not in os.environ:
    os.environ["ENCOUNTER_SEED"] = "42"

from backend.app.config import DEFAULT_DB_PATH
from backend.app.core.companions import build_initial_companion_state
from backend.app.core.event_store import append_events, get_current_turn_number
from backend.app.core.graph import run_turn
from backend.app.core.state_loader import build_initial_gamestate, load_campaign
from backend.app.core.transcript_store import get_rendered_turns
from backend.app.db.connection import get_connection
from backend.app.db.migrate import apply_schema
from backend.app.models.events import Event


DEFAULT_INPUTS = [
    "I look around the room",
    "I ask the barkeep for information",
    "help",
    "I search the crates",
    "I tell her I'm leaving",
    "I walk to the market",
    "save",
    "I talk to the guard",
    "I pick up the datapad",
    "I examine the door",
]


def _create_campaign_auto(conn, time_period: str | None = "rebellion") -> tuple[str, str]:
    """Create campaign via Architect + Biographer (auto setup). Returns (campaign_id, player_id)."""
    import json
    from backend.app.core.agents import CampaignArchitect, BiographerAgent
    from backend.app.core.agents.base import AgentLLM

    try:
        arch = CampaignArchitect(llm=AgentLLM("architect"))
    except Exception as e:
        print(f"  Architect LLM fallback: {e}", file=sys.stderr)
        arch = CampaignArchitect(llm=None)
    try:
        bio = BiographerAgent(llm=AgentLLM("biographer"))
    except Exception as e:
        print(f"  Biographer LLM fallback: {e}", file=sys.stderr)
        bio = BiographerAgent(llm=None)

    skeleton = arch.build(time_period=time_period, themes=[])
    character_sheet = bio.build("A hero in a vast world", skeleton.get("time_period"))

    campaign_id = str(uuid.uuid4())
    player_id = str(uuid.uuid4())
    title = skeleton.get("title", "New Campaign")
    active_factions = skeleton.get("active_factions")
    if not isinstance(active_factions, list):
        ws = skeleton.get("world_state_json") or {}
        active_factions = ws.get("active_factions", []) if isinstance(ws, dict) else []
    if not isinstance(active_factions, list):
        active_factions = []
    companion_state = build_initial_companion_state(world_time_minutes=0)
    world_state = {"active_factions": active_factions, **companion_state}

    conn.execute(
        """INSERT INTO campaigns (id, title, time_period, world_state_json)
           VALUES (?, ?, ?, ?)""",
        (campaign_id, title, time_period or None, json.dumps(world_state)),
    )
    name = character_sheet.get("name", "Hero")
    stats = character_sheet.get("stats") or {}
    hp_current = int(character_sheet.get("hp_current", 10))
    starting_location = character_sheet.get("starting_location", "loc-tavern")
    conn.execute(
        """INSERT INTO characters (id, campaign_id, name, role, location_id, stats_json, hp_current, relationship_score, secret_agenda, credits)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
        (player_id, campaign_id, name, "Player", starting_location, json.dumps(stats), hp_current, None, None),
    )
    # NPC cast from skeleton
    from backend.app.api.v2_campaigns import _create_npc_cast_from_skeleton
    _create_npc_cast_from_skeleton(conn, campaign_id, skeleton, starting_location)
    conn.commit()
    initial_events = [Event(event_type="FLAG_SET", payload={"key": "campaign_started", "value": True})]
    append_events(conn, campaign_id, 1, initial_events)
    from backend.app.core.projections import apply_projection
    apply_projection(conn, campaign_id, initial_events)
    return campaign_id, player_id


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Smoke-test: create campaign (auto setup), run N turns, print summary."
    )
    ap.add_argument("--turns", "-n", type=int, default=5, help="Number of turns (default 5)")
    ap.add_argument(
        "--inputs",
        type=str,
        default=None,
        help="Comma-separated player inputs (default: built-in list)",
    )
    ap.add_argument("--db", type=str, default=None, help="DB path (default: config DEFAULT_DB_PATH)")
    ap.add_argument(
        "--use-temp-db",
        action="store_true",
        help="Use temporary DB (no main DB; safe for CI)",
    )
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

    inputs = [s.strip() for s in args.inputs.split(",")] if args.inputs else DEFAULT_INPUTS[: args.turns]
    if len(inputs) < args.turns:
        inputs = (inputs * ((args.turns // len(inputs)) + 1))[: args.turns]
    else:
        inputs = inputs[: args.turns]

    apply_schema(db_path)
    conn = get_connection(db_path)

    try:
        print("Creating campaign (auto setup)...")
        campaign_id, player_id = _create_campaign_auto(conn, time_period=args.time_period)
        print(f"  campaign_id={campaign_id} player_id={player_id}")

        print(f"\nRunning {args.turns} turns (ENCOUNTER_SEED={os.environ.get('ENCOUNTER_SEED', 'not set')})...")
        outcomes: list[dict] = []
        trimming_flags: list[dict] = []
        for i, user_input in enumerate(inputs):
            try:
                state = build_initial_gamestate(conn, campaign_id, player_id)
                state.user_input = user_input
                result = run_turn(conn, state)
                text_preview = (result.final_text or "")[:80].replace("\n", " ")
                if len((result.final_text or "")) > 80:
                    text_preview += "..."
                outcomes.append({
                    "turn": i + 1,
                    "input": user_input[:50],
                    "ok": True,
                    "text_preview": text_preview,
                    "suggestions": len(result.suggested_actions or []),
                })
                if result.context_stats:
                    trimming_flags.append({
                        "turn": i + 1,
                        "input": user_input[:30],
                        **result.context_stats,
                    })
            except Exception as e:
                outcomes.append({
                    "turn": i + 1,
                    "input": user_input[:50],
                    "ok": False,
                    "error": f"{type(e).__name__}: {e}",
                })
                print(f"  Turn {i + 1} FAILED: {e}", file=sys.stderr)

        # Summary
        rendered = get_rendered_turns(conn, campaign_id, limit=100)
        max_turn = get_current_turn_number(conn, campaign_id)
        print("\n--- Summary ---")
        print(f"  Turns executed: {args.turns}")
        print(f"  Rendered turns: {len(rendered)}")
        print(f"  Max turn_number (turn_events): {max_turn}")
        ok_count = sum(1 for o in outcomes if o.get("ok"))
        print(f"  Successes: {ok_count}/{len(outcomes)}")

        if trimming_flags:
            print("\n--- Trimming flags (DEV_CONTEXT_STATS) ---")
            for tf in trimming_flags:
                print(f"  Turn {tf.get('turn')}: {tf}")

        if len(rendered) != args.turns:
            print(f"\n  FAILED: rendered count ({len(rendered)}) != turn count ({args.turns})", file=sys.stderr)
            return 1
        if ok_count != len(outcomes):
            failed_turns = [o["turn"] for o in outcomes if not o.get("ok")]
            print(f"\n  FAILED: turns {failed_turns} errored", file=sys.stderr)
            return 1
        print("\nSmoke test OK.")
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
