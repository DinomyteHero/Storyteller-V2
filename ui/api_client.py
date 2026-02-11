"""HTTP client for Storyteller V2 API (campaigns, turn, transcript, state, world_state)."""
from __future__ import annotations

import json
import os
from typing import Any, Iterator

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

DEFAULT_BASE_URL = os.environ.get("STORYTELLER_API_URL", "http://localhost:8000")


def _client(base_url: str = DEFAULT_BASE_URL, timeout: float = 60.0) -> "httpx.Client":
    if httpx is None:
        raise RuntimeError("httpx required for api_client. pip install httpx")
    return httpx.Client(base_url=base_url.rstrip("/") or DEFAULT_BASE_URL, timeout=timeout)


def create_campaign(
    base_url: str = DEFAULT_BASE_URL,
    title: str = "New Campaign",
    time_period: str | None = None,
    player_name: str = "Player",
    starting_location: str = "loc-tavern",
    player_stats: dict[str, int] | None = None,
    hp_current: int = 10,
) -> dict[str, Any]:
    """POST /v2/campaigns. Returns {campaign_id, player_id}."""
    with _client(base_url) as c:
        r = c.post(
            "/v2/campaigns",
            json={
                "title": title,
                "time_period": time_period,
                "player_name": player_name,
                "starting_location": starting_location,
                "player_stats": player_stats or {},
                "hp_current": hp_current,
            },
        )
        r.raise_for_status()
        return r.json()


def setup_auto(
    base_url: str = DEFAULT_BASE_URL,
    time_period: str | None = None,
    genre: str | None = None,
    themes: list[str] | None = None,
    player_concept: str = "A hero in a vast world",
    starting_location: str | None = None,
    randomize_starting_location: bool = False,
    background_id: str | None = None,
    background_answers: dict | None = None,
    player_gender: str | None = None,
) -> dict[str, Any]:
    """POST /v2/setup/auto. Returns {campaign_id, player_id, skeleton, character_sheet}."""
    with _client(base_url, timeout=180.0) as c:
        payload: dict[str, Any] = {
            "time_period": time_period,
            "genre": genre,
            "themes": themes or [],
            "player_concept": player_concept,
            "randomize_starting_location": bool(randomize_starting_location),
        }
        if starting_location:
            payload["starting_location"] = starting_location
        if background_id:
            payload["background_id"] = background_id
        if background_answers:
            payload["background_answers"] = background_answers
        if player_gender:
            payload["player_gender"] = player_gender
        r = c.post(
            "/v2/setup/auto",
            json=payload,
        )
        r.raise_for_status()
        return r.json()


def get_era_locations(
    era_id: str,
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """GET /v2/era/{era_id}/locations. Returns {era_id, locations}."""
    with _client(base_url) as c:
        r = c.get(f"/v2/era/{era_id}/locations")
        r.raise_for_status()
        return r.json()


def get_era_backgrounds(
    era_id: str,
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """GET /v2/era/{era_id}/backgrounds. Returns {era_id, backgrounds}."""
    with _client(base_url) as c:
        r = c.get(f"/v2/era/{era_id}/backgrounds")
        r.raise_for_status()
        return r.json()


def get_state(
    campaign_id: str,
    player_id: str,
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """GET /v2/campaigns/{id}/state?player_id=... Returns GameState as dict."""
    with _client(base_url) as c:
        r = c.get(
            f"/v2/campaigns/{campaign_id}/state",
            params={"player_id": player_id},
        )
        r.raise_for_status()
        return r.json()


def run_turn(
    campaign_id: str,
    player_id: str,
    user_input: str,
    base_url: str = DEFAULT_BASE_URL,
    debug: bool = False,
    include_state: bool = False,
) -> dict[str, Any]:
    """POST /v2/campaigns/{id}/turn. Returns UI contract: narrated_text, suggested_actions (padded), player_sheet, inventory, quest_log.
    state and debug are optional; include_state=false by default."""
    with _client(base_url, timeout=180.0) as c:
        r = c.post(
            f"/v2/campaigns/{campaign_id}/turn",
            params={"player_id": player_id},
            json={"user_input": user_input, "debug": debug, "include_state": include_state},
        )
        r.raise_for_status()
        return r.json()


def get_transcript(
    campaign_id: str,
    limit: int = 50,
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """GET /v2/campaigns/{id}/transcript?limit=... Returns {campaign_id, turns} (turns desc by turn_number)."""
    with _client(base_url) as c:
        r = c.get(
            f"/v2/campaigns/{campaign_id}/transcript",
            params={"limit": limit},
        )
        r.raise_for_status()
        return r.json()


def get_world_state(
    campaign_id: str,
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """GET /v2/campaigns/{id}/world_state. Returns {campaign_id, world_state}."""
    with _client(base_url) as c:
        r = c.get(f"/v2/campaigns/{campaign_id}/world_state")
        r.raise_for_status()
        return r.json()


def get_rumors(
    campaign_id: str,
    limit: int = 5,
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """GET /v2/campaigns/{id}/rumors?limit=... Returns {campaign_id, rumors} (last N public rumor texts)."""
    with _client(base_url) as c:
        r = c.get(
            f"/v2/campaigns/{campaign_id}/rumors",
            params={"limit": limit},
        )
        r.raise_for_status()
        return r.json()


def run_turn_stream(
    campaign_id: str,
    player_id: str,
    user_input: str,
    base_url: str = DEFAULT_BASE_URL,
) -> Iterator[dict[str, Any]]:
    """POST /v2/campaigns/{id}/turn_stream — SSE streaming endpoint.

    Yields parsed SSE events as dicts:
      - {"type": "token", "text": "..."}
      - {"type": "done", "narrated_text": "...", "suggested_actions": [...], ...}
      - {"type": "error", "message": "..."}
    """
    if httpx is None:
        raise RuntimeError("httpx required for api_client. pip install httpx")

    url = f"{(base_url or DEFAULT_BASE_URL).rstrip('/')}/v2/campaigns/{campaign_id}/turn_stream"
    with httpx.stream(
        "POST",
        url,
        params={"player_id": player_id},
        json={"user_input": user_input},
        timeout=300.0,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            try:
                data = json.loads(line[6:])
                yield data
            except json.JSONDecodeError:
                continue


# ---------------------------------------------------------------------------
# V2.10: Player Profiles & Cross-Campaign Legacy
# ---------------------------------------------------------------------------


def create_player_profile(
    display_name: str,
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """POST /v2/player/profiles. Returns {id, display_name, created_at}."""
    with _client(base_url) as c:
        r = c.post("/v2/player/profiles", json={"display_name": display_name})
        r.raise_for_status()
        return r.json()


def list_player_profiles(
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """GET /v2/player/profiles. Returns {profiles: [{id, display_name, created_at}]}."""
    with _client(base_url) as c:
        r = c.get("/v2/player/profiles")
        r.raise_for_status()
        return r.json()


def get_player_legacy(
    player_profile_id: str,
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """GET /v2/player/{id}/legacy. Returns {player_profile_id, legacy: [...]}."""
    with _client(base_url) as c:
        r = c.get(f"/v2/player/{player_profile_id}/legacy")
        r.raise_for_status()
        return r.json()


def complete_campaign(
    campaign_id: str,
    outcome_summary: str = "",
    character_fate: str = "",
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """POST /v2/campaigns/{id}/complete. Returns {status, legacy_id, campaign_id}."""
    with _client(base_url) as c:
        r = c.post(
            f"/v2/campaigns/{campaign_id}/complete",
            json={"outcome_summary": outcome_summary, "character_fate": character_fate},
        )
        r.raise_for_status()
        return r.json()
