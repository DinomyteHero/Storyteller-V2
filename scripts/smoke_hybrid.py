"""Smoke test: create hybrid campaign, start passage, pick first choice for 3 turns."""
from __future__ import annotations

import requests

BASE = "http://localhost:8000"


def main() -> None:
    create = requests.post(
        f"{BASE}/v2/campaigns",
        json={"title": "Smoke Hybrid", "time_period": "REBELLION", "player_name": "Smoke", "starting_location": "loc-cantina"},
        timeout=30,
    )
    create.raise_for_status()
    payload = create.json()
    campaign_id = payload["campaign_id"]

    start = requests.post(
        f"{BASE}/v2/campaigns/{campaign_id}/start_passage",
        json={"pack_id": "rebellion", "mode": "HYBRID"},
        timeout=30,
    )
    start.raise_for_status()
    current = start.json()
    print(current.get("display_text", ""))

    for i in range(3):
        choices = current.get("choices") or current.get("turn_contract", {}).get("choices") or []
        if not choices:
            break
        choice_id = choices[0]["id"]
        nxt = requests.post(f"{BASE}/v2/campaigns/{campaign_id}/choose", json={"choice_id": choice_id}, timeout=30)
        nxt.raise_for_status()
        current = nxt.json()
        tc = current.get("turn_contract", {})
        print(f"Turn {i+1}: {tc.get('display_text', '')[:100]}")
        print("Choices:", [c.get("label") for c in tc.get("choices", [])])
        print("Outcome:", (tc.get("outcome") or {}).get("category"))


if __name__ == "__main__":
    main()
