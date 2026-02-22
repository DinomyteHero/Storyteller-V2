"""Deferred maintenance agents — run post-commit to reduce transaction hold time.

Maintenance agents (Memory, QuestWeaver, Progression, PsychArchivist) write
their world_state mutations as JSON patches to `pending_world_state_patches`.
These patches are merged into the live world_state on the NEXT turn's load.

This reduces the `BEGIN IMMEDIATE` lock duration from 10-20s to ~2s on
maintenance turns by moving LLM calls out of the transaction boundary.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from backend.app.core.error_handling import AgentFailureError, authoritative_call
from backend.app.constants import (
    COMMIT_GROUP2_MAX_WORKERS,
    QUEST_WEAVER_GENERATION_INTERVAL,
    PROGRESSION_INTERVAL_BASE,
    PROGRESSION_INTERVAL_HIGH_INTENSITY,
    REVELATION_EVAL_INTERVAL,
    CALLBACK_CRYSTALLIZE_INTERVAL,
    PLAYER_PROFILE_INTERVAL,
    PLAYER_PROFILE_MIN_TURNS,
    DECISION_LEDGER_EVAL_INTERVAL,
)
from backend.app.models.event_utils import ensure_event

logger = logging.getLogger(__name__)


def apply_pending_patches(conn: sqlite3.Connection, campaign_id: str, world_state: dict) -> dict:
    """Apply unapplied patches to world_state and mark them applied.

    Called during state loading (before returning GameState to the pipeline).
    Returns the updated world_state dict.
    """
    rows = conn.execute(
        "SELECT id, agent_name, patch_json FROM pending_world_state_patches "
        "WHERE campaign_id = ? AND applied = 0 ORDER BY id",
        (campaign_id,),
    ).fetchall()

    if not rows:
        return world_state

    applied_ids = []
    for row in rows:
        patch_id = row["id"]
        agent_name = row["agent_name"]
        try:
            patch = json.loads(row["patch_json"])
            _merge_patch(world_state, patch)
            applied_ids.append(patch_id)
            logger.debug("Applied deferred patch from %s (id=%d)", agent_name, patch_id)
        except Exception as e:
            logger.warning("Failed to apply deferred patch id=%d from %s: %s", patch_id, agent_name, e)
            applied_ids.append(patch_id)  # Mark as applied to prevent retry loops

    if applied_ids:
        placeholders = ",".join("?" for _ in applied_ids)
        conn.execute(
            f"UPDATE pending_world_state_patches SET applied = 1 WHERE id IN ({placeholders})",
            applied_ids,
        )
        # Persist the merged world_state back to campaigns table
        conn.execute(
            "UPDATE campaigns SET world_state_json = ? WHERE id = ?",
            (json.dumps(world_state), campaign_id),
        )
        conn.commit()
        logger.info("Applied %d deferred patches for campaign %s", len(applied_ids), campaign_id)

    return world_state


def _merge_patch(target: dict, patch: dict) -> None:
    """Deep-merge patch into target. Lists are replaced, not appended."""
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge_patch(target[key], value)
        else:
            target[key] = value


def _write_patch(db_path: str, campaign_id: str, turn_number: int, agent_name: str, patch: dict) -> None:
    """Write a single agent's world_state patch to the DB."""
    from backend.app.db.connection import get_connection

    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO pending_world_state_patches (campaign_id, turn_number, agent_name, patch_json) "
            "VALUES (?, ?, ?, ?)",
            (campaign_id, turn_number, agent_name, json.dumps(patch)),
        )
        conn.commit()
    finally:
        conn.close()


def run_deferred_maintenance(
    db_path: str,
    campaign_id: str,
    player_id: str,
    turn_number: int,
    world_state_snapshot: dict,
    state_snapshot: dict,
    events_snapshot: list,
    arc_guidance: dict | None,
    campaign_settings: dict | None = None,
) -> None:
    """Run deferred maintenance agents in a background thread.

    This is called AFTER conn.commit() in the commit node. Each agent
    captures its world_state mutations as a JSON patch and writes it
    to pending_world_state_patches for next-turn application.

    Args:
        db_path: Path to SQLite database (for creating independent connections)
        campaign_id: Campaign ID
        player_id: Player ID
        turn_number: The just-committed turn number
        world_state_snapshot: Deep copy of world_state at commit time
        state_snapshot: Relevant subset of pipeline state (player, present_npcs, etc.)
        events_snapshot: Serialized events from this turn
        arc_guidance: Arc guidance dict from pipeline state
        campaign_settings: Cloud LLM settings for provider resolution (V12.0)
    """
    def _background():
        try:
            _run_agents(
                db_path=db_path,
                campaign_id=campaign_id,
                player_id=player_id,
                turn_number=turn_number,
                world_state=world_state_snapshot,
                state=state_snapshot,
                events=events_snapshot,
                arc_guidance=arc_guidance,
                campaign_settings=campaign_settings,
            )
        except Exception as e:
            logger.error(
                "Deferred maintenance agents failed (campaign=%s, turn=%d): %s",
                campaign_id, turn_number, e,
            )

    thread = threading.Thread(
        target=_background,
        name=f"deferred-maintenance-{campaign_id}-{turn_number}",
        daemon=True,
    )
    thread.start()


def _resolve_deferred_llm(role: str, campaign_settings: dict | None, db_path: str):
    """Resolve an AgentLLM for a deferred agent using campaign settings.

    Creates a temporary DB connection for key resolution.
    Returns None on failure (agent will use its default LLM).
    """
    if not campaign_settings:
        return None
    try:
        from backend.app.core.provider_resolver import make_agent_llm
        from backend.app.db.connection import get_connection
        conn = get_connection(db_path)
        try:
            return make_agent_llm(role, campaign_settings, conn)
        finally:
            conn.close()
    except Exception as e:
        logger.debug("Deferred LLM resolution for %s failed: %s", role, e)
        return None


def _run_agents(
    db_path: str,
    campaign_id: str,
    player_id: str,
    turn_number: int,
    world_state: dict,
    state: dict,
    events: list,
    arc_guidance: dict | None,
    campaign_settings: dict | None = None,
) -> None:
    """Execute the 4 deferred maintenance agents and write their patches."""
    import copy

    final_text = state.get("final_text", "")
    intent = state.get("intent", "")
    present_npcs = state.get("present_npcs") or []
    recent_narrative = state.get("recent_narrative") or []

    # --- Group 2: MemoryAgent + QuestWeaverAgent (parallel, no DB needed) ---
    ws_before_g2 = copy.deepcopy(world_state)

    mem_events = [
        {"event_type": e.get("event_type", ""), "payload": e.get("payload", {})}
        for e in events
    ] if present_npcs and final_text else []

    def _run_memory():
        if present_npcs and final_text:
            from backend.app.core.agents.memory_agent import MemoryAgent
            _mem_llm = _resolve_deferred_llm("memory", campaign_settings, db_path)
            authoritative_call(
                "MemoryAgent",
                MemoryAgent(llm=_mem_llm).update,
                world_state=world_state,
                final_text=final_text,
                turn_number=turn_number,
                present_npcs=present_npcs,
                events=mem_events,
            )

    def _run_quest_weaver():
        if not (final_text and intent != "META"):
            return
        from backend.app.core.agents.quest_weaver_agent import QuestWeaverAgent
        _qw_llm = _resolve_deferred_llm("quest_weaver", campaign_settings, db_path)
        _qw = QuestWeaverAgent(llm=_qw_llm)
        _qw_events = [
            {"event_type": e.get("event_type", ""), "payload": e.get("payload", {})}
            for e in events
        ]
        # Evaluate active quests
        _dq = world_state.get("dynamic_quests") or []
        _active_dq = [q for q in _dq if q.get("status") == "active"]
        if _active_dq:
            authoritative_call(
                "QuestWeaverAgent.evaluate",
                _qw.evaluate_completion,
                world_state=world_state,
                final_text=final_text,
                events=_qw_events,
            )
        # Generate new quests — arc-aware triggers (V8.0)
        _active_count = sum(1 for q in (world_state.get("dynamic_quests") or []) if q.get("status") == "active")
        _arc_st = (world_state.get("arc_state") or {})
        _arc = _arc_st.get("current_stage", "SETUP")
        _arc_transitioned = (arc_guidance or {}).get("transition_occurred", False) if isinstance(arc_guidance, dict) else False
        _entering_new_arc = _arc == "SETUP" and int(_arc_st.get("current_arc_number", 1)) > 1
        _in_resolution = _arc == "RESOLUTION"

        _should_generate = (
            (turn_number % QUEST_WEAVER_GENERATION_INTERVAL == 0)
            or _active_count == 0
            or _arc_transitioned
            or _entering_new_arc
        ) and not _in_resolution  # Don't generate new quests during RESOLUTION

        if _should_generate:
            _recent_narr = "\n".join(recent_narrative[-2:])[:600] if recent_narrative else ""
            # V8.0: Inject dangling hooks from previous arcs for saga continuity
            _qw_ws = world_state
            _arc_history = _arc_st.get("arc_history") or []
            if _arc_history and _entering_new_arc:
                _prev_hooks = _arc_history[-1].get("dangling_hooks") or [] if isinstance(_arc_history[-1], dict) else []
                if _prev_hooks:
                    _dq = list(_qw_ws.get("dynamic_quests") or [])
                    for hook in _prev_hooks[:3]:
                        _dq.append({"_arc_dangling_hook": hook})
                    _qw_ws = {**_qw_ws, "dynamic_quests": _dq}
            authoritative_call(
                "QuestWeaverAgent.generate",
                _qw.generate,
                world_state=_qw_ws,
                arc_stage=_arc,
                player_location=state.get("current_location") or "",
                turn_number=turn_number,
                recent_narrative=_recent_narr,
            )

    # V10.0 Feature 1: RevelationAgent — information economy
    _arc = (arc_guidance or {}).get("arc_stage") or "SETUP"

    def _run_revelation():
        if not (final_text and intent != "META" and turn_number % REVELATION_EVAL_INTERVAL == 0):
            return
        try:
            from backend.app.core.agents.revelation_agent import RevelationAgent
            _rev_llm = _resolve_deferred_llm("revelation_agent", campaign_settings, db_path)
            authoritative_call(
                "RevelationAgent",
                RevelationAgent(llm=_rev_llm).evaluate,
                world_state=world_state,
                arc_stage=_arc,
                turn_number=turn_number,
                recent_narrative="\n".join(recent_narrative[-2:])[:600] if recent_narrative else "",
                events=mem_events,
            )
        except AgentFailureError as e:
            logger.warning("Deferred RevelationAgent failed: %s", e)

    # V10.0 Feature 3: CallbackCrystallizerAgent — peak moment identification
    def _run_callback_crystallizer():
        if not (final_text and intent != "META" and turn_number % CALLBACK_CRYSTALLIZE_INTERVAL == 0):
            return
        try:
            from backend.app.core.agents.callback_crystallizer_agent import CallbackCrystallizerAgent
            _cb_llm = _resolve_deferred_llm("callback_crystallizer", campaign_settings, db_path)
            authoritative_call(
                "CallbackCrystallizerAgent",
                CallbackCrystallizerAgent(llm=_cb_llm).crystallize,
                world_state=world_state,
                recent_narrative="\n".join(recent_narrative[-3:])[:900] if recent_narrative else "",
                turn_number=turn_number,
                events=mem_events,
                arc_stage=_arc,
            )
        except AgentFailureError as e:
            logger.warning("Deferred CallbackCrystallizerAgent failed: %s", e)

    # V1.1: DecisionLedgerAgent — consequence delivery tracking
    def _run_decision_ledger():
        if not (final_text and intent != "META" and turn_number % DECISION_LEDGER_EVAL_INTERVAL == 0):
            return
        try:
            from backend.app.core.agents.decision_ledger_agent import DecisionLedgerAgent
            from backend.app.db.connection import get_connection
            _dl_llm = _resolve_deferred_llm("decision_ledger", campaign_settings, db_path)
            _dl_conn = get_connection(db_path)
            try:
                DecisionLedgerAgent(llm=_dl_llm).evaluate(
                    conn=_dl_conn,
                    campaign_id=campaign_id,
                    world_state=world_state,
                    recent_narrative="\n".join(recent_narrative[-3:])[:600] if recent_narrative else "",
                    recent_events=mem_events,
                    turn_number=turn_number,
                )
                _dl_conn.commit()
            finally:
                _dl_conn.close()
        except Exception as e:
            logger.warning("Deferred DecisionLedgerAgent failed: %s", e)

    # V10.0 Feature 4: PlayerProfileAgent — deterministic behavioral profiling
    def _run_player_profile():
        if not (turn_number % PLAYER_PROFILE_INTERVAL == 0 and turn_number >= PLAYER_PROFILE_MIN_TURNS):
            return
        try:
            from backend.app.core.agents.player_profile_agent import PlayerProfileAgent
            PlayerProfileAgent().analyze(
                world_state=world_state,
                state_snapshot=state,
                turn_number=turn_number,
            )
        except Exception as e:
            logger.warning("Deferred PlayerProfileAgent failed: %s", e)

    # Run Group 2 in parallel (expanded with V10.0 narrative intelligence agents)
    _g2_max_workers = max(COMMIT_GROUP2_MAX_WORKERS, 3)
    with ThreadPoolExecutor(max_workers=_g2_max_workers, thread_name_prefix="deferred_g2") as pool:
        futures = {
            pool.submit(_run_memory): "MemoryAgent",
            pool.submit(_run_quest_weaver): "QuestWeaverAgent",
            pool.submit(_run_revelation): "RevelationAgent",
            pool.submit(_run_callback_crystallizer): "CallbackCrystallizerAgent",
            pool.submit(_run_player_profile): "PlayerProfileAgent",
            pool.submit(_run_decision_ledger): "DecisionLedgerAgent",
        }
        for fut in as_completed(futures):
            try:
                fut.result()
            except AgentFailureError as e:
                logger.warning("Deferred %s failed: %s", futures[fut], e)

    # Extract Group 2 patches
    g2_patch = _diff_world_state(ws_before_g2, world_state)
    if g2_patch:
        _write_patch(db_path, campaign_id, turn_number, "group2_memory_quest", g2_patch)

    # --- Group 3: ProgressionAgent + PsychArchivistAgent (sequential, need DB) ---
    from backend.app.db.connection import get_connection

    _arc_g = arc_guidance or {}
    _arc_state = _arc_g.get("arc_state") or {} if isinstance(_arc_g, dict) else {}
    _current_arc_stage = _arc_state.get("current_stage", "SETUP") if isinstance(_arc_state, dict) else "SETUP"
    _progression_interval = (
        PROGRESSION_INTERVAL_HIGH_INTENSITY
        if _current_arc_stage in ("RISING", "CLIMAX")
        else PROGRESSION_INTERVAL_BASE
    )

    ws_before_g3 = copy.deepcopy(world_state)
    conn = get_connection(db_path)
    try:
        # ProgressionAgent
        if final_text and intent != "META" and turn_number % _progression_interval == 0:
            from backend.app.core.agents.progression_agent import ProgressionAgent
            _prog_llm = _resolve_deferred_llm("progression", campaign_settings, db_path)
            _prog_player = state.get("player")
            _prog_stats: dict = {}
            _prog_psych: dict = {}
            _prog_bg = ""
            if isinstance(_prog_player, dict):
                _prog_stats = dict(_prog_player.get("stats") or {})
                _prog_psych = dict(_prog_player.get("psych_profile") or {})
                _prog_bg = str(_prog_player.get("background") or "")
            _prog_narr = "\n".join(recent_narrative[-2:])[:600] if recent_narrative else ""
            try:
                authoritative_call(
                    "ProgressionAgent",
                    ProgressionAgent(llm=_prog_llm).advance,
                    world_state=world_state,
                    player_stats=_prog_stats,
                    psych_profile=_prog_psych,
                    background=_prog_bg,
                    turn_number=turn_number,
                    recent_narrative=_prog_narr,
                    conn=conn,
                    campaign_id=campaign_id,
                    player_id=player_id,
                )
            except AgentFailureError as e:
                logger.warning("Deferred ProgressionAgent failed: %s", e)

        # PsychArchivistAgent
        if final_text and intent != "META":
            from backend.app.core.agents.psych_archivist_agent import PsychArchivistAgent
            _pa_llm = _resolve_deferred_llm("psych_archivist", campaign_settings, db_path)
            _psych_player = state.get("player")
            _psych_profile: dict = {}
            _psych_bg = ""
            if isinstance(_psych_player, dict):
                _psych_profile = dict(_psych_player.get("psych_profile") or {})
                _psych_bg = str(_psych_player.get("background") or "")
            _psych_narr = "\n".join(recent_narrative[-2:])[:600] if recent_narrative else ""
            _psych_events = [
                {"event_type": e.get("event_type", ""), "payload": e.get("payload", {})}
                for e in events
            ]
            _arc_stage = _arc_g.get("arc_stage") if isinstance(_arc_g, dict) else "SETUP"
            try:
                authoritative_call(
                    "PsychArchivistAgent",
                    PsychArchivistAgent(llm=_pa_llm).update,
                    world_state=world_state,
                    current_psych_profile=_psych_profile,
                    background=_psych_bg,
                    turn_number=turn_number,
                    recent_narrative=_psych_narr,
                    events=_psych_events,
                    arc_stage=_arc_stage or "SETUP",
                    conn=conn,
                    campaign_id=campaign_id,
                    player_id=player_id,
                )
            except AgentFailureError as e:
                logger.warning("Deferred PsychArchivistAgent failed: %s", e)
    finally:
        conn.close()

    # Extract Group 3 world_state patches (if any)
    g3_patch = _diff_world_state(ws_before_g3, world_state)
    if g3_patch:
        _write_patch(db_path, campaign_id, turn_number, "group3_progression_psych", g3_patch)


def _diff_world_state(before: dict, after: dict) -> dict:
    """Compute a shallow diff of top-level keys that changed."""
    patch = {}
    for key in after:
        if key not in before:
            patch[key] = after[key]
        elif after[key] != before[key]:
            patch[key] = after[key]
    return patch
