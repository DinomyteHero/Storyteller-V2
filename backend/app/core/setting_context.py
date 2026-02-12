"""Helper to extract SettingRules from pipeline state.

Every agent that needs setting-specific text calls ``get_setting_rules(state)``
to avoid hard-coding universe names, species, or factions.  Falls back to
Star Wars Legends defaults when no ``setting_rules`` key exists in state.
"""
from __future__ import annotations

from typing import Any

from backend.app.world.era_pack_models import SettingRules


def get_setting_rules(state: dict[str, Any]) -> SettingRules:
    """Extract SettingRules from pipeline state. Falls back to SW defaults."""
    campaign = state.get("campaign")
    if not isinstance(campaign, dict):
        return SettingRules()
    ws = campaign.get("world_state_json")
    if not isinstance(ws, dict):
        return SettingRules()
    rules_data = ws.get("setting_rules")
    if isinstance(rules_data, dict):
        return SettingRules.model_validate(rules_data)
    return SettingRules()
