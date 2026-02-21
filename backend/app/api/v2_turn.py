"""V2 turn execution endpoints: post_turn, post_turn_stream, classify, validation."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.app.constants import SUGGESTED_ACTIONS_TARGET
from backend.app.config import DEFAULT_DB_PATH, DEV_CONTEXT_STATS
from backend.app.core.error_handling import log_error_with_context
from backend.app.db.connection import get_connection
from backend.app.core.state_loader import build_initial_gamestate, load_campaign, load_player_by_id
from backend.app.core.companions import get_companion_by_id
from backend.app.core.companion_reactions import affinity_to_mood_tag
from backend.app.models.news import NEWS_FEED_MAX
from backend.app.core.graph import run_turn
from backend.app.models.state import GameState
from backend.app.models.turn_contract import TurnMeta
from backend.app.core.turn_contract import build_turn_contract
from backend.app.core.truth_ledger import get_facts_with_meta, upsert_facts, record_event
from backend.app.core.story_position import canonical_year_label_from_campaign
from backend.app.prompts.registry import prompt_registry_snapshot
from backend.app.api.campaign_models import TurnRequest, TurnResponse, PartyStatusItem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2", tags=["v2-turn"])

MAX_USER_INPUT_CHARS = int(os.environ.get("STORYTELLER_MAX_USER_INPUT_CHARS", "4000"))

_TURN_IDEMPOTENCY_HEADER = "Idempotency-Key"
_MAX_IDEMPOTENCY_KEY_LEN = 128
_campaign_turn_locks: dict[str, threading.Lock] = {}
_campaign_turn_locks_guard = threading.Lock()


# ── Shared utilities (imported by other modules) ─────────────────────

def _get_conn():
    """Return DB connection."""
    return get_connection(DEFAULT_DB_PATH)


def _ensure_campaign_and_player(conn, campaign_id: str, player_id: str) -> None:
    """Raise HTTP 404 if campaign or player not found."""
    if load_campaign(conn, campaign_id) is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if load_player_by_id(conn, campaign_id, player_id) is None:
        raise HTTPException(status_code=404, detail="Player not found")


def _world_state_dict(camp: dict) -> dict:
    ws = camp.get("world_state_json") if isinstance(camp, dict) else {}
    if isinstance(ws, str):
        try:
            ws = json.loads(ws) if ws else {}
        except json.JSONDecodeError:
            ws = {}
    return ws if isinstance(ws, dict) else {}


# ── Idempotency ──────────────────────────────────────────────────────

def _canonicalize_turn_request(body: TurnRequest) -> dict[str, Any]:
    if body.intent is not None:
        intent_payload = body.intent.model_dump(mode="json")
    else:
        intent_payload = None
    return {
        "user_input": body.user_input or "",
        "intent": intent_payload,
        "debug": bool(body.debug),
        "include_state": bool(body.include_state),
    }


def _validate_turn_input_limits(body: TurnRequest) -> None:
    user_input = body.user_input or ""
    intent_utterance = ""
    if body.intent is not None:
        intent_utterance = str(body.intent.user_utterance or "")
    if len(user_input) > MAX_USER_INPUT_CHARS or len(intent_utterance) > MAX_USER_INPUT_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"user_input exceeds max allowed length ({MAX_USER_INPUT_CHARS} chars).",
        )


def _turn_request_hash(body: TurnRequest) -> str:
    payload = _canonicalize_turn_request(body)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _resolve_idempotency_key(request: Request | None, body: TurnRequest) -> str | None:
    header_key = ""
    if request is not None:
        header_key = (request.headers.get(_TURN_IDEMPOTENCY_HEADER, "") or "").strip()
    body_key = (body.idempotency_key or "").strip()
    key = header_key or body_key
    if not key:
        return None
    if len(key) > _MAX_IDEMPOTENCY_KEY_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"Idempotency key too long (max {_MAX_IDEMPOTENCY_KEY_LEN} chars).",
        )
    return key


@contextmanager
def _campaign_turn_lock(campaign_id: str):
    with _campaign_turn_locks_guard:
        lock = _campaign_turn_locks.setdefault(campaign_id, threading.Lock())
    acquired = lock.acquire(blocking=False)
    if not acquired:
        raise HTTPException(
            status_code=409,
            detail="A turn is already in progress for this campaign. Retry after it finishes.",
        )
    try:
        yield
    finally:
        lock.release()


def _idempotency_lookup(
    conn, campaign_id: str, player_id: str, endpoint: str,
    idempotency_key: str, request_hash: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """SELECT request_hash, status, response_json
           FROM turn_idempotency
           WHERE campaign_id = ? AND player_id = ? AND endpoint = ? AND idempotency_key = ?""",
        (campaign_id, player_id, endpoint, idempotency_key),
    ).fetchone()
    if not row:
        return None
    existing_hash = str(row["request_hash"] or "")
    if existing_hash != request_hash:
        raise HTTPException(
            status_code=409,
            detail="Idempotency key reuse with different request payload is not allowed.",
        )
    status = str(row["status"] or "processing")
    if status != "completed":
        raise HTTPException(
            status_code=409,
            detail="An identical request is already processing. Retry shortly.",
        )
    try:
        payload = json.loads(row["response_json"] or "{}")
    except Exception:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def _idempotency_begin(
    conn, campaign_id: str, player_id: str, endpoint: str,
    idempotency_key: str, request_hash: str,
) -> None:
    conn.execute(
        """INSERT INTO turn_idempotency
           (campaign_id, player_id, endpoint, idempotency_key, request_hash, status, response_json)
           VALUES (?, ?, ?, ?, ?, 'processing', NULL)""",
        (campaign_id, player_id, endpoint, idempotency_key, request_hash),
    )
    conn.commit()


def _idempotency_complete(
    conn, campaign_id: str, player_id: str, endpoint: str,
    idempotency_key: str, payload: dict[str, Any],
) -> None:
    conn.execute(
        """UPDATE turn_idempotency
           SET status = 'completed', response_json = ?, updated_at = datetime('now')
           WHERE campaign_id = ? AND player_id = ? AND endpoint = ? AND idempotency_key = ?""",
        (json.dumps(payload), campaign_id, player_id, endpoint, idempotency_key),
    )
    conn.commit()


# ── Turn helpers ─────────────────────────────────────────────────────

def _pad_suggestions_to_three(actions: list) -> list:
    """Backward-compat alias."""
    return _pad_suggestions_for_ui(actions)


def _pad_suggestions_for_ui(actions: list) -> list:
    """Pass through suggestions for the UI. SuggestionRefiner owns the 4-item contract."""
    if not actions:
        return []
    from backend.app.core.action_lint import lint_actions

    padded, _notes = lint_actions(actions or [])
    return padded[:SUGGESTED_ACTIONS_TARGET]


def _seed_default_objective(conn, campaign_id: str) -> None:
    existing = conn.execute(
        "SELECT id FROM objectives WHERE campaign_id = ? AND status = 'active' LIMIT 1",
        (campaign_id,),
    ).fetchone()
    if existing:
        return
    oid = f"obj-{uuid.uuid4().hex[:8]}"
    conn.execute(
        """INSERT INTO objectives (id, campaign_id, title, description, success_conditions_json, progress_json, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 'active', datetime('now'), datetime('now'))""",
        (
            oid, campaign_id,
            "Establish your foothold",
            "Secure intelligence and identify the primary opposition.",
            json.dumps({"type": "discover_opposition"}),
            json.dumps({"progress": 0, "target": 3}),
        ),
    )


def _active_objectives(conn, campaign_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT id, title, description, progress_json, status FROM objectives WHERE campaign_id = ? AND status = 'active' ORDER BY updated_at DESC LIMIT 5",
        (campaign_id,),
    ).fetchall()
    out = []
    for r in rows:
        progress = {}
        try:
            progress = json.loads(r["progress_json"] or "{}")
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        out.append({
            "objective_id": r["id"], "title": r["title"],
            "description": r["description"], "progress": progress, "status": r["status"],
        })
    return out


def _decrement_beats(conn, campaign_id: str, camp: dict) -> tuple[int, str | None, bool]:
    ws = _world_state_dict(camp)
    beats = int(ws.get("beats_remaining", 4)) - 1
    scene_note = None
    forced = False
    if beats <= 0:
        beats = 4
        ws["scene_id"] = f"scene-{uuid.uuid4().hex[:8]}"
        ws["force_scene_transition"] = True
        forced = True
        scene_note = "Scene transitioned due to beat budget exhaustion."
    else:
        ws["force_scene_transition"] = False
    ws["beats_remaining"] = beats
    conn.execute("UPDATE campaigns SET world_state_json = ? WHERE id = ?", (json.dumps(ws), campaign_id))
    return beats, scene_note, forced


def _inject_truth_constraints_into_state(conn, campaign_id: str, state: GameState) -> None:
    """Mirror immutable truth facts into world_state ledger for narrator constraints."""
    from backend.app.api.v2_campaigns import _merge_canon_constraints_into_world_state

    if not isinstance(state.campaign, dict):
        return
    ws = state.campaign.get("world_state_json")
    if not isinstance(ws, dict):
        ws = {}
    facts, immutable = get_facts_with_meta(conn, campaign_id)
    immutable_lines = []
    for key, is_imm in immutable.items():
        if not is_imm:
            continue
        val = facts.get(key)
        if isinstance(val, str):
            immutable_lines.append(val)
        else:
            immutable_lines.append(f"{key}: {val}")
    _merge_canon_constraints_into_world_state(ws, immutable_lines)
    state.campaign["world_state_json"] = ws


# ── Classify endpoint ────────────────────────────────────────────────

class ClassifyRequest(BaseModel):
    """Lightweight request for intent classification preview."""
    user_input: str = ""


class ClassifyResponse(BaseModel):
    """Preview how the router will classify free text."""
    route: str
    action_class: str
    requires_resolution: bool
    confidence: float
    rationale_short: str


@router.post("/campaigns/{campaign_id}/classify", response_model=ClassifyResponse)
def classify_intent(campaign_id: str, body: ClassifyRequest):
    """Preview router classification for free text input without running a full turn."""
    from backend.app.core.router import route as router_route

    user_input = (body.user_input or "").strip()
    if not user_input:
        return ClassifyResponse(
            route="META", action_class="META",
            requires_resolution=False, confidence=1.0, rationale_short="empty input",
        )
    result = router_route(user_input)
    return ClassifyResponse(
        route=result.route, action_class=result.action_class,
        requires_resolution=result.requires_resolution,
        confidence=result.confidence, rationale_short=result.rationale_short,
    )


# ── Post turn (non-streaming) ───────────────────────────────────────

@router.post("/campaigns/{campaign_id}/turn", response_model=TurnResponse)
def post_turn(
    campaign_id: str,
    player_id: str = Query(..., description="Player character ID"),
    request: Request = None,
    body: TurnRequest | None = None,
):
    """Run one turn. Returns narrated_text, suggested_actions, player_sheet, inventory, quest_log."""
    if body is None:
        body = TurnRequest(user_input="")
    _validate_turn_input_limits(body)
    conn = _get_conn()
    start_ts = time.perf_counter()
    request_id = getattr(request.state, "request_id", "unknown") if request is not None else "unknown"
    endpoint_key = "turn"
    idempotency_key = _resolve_idempotency_key(request, body)
    request_hash = _turn_request_hash(body) if idempotency_key else ""
    idempotency_started = False
    idempotency_completed = False
    turn_lock_ctx = _campaign_turn_lock(campaign_id)
    turn_lock_acquired = False
    try:
        turn_lock_ctx.__enter__()
        turn_lock_acquired = True
        _ensure_campaign_and_player(conn, campaign_id, player_id)
        if idempotency_key:
            cached_payload = _idempotency_lookup(
                conn=conn, campaign_id=campaign_id, player_id=player_id,
                endpoint=endpoint_key, idempotency_key=idempotency_key, request_hash=request_hash,
            )
            if cached_payload:
                return TurnResponse(**cached_payload)
            _idempotency_begin(
                conn=conn, campaign_id=campaign_id, player_id=player_id,
                endpoint=endpoint_key, idempotency_key=idempotency_key, request_hash=request_hash,
            )
            idempotency_started = True

        state = build_initial_gamestate(conn, campaign_id, player_id)
        _inject_truth_constraints_into_state(conn, campaign_id, state)
        if body.intent is not None:
            state.user_input = body.intent.user_utterance or json.dumps(body.intent.model_dump(mode="json"))
        else:
            state.user_input = body.user_input
        if body.structured_intent is not None:
            state.structured_intent = body.structured_intent.model_dump(mode="json")
        try:
            result = run_turn(conn, state)
        except Exception as e:
            log_error_with_context(
                error=e, node_name="turn", campaign_id=campaign_id,
                turn_number=state.turn_number, agent_name="run_turn",
                extra_context={"user_input": body.user_input[:100] if body.user_input else None},
            )
            raise

        camp = load_campaign(conn, campaign_id) or {}
        _ws_raw = camp.get("world_state_json")
        if isinstance(_ws_raw, str):
            try:
                _ws_raw = json.loads(_ws_raw) if _ws_raw else {}
            except json.JSONDecodeError:
                _ws_raw = {}
        _ws_raw = _ws_raw if isinstance(_ws_raw, dict) else {}
        quest_log = _ws_raw.get("quest_log") or {}
        player_sheet = result.player.model_dump(mode="json") if result.player else {}
        inventory = (result.player.inventory or []) if result.player else []
        raw_actions = result.suggested_actions or []
        suggested_actions = _pad_suggestions_for_ui(raw_actions)

        world_time_minutes = None
        if result.campaign and isinstance(result.campaign, dict):
            world_time_minutes = result.campaign.get("world_time_minutes")
        if world_time_minutes is None and camp:
            world_time_minutes = camp.get("world_time_minutes")
        canonical_year_label = canonical_year_label_from_campaign(campaign=result.campaign, world_state=_ws_raw)

        debug_out = None
        if body.debug:
            world_state = _ws_raw if isinstance(_ws_raw, dict) else {}
            active_factions = world_state.get("active_factions")
            if active_factions is None and result.campaign and isinstance(result.campaign.get("world_state_json"), dict):
                active_factions = result.campaign["world_state_json"].get("active_factions")
            debug_out = {
                "router_intent": getattr(result, "intent", None),
                "router_route": getattr(result, "route", None),
                "router_action_class": getattr(result, "action_class", None),
                "router_output": result.router_output.model_dump(mode="json") if getattr(result, "router_output", None) else None,
                "mechanic_output": result.mechanic_result.model_dump(mode="json") if result.mechanic_result else None,
                "director_instructions": getattr(result, "director_instructions", None),
                "present_npcs": getattr(result, "present_npcs", None),
                "world_sim_events": getattr(result, "world_sim_events", None) or [],
                "new_rumors": getattr(result, "new_rumors", None) or [],
                "active_factions": active_factions,
            }

        state_out = None
        if body.include_state:
            state_out = result.model_dump(mode="json")

        party_status: list[PartyStatusItem] | None = None
        alignment_out: dict | None = None
        faction_reputation_out: dict | None = None
        camp = result.campaign if isinstance(result.campaign, dict) else {}
        if camp:
            party_ids = camp.get("party") or []
            if party_ids:
                party_status = []
                for cid in party_ids:
                    comp = get_companion_by_id(cid)
                    name = comp.get("name", cid) if comp else cid
                    affinity = (camp.get("party_affinity") or {}).get(cid, 0)
                    loyalty = (camp.get("loyalty_progress") or {}).get(cid, 0)
                    mood_tag = affinity_to_mood_tag(affinity)
                    party_status.append(
                        PartyStatusItem(id=cid, name=name, affinity=affinity, loyalty_progress=loyalty, mood_tag=mood_tag)
                    )
                ws = camp.get("world_state_json")
                if isinstance(ws, str):
                    try:
                        ws = json.loads(ws)
                    except (json.JSONDecodeError, TypeError, ValueError):
                        ws = {}
                ps_raw = (ws or {}).get("party_state") if isinstance(ws, dict) else None
                if ps_raw and isinstance(ps_raw, dict):
                    cs_map = ps_raw.get("companion_states") or {}
                    for item in party_status:
                        cs = cs_map.get(item.id)
                        if cs and isinstance(cs, dict):
                            item.influence = cs.get("influence", 0)
                            item.trust = cs.get("trust", 0)
                            item.respect = cs.get("respect", 0)
                            item.fear = cs.get("fear", 0)
            aln = camp.get("alignment")
            if isinstance(aln, dict):
                alignment_out = {"light_dark": aln.get("light_dark", 0), "paragon_renegade": aln.get("paragon_renegade", 0)}
            fr = camp.get("faction_reputation")
            if isinstance(fr, dict) and fr:
                faction_reputation_out = dict(fr)

        news_feed_out = None
        if camp:
            nf = camp.get("news_feed")
            if isinstance(nf, list) and nf:
                news_feed_out = [item if isinstance(item, dict) else getattr(item, "model_dump", lambda **kw: item)(mode="json") for item in nf[:NEWS_FEED_MAX]]

        context_stats_out = None
        agent_timings_out = None
        token_usage_out = None
        if DEV_CONTEXT_STATS and result.context_stats:
            context_stats_out = result.context_stats
        if DEV_CONTEXT_STATS:
            merged_timings = {}
            if getattr(result, "agent_timings", None):
                merged_timings.update(result.agent_timings or {})
            if getattr(result, "llm_timings", None):
                merged_timings["llm"] = result.llm_timings
            if merged_timings:
                agent_timings_out = merged_timings
            if getattr(result, "token_usage", None):
                token_usage_out = result.token_usage
        warnings_out = getattr(result, "warnings", None) or []

        camp_live = load_campaign(conn, campaign_id) or {}
        beats_remaining, scene_transition_note, force_scene_transition = _decrement_beats(conn, campaign_id, camp_live)
        ws_live = _world_state_dict(camp_live)
        mode = str(ws_live.get("mode") or "SIM").upper()
        ledger_facts, immutable_facts = get_facts_with_meta(conn, campaign_id)
        setting_rules_live = ws_live.get("setting_rules") if isinstance(ws_live.get("setting_rules"), dict) else {}
        historical_label = str((setting_rules_live or {}).get("historical_lore_label") or "established lore")
        objectives = _active_objectives(conn, campaign_id)
        if not objectives:
            _seed_default_objective(conn, campaign_id)
            objectives = _active_objectives(conn, campaign_id)
        if scene_transition_note:
            warnings_out.append(scene_transition_note)
        turn_contract = build_turn_contract(
            mode=mode if mode in {"SIM", "PASSAGE", "HYBRID"} else "SIM",
            campaign_id=campaign_id,
            turn_id=f"{campaign_id}_t{state.turn_number + 1}",
            display_text=result.final_text or "",
            scene_goal=((getattr(result, "scene_frame", None) or {}).get("player_objective") if isinstance(getattr(result, "scene_frame", None), dict) else "Advance the current objective"),
            obstacle=((getattr(result, "scene_frame", None) or {}).get("immediate_situation") if isinstance(getattr(result, "scene_frame", None), dict) else "Escalating opposition"),
            stakes="Mission momentum, faction trust, and party safety.",
            mechanic_result=result.mechanic_result,
            suggested_actions=suggested_actions,
            meta=TurnMeta(
                scene_id=ws_live.get("scene_id"),
                beats_remaining=beats_remaining,
                active_objectives=objectives,
                alignment=alignment_out or None,
                reputations=faction_reputation_out or None,
                passage_id=ws_live.get("current_passage_id"),
                prompt_versions=prompt_registry_snapshot(),
            ),
            ledger_facts=ledger_facts,
            immutable_facts=immutable_facts,
            historical_lore_label=historical_label,
            has_companions=bool((camp or {}).get("party")),
            force_scene_transition=force_scene_transition,
        )
        if turn_contract.state_delta.facts_upsert:
            upsert_facts(conn, campaign_id, turn_contract.turn_id, turn_contract.state_delta.facts_upsert)
        if turn_contract.debug and turn_contract.debug.validation_errors:
            record_event(conn, campaign_id, turn_contract.turn_id, {
                "event_type": "turn_contract_validation_failure",
                "errors": turn_contract.debug.validation_errors,
                "repair_count": turn_contract.debug.repair_count,
            })
        conn.commit()

        logger.info(
            "turn_complete node=post_turn request_id=%s campaign_id=%s turn_id=%s latency_ms=%s validation_errors=%s repair_count=%s",
            request_id, campaign_id, turn_contract.turn_id,
            int((time.perf_counter() - start_ts) * 1000),
            len((turn_contract.debug.validation_errors if turn_contract.debug else [])),
            (turn_contract.debug.repair_count if turn_contract.debug else 0),
        )

        consequence_type_out: str | None = None
        mr = result.mechanic_result
        if mr is not None:
            consequence_type_out = getattr(mr, "consequence_type", None) or (
                mr.get("consequence_type") if isinstance(mr, dict) else None
            )

        mechanic_notes_out: dict | None = None
        if mr is not None:
            _mr_dict = mr if isinstance(mr, dict) else (mr.model_dump(mode="json") if hasattr(mr, "model_dump") else {})
            if _mr_dict.get("action_type") and _mr_dict["action_type"] != "IDLE":
                mechanic_notes_out = {
                    "action_type": _mr_dict.get("action_type"),
                    "dice_result": _mr_dict.get("dice_result"),
                    "difficulty": _mr_dict.get("difficulty"),
                    "success": _mr_dict.get("success"),
                    "outcome_summary": _mr_dict.get("outcome_summary"),
                    "critical_outcome": _mr_dict.get("critical_outcome"),
                }

        active_npc_contexts_out: list[dict] | None = None
        try:
            scene_frame_raw = getattr(result, "scene_frame", None) or {}
            present_npcs_raw = scene_frame_raw.get("present_npcs") or [] if isinstance(scene_frame_raw, dict) else []
            if present_npcs_raw:
                ws_for_npc = camp.get("world_state_json") if camp else None
                if isinstance(ws_for_npc, str):
                    try:
                        ws_for_npc = json.loads(ws_for_npc)
                    except Exception:
                        ws_for_npc = {}
                npc_states_map = (ws_for_npc or {}).get("npc_states") or {} if isinstance(ws_for_npc, dict) else {}
                npc_contexts = []
                for npc_ref in present_npcs_raw:
                    if not isinstance(npc_ref, dict):
                        continue
                    npc_id = npc_ref.get("id") or ""
                    npc_name = npc_ref.get("name") or npc_id
                    npc_state = npc_states_map.get(npc_id) or npc_states_map.get(npc_name) or {}
                    npc_contexts.append({
                        "id": npc_id, "name": npc_name,
                        "role": npc_ref.get("role") or "",
                        "emotional_state": npc_state.get("emotional_state") or "",
                        "agenda": npc_state.get("agenda") or "",
                        "next_move": npc_state.get("next_move") or "",
                    })
                if npc_contexts:
                    active_npc_contexts_out = npc_contexts
        except Exception:
            pass

        if party_status and camp:
            try:
                ws_spoken = camp.get("world_state_json")
                if isinstance(ws_spoken, str):
                    try:
                        ws_spoken = json.loads(ws_spoken)
                    except Exception:
                        ws_spoken = {}
                spoken_map = (ws_spoken or {}).get("companion_spoken_reactions") or {} if isinstance(ws_spoken, dict) else {}
                if spoken_map:
                    for item in party_status:
                        item.spoken_reaction = spoken_map.get(item.id) or spoken_map.get(item.name)
            except Exception:
                pass

        response_payload = TurnResponse(
            narrated_text=result.final_text or "",
            suggested_actions=suggested_actions,
            player_sheet=player_sheet,
            inventory=inventory,
            quest_log=quest_log or {},
            world_time_minutes=world_time_minutes,
            canonical_year_label=canonical_year_label,
            state=state_out,
            debug=debug_out,
            party_status=party_status,
            alignment=alignment_out,
            faction_reputation=faction_reputation_out,
            news_feed=news_feed_out,
            context_stats=context_stats_out,
            agent_timings=agent_timings_out,
            token_usage=token_usage_out,
            warnings=warnings_out,
            dialogue_turn=getattr(result, "dialogue_turn", None),
            turn_contract=turn_contract,
            consequence_type=consequence_type_out,
            active_npc_contexts=active_npc_contexts_out,
            world_sim_ran=bool(getattr(result, "world_sim_ran", False)),
            mechanic_notes=mechanic_notes_out,
            bridge_paragraph=getattr(result, "bridge_paragraph", None),
            arc_stage=(getattr(result, "arc_guidance", None) or {}).get("arc_stage"),
            current_arc_number=(getattr(result, "arc_guidance", None) or {}).get("current_arc_number"),
            current_arc_id=(getattr(result, "arc_guidance", None) or {}).get("current_arc_id"),
            campaign_complete=bool((getattr(result, "arc_guidance", None) or {}).get("campaign_complete", False)),
            epilogue_active=bool((getattr(result, "arc_guidance", None) or {}).get("epilogue_active", False)),
        )
        if idempotency_key:
            _idempotency_complete(
                conn=conn, campaign_id=campaign_id, player_id=player_id,
                endpoint=endpoint_key, idempotency_key=idempotency_key,
                payload=response_payload.model_dump(mode="json"),
            )
            idempotency_completed = True
        return response_payload
    except HTTPException:
        raise
    except Exception as e:
        log_error_with_context(
            error=e, node_name="turn", campaign_id=campaign_id,
            turn_number=None, agent_name="post_turn",
            extra_context={"player_id": player_id},
        )
        raise
    finally:
        if idempotency_key and idempotency_started and not idempotency_completed:
            try:
                conn.execute(
                    """DELETE FROM turn_idempotency
                       WHERE campaign_id = ? AND player_id = ? AND endpoint = ? AND idempotency_key = ? AND status = 'processing'""",
                    (campaign_id, player_id, endpoint_key, idempotency_key),
                )
                conn.commit()
            except Exception:
                pass
        if turn_lock_acquired:
            turn_lock_ctx.__exit__(None, None, None)
        conn.close()


# ── Streaming narrator endpoint (SSE) ────────────────────────────────

def _run_pre_narrator_pipeline(conn, state: GameState) -> dict:
    """Run pipeline nodes up to (but not including) Narrator."""
    from backend.app.core.nodes import state_to_dict
    from backend.app.core.nodes.router import router_node
    from backend.app.core.graph import get_pre_narrator_steps

    s = state_to_dict(state)
    s["__runtime_conn"] = conn
    s = router_node(s)
    if s.get("intent") == "META":
        return s
    for _name, fn in get_pre_narrator_steps(s.get("intent", "ACTION")):
        s = fn(s)
    return s


def _run_post_narrator_pipeline(conn, state_dict: dict, final_text: str, lore_citations: list) -> dict:
    """Run narrative validation + choice crafting + commit after streaming completes."""
    from backend.app.core.graph import get_post_narrator_steps

    state_dict["final_text"] = final_text
    state_dict["lore_citations"] = lore_citations
    for _name, fn in get_post_narrator_steps():
        state_dict = fn(state_dict)
    return state_dict


@router.post("/campaigns/{campaign_id}/turn_stream")
def post_turn_stream(
    campaign_id: str,
    player_id: str = Query(..., description="Player character ID"),
    request: Request = None,
    body: TurnRequest | None = None,
):
    """Stream narration via Server-Sent Events."""
    if body is None:
        body = TurnRequest(user_input="")
    _validate_turn_input_limits(body)

    conn = _get_conn()
    start_ts = time.perf_counter()
    request_id = getattr(request.state, "request_id", "unknown") if request is not None else "unknown"
    endpoint_key = "turn_stream"
    idempotency_key = _resolve_idempotency_key(request, body)
    request_hash = _turn_request_hash(body) if idempotency_key else ""

    try:
        _ensure_campaign_and_player(conn, campaign_id, player_id)
    except HTTPException:
        conn.close()
        raise

    def event_stream():
        idempotency_started = False
        idempotency_completed = False
        turn_lock_ctx = _campaign_turn_lock(campaign_id)
        turn_lock_acquired = False
        try:
            turn_lock_ctx.__enter__()
            turn_lock_acquired = True
            from backend.app.core.nodes import dict_to_state
            from backend.app.core.agents.narrator import (
                _strip_structural_artifacts,
                _strip_embedded_suggestions,
                _truncate_overlong_prose,
                _enforce_pov_consistency,
            )
            from backend.app.core.agents.narrator_postprocess import get_word_limit_for_scene_weight
            from backend.app.core.agents import NarratorAgent
            from backend.app.core.agents.base import AgentLLM
            from backend.app.core.nodes.narrator import _is_high_stakes_combat
            from backend.app.rag.kg_retriever import KGRetriever

            if idempotency_key:
                cached_payload = _idempotency_lookup(
                    conn=conn, campaign_id=campaign_id, player_id=player_id,
                    endpoint=endpoint_key, idempotency_key=idempotency_key, request_hash=request_hash,
                )
                if cached_payload:
                    done_cached = dict(cached_payload)
                    done_cached.setdefault("type", "done")
                    done_cached.setdefault("request_id", request_id)
                    yield f"data: {json.dumps(done_cached)}\n\n"
                    return
                _idempotency_begin(
                    conn=conn, campaign_id=campaign_id, player_id=player_id,
                    endpoint=endpoint_key, idempotency_key=idempotency_key, request_hash=request_hash,
                )
                idempotency_started = True

            state = build_initial_gamestate(conn, campaign_id, player_id)
            _inject_truth_constraints_into_state(conn, campaign_id, state)
            if body.intent is not None:
                state.user_input = body.intent.user_utterance or json.dumps(body.intent.model_dump(mode="json"))
            else:
                state.user_input = body.user_input
            if body.structured_intent is not None:
                state.structured_intent = body.structured_intent.model_dump(mode="json")

            pre_state = _run_pre_narrator_pipeline(conn, state)

            if pre_state.get("intent") == "META":
                from backend.app.core.nodes.router import meta_node
                from backend.app.core.nodes.commit import make_commit_node
                pre_state = meta_node(pre_state)
                commit_fn = make_commit_node()
                result_dict = commit_fn(pre_state)
                result_dict.pop("__runtime_conn", None)
                result_gs = dict_to_state(result_dict)
                raw_actions = result_gs.suggested_actions or []
                suggested_actions = _pad_suggestions_for_ui(raw_actions)
                meta_done = {
                    "type": "done",
                    "request_id": request_id,
                    "narrated_text": result_gs.final_text or "",
                    "suggested_actions": [
                        a.model_dump(mode="json") if hasattr(a, "model_dump") else a
                        for a in suggested_actions
                    ],
                }
                if idempotency_key:
                    replay_payload = dict(meta_done)
                    replay_payload.pop("type", None)
                    _idempotency_complete(
                        conn=conn, campaign_id=campaign_id, player_id=player_id,
                        endpoint=endpoint_key, idempotency_key=idempotency_key, payload=replay_payload,
                    )
                    idempotency_completed = True
                yield f"data: {json.dumps(meta_done)}\n\n"
                return

            gs = dict_to_state(pre_state)

            shared_char_ctx = pre_state.get("shared_kg_character_context", "")
            shared_event_ctx = pre_state.get("shared_kg_relevant_events", "")
            shared_mem_block = pre_state.get("shared_episodic_memories", "")
            kg_retriever = KGRetriever()

            if shared_char_ctx or shared_event_ctx:
                campaign_dict = getattr(gs, "campaign", None) or {}
                era = (campaign_dict.get("time_period") or campaign_dict.get("era") or "rebellion").strip() or "rebellion"
                loc_ctx = kg_retriever.get_location_context(gs.current_location or "", era)
                kg_parts = [p for p in [shared_char_ctx, loc_ctx, shared_event_ctx] if p]
                kg_context = "## Knowledge Graph Context\n" + "\n\n".join(kg_parts) if kg_parts else ""
            else:
                kg_context = kg_retriever.get_context_for_narrator(gs)

            if shared_mem_block:
                kg_context = (kg_context + "\n\n" + shared_mem_block) if kg_context else shared_mem_block
            else:
                try:
                    from backend.app.core.episodic_memory import EpisodicMemory
                    epi = EpisodicMemory(conn, gs.campaign_id or "")
                    query_text = (gs.user_input or "") + " " + (gs.current_location or "")
                    npc_names = [n.get("name", "") for n in (gs.present_npcs or []) if n.get("name")]
                    memories = epi.recall(
                        query_text=query_text, current_turn=int(gs.turn_number or 0),
                        location_id=gs.current_location, npcs=npc_names, max_results=4,
                    )
                    mem_block = epi.format_for_prompt(memories, max_chars=500)
                    if mem_block:
                        kg_context = (kg_context + "\n\n" + mem_block) if kg_context else mem_block
                except Exception:
                    pass

            from backend.app.rag.lore_retriever import retrieve_lore
            from backend.app.rag.retrieval_bundles import NARRATOR_DOC_TYPES, NARRATOR_SECTION_KINDS
            from backend.app.rag.style_retriever import retrieve_style_layered

            def lore_retriever_fn(query, top_k=6, era=None, related_npcs=None):
                return retrieve_lore(query, top_k=top_k, era=era, doc_types=NARRATOR_DOC_TYPES, section_kinds=NARRATOR_SECTION_KINDS, related_npcs=related_npcs)

            voice_retriever_fn = None

            def style_retriever_fn(query, top_k=3, era_id=None, genre=None, archetype=None):
                return retrieve_style_layered(query, top_k=top_k, era_id=era_id, genre=genre, archetype=archetype)

            try:
                narrator_llm = AgentLLM("narrator")
            except Exception:
                logger.warning("Narrator LLM init failed; falling back to None", exc_info=True)
                narrator_llm = None

            narrator = NarratorAgent(
                llm=narrator_llm, lore_retriever=lore_retriever_fn,
                voice_retriever=voice_retriever_fn, style_retriever=style_retriever_fn,
            )

            accumulated = ""
            for token in narrator.generate_stream(gs, kg_context=kg_context):
                accumulated += token
                yield f"data: {json.dumps({'type': 'token', 'text': token})}\n\n"

            yield f"data: {json.dumps({'type': 'narrator_done'})}\n\n"

            final_text = _strip_structural_artifacts(accumulated)
            final_text = _strip_embedded_suggestions(final_text)
            final_text = _enforce_pov_consistency(final_text)
            max_words = get_word_limit_for_scene_weight(
                pre_state.get("scene_weight"), narrator_mode=pre_state.get("narrator_mode"),
            )
            final_text = _truncate_overlong_prose(final_text, max_words=max_words)

            campaign_data = dict(pre_state.get("campaign") or {})
            banter_queue = list(campaign_data.get("banter_queue") or [])
            if banter_queue and not _is_high_stakes_combat(pre_state):
                first = banter_queue[0]
                line = first.get("text", first) if isinstance(first, dict) else first
                if line:
                    clean_line = str(line).strip().strip('"').strip("'").strip()
                    if clean_line:
                        final_text = f"{final_text}\n\n---\n\n*{clean_line}*"
                campaign_data = {**campaign_data, "banter_queue": banter_queue[1:]}
                pre_state["campaign"] = campaign_data

            result_dict = _run_post_narrator_pipeline(conn, pre_state, final_text, [])
            result_dict.pop("__runtime_conn", None)
            result_gs = dict_to_state(result_dict)

            raw_actions = result_gs.suggested_actions or []
            suggested_actions = _pad_suggestions_for_ui(raw_actions)

            camp = load_campaign(conn, campaign_id) or {}
            _ws_sse_raw = camp.get("world_state_json")
            if isinstance(_ws_sse_raw, str):
                try:
                    _ws_sse_raw = json.loads(_ws_sse_raw) if _ws_sse_raw else {}
                except json.JSONDecodeError:
                    _ws_sse_raw = {}
            _ws_sse_raw = _ws_sse_raw if isinstance(_ws_sse_raw, dict) else {}
            quest_log = _ws_sse_raw.get("quest_log") or {}
            player_sheet = result_gs.player.model_dump(mode="json") if result_gs.player else {}
            inventory = (result_gs.player.inventory or []) if result_gs.player else []

            world_time_minutes = None
            if result_gs.campaign and isinstance(result_gs.campaign, dict):
                world_time_minutes = result_gs.campaign.get("world_time_minutes")
            if world_time_minutes is None and camp:
                world_time_minutes = camp.get("world_time_minutes")
            canonical_year_label = canonical_year_label_from_campaign(campaign=result_gs.campaign, world_state=_ws_sse_raw)
            warnings_out = getattr(result_gs, "warnings", None) or []

            beats_remaining, scene_transition_note, force_scene_transition = _decrement_beats(conn, campaign_id, camp)
            ws_live = _world_state_dict(camp)
            objectives = _active_objectives(conn, campaign_id)
            if not objectives:
                _seed_default_objective(conn, campaign_id)
                objectives = _active_objectives(conn, campaign_id)
            if scene_transition_note:
                warnings_out.append(scene_transition_note)
            ledger_facts, immutable_facts = get_facts_with_meta(conn, campaign_id)
            setting_rules_live = ws_live.get("setting_rules") if isinstance(ws_live.get("setting_rules"), dict) else {}
            historical_label = str((setting_rules_live or {}).get("historical_lore_label") or "established lore")

            turn_contract = build_turn_contract(
                mode=str(ws_live.get("mode") or "SIM").upper(),
                campaign_id=campaign_id,
                turn_id=f"{campaign_id}_t{state.turn_number + 1}",
                display_text=final_text,
                scene_goal=((getattr(result_gs, "scene_frame", None) or {}).get("player_objective") if isinstance(getattr(result_gs, "scene_frame", None), dict) else "Advance the current objective"),
                obstacle=((getattr(result_gs, "scene_frame", None) or {}).get("immediate_situation") if isinstance(getattr(result_gs, "scene_frame", None), dict) else "Escalating opposition"),
                stakes="Mission momentum, faction trust, and party safety.",
                mechanic_result=result_gs.mechanic_result,
                suggested_actions=suggested_actions,
                meta=TurnMeta(
                    scene_id=ws_live.get("scene_id"),
                    beats_remaining=beats_remaining,
                    active_objectives=objectives,
                    passage_id=ws_live.get("current_passage_id"),
                    prompt_versions=prompt_registry_snapshot(),
                ),
                ledger_facts=ledger_facts,
                immutable_facts=immutable_facts,
                historical_lore_label=historical_label,
                has_companions=bool((camp or {}).get("party")),
                force_scene_transition=force_scene_transition,
            )
            if turn_contract.debug and turn_contract.debug.validation_errors:
                record_event(conn, campaign_id, turn_contract.turn_id, {
                    "event_type": "turn_contract_validation_failure",
                    "errors": turn_contract.debug.validation_errors,
                    "repair_count": turn_contract.debug.repair_count,
                })
            conn.commit()

            _stream_mr = result_gs.mechanic_result
            _stream_mechanic_notes: dict | None = None
            if _stream_mr is not None:
                _smr = _stream_mr if isinstance(_stream_mr, dict) else (
                    _stream_mr.model_dump(mode="json") if hasattr(_stream_mr, "model_dump") else {}
                )
                if _smr.get("action_type") and _smr["action_type"] != "IDLE":
                    _stream_mechanic_notes = {
                        "action_type": _smr.get("action_type"),
                        "dice_result": _smr.get("dice_result"),
                        "difficulty": _smr.get("difficulty"),
                        "success": _smr.get("success"),
                        "outcome_summary": _smr.get("outcome_summary"),
                        "critical_outcome": _smr.get("critical_outcome"),
                    }

            done_payload = {
                "type": "done",
                "request_id": request_id,
                "narrated_text": final_text,
                "suggested_actions": [
                    a.model_dump(mode="json") if hasattr(a, "model_dump") else a
                    for a in suggested_actions
                ],
                "player_sheet": player_sheet,
                "inventory": inventory,
                "quest_log": quest_log or {},
                "world_time_minutes": world_time_minutes,
                "canonical_year_label": canonical_year_label,
                "warnings": warnings_out,
                "dialogue_turn": getattr(result_gs, "dialogue_turn", None),
                "turn_contract": turn_contract.model_dump(mode="json"),
                "mechanic_notes": _stream_mechanic_notes,
                "bridge_paragraph": getattr(result_gs, "bridge_paragraph", None),
            }
            if DEV_CONTEXT_STATS:
                merged_timings = {}
                if getattr(result_gs, "agent_timings", None):
                    merged_timings.update(result_gs.agent_timings or {})
                if getattr(result_gs, "llm_timings", None):
                    merged_timings["llm"] = result_gs.llm_timings
                if merged_timings:
                    done_payload["agent_timings"] = merged_timings
                if getattr(result_gs, "token_usage", None):
                    done_payload["token_usage"] = result_gs.token_usage
            logger.info(
                "turn_complete node=turn_stream request_id=%s campaign_id=%s turn_id=%s latency_ms=%s validation_errors=%s repair_count=%s",
                request_id, campaign_id, turn_contract.turn_id,
                int((time.perf_counter() - start_ts) * 1000),
                len((turn_contract.debug.validation_errors if turn_contract.debug else [])),
                (turn_contract.debug.repair_count if turn_contract.debug else 0),
            )
            if idempotency_key:
                replay_payload = dict(done_payload)
                replay_payload.pop("type", None)
                _idempotency_complete(
                    conn=conn, campaign_id=campaign_id, player_id=player_id,
                    endpoint=endpoint_key, idempotency_key=idempotency_key, payload=replay_payload,
                )
                idempotency_completed = True
            yield f"data: {json.dumps(done_payload)}\n\n"

        except HTTPException as e:
            yield f"data: {json.dumps({'type': 'error', 'request_id': request_id, 'message': str(e.detail)})}\n\n"
        except Exception as e:
            logger.exception(
                "SSE turn_stream failed node=turn_stream request_id=%s campaign_id=%s latency_ms=%s",
                request_id, campaign_id, int((time.perf_counter() - start_ts) * 1000),
            )
            yield f"data: {json.dumps({'type': 'error', 'request_id': request_id, 'message': f'Stream failed; retrying via non-stream endpoint is recommended. Details: {str(e)[:160]}'})}\n\n"
        finally:
            if idempotency_key and idempotency_started and not idempotency_completed:
                try:
                    conn.execute(
                        """DELETE FROM turn_idempotency
                           WHERE campaign_id = ? AND player_id = ? AND endpoint = ? AND idempotency_key = ? AND status = 'processing'""",
                        (campaign_id, player_id, endpoint_key, idempotency_key),
                    )
                    conn.commit()
                except Exception:
                    pass
            if turn_lock_acquired:
                turn_lock_ctx.__exit__(None, None, None)
            conn.close()

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── Validation failures ──────────────────────────────────────────────

@router.get("/campaigns/{campaign_id}/validation_failures")
def get_validation_failures(
    campaign_id: str,
    limit: int = Query(20, ge=1, le=200),
):
    conn = _get_conn()
    try:
        if load_campaign(conn, campaign_id) is None:
            raise HTTPException(status_code=404, detail="Campaign not found")
        rows = conn.execute(
            """SELECT turn_id, event_json, created_at FROM truth_events
            WHERE campaign_id = ? ORDER BY id DESC LIMIT ?""",
            (campaign_id, limit),
        ).fetchall()
        failures = []
        for r in rows:
            payload = {}
            try:
                payload = json.loads(r["event_json"] or "{}")
            except Exception:
                payload = {}
            if payload.get("event_type") != "turn_contract_validation_failure":
                continue
            failures.append({
                "turn_id": r["turn_id"],
                "created_at": r["created_at"],
                "errors": payload.get("errors") or [],
                "repair_count": int(payload.get("repair_count") or 0),
            })
        return {"campaign_id": campaign_id, "validation_failures": failures}
    finally:
        conn.close()
