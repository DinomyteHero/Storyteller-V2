"""EraTransitionSceneAgent: generates a 3-5 turn recap/bridge scene between eras (Phase 2.5.4).

Reuses PrologueScreenplayAgent's structure. The transition scene summarises the arc
that just ended and sets up the atmosphere for the next era.

Called by POST /v2/campaigns/{campaign_id}/era_transition.
"""
from __future__ import annotations

import logging
from typing import Any

from backend.app.core.agents.base import AgentLLM
from backend.app.core.json_reliability import call_with_json_reliability
from backend.app.core.error_handling import log_error_with_context
from shared.schemas import PrologueScreenplay, PrologueNpc

logger = logging.getLogger(__name__)


def _build_fallback_transition(
    from_era: str,
    to_era: str,
    transition_bridge: str,
    player_name: str,
    opening_location_id: str,
) -> dict[str, Any]:
    """Deterministic fallback transition scene."""
    return {
        "prologue_title": f"Interlude: {from_era.title()} to {to_era.title()}",
        "opening_location_id": opening_location_id,
        "npc_cast": [
            {
                "name": "A Familiar Face",
                "role": "ally",
                "motivation": "To say farewell or wish the player well",
                "location_id": opening_location_id,
            }
        ],
        "inciting_moment": transition_bridge,
        "opening_narration": (
            f"Time has passed. {player_name}'s story did not end with the last chapter. "
            f"It continues — into a galaxy that has changed, and into challenges yet unimagined."
        ),
        "departure_trigger": "Accept the call of the new era.",
        "tone": "reflective",
        "origin_context": {
            "from_era": from_era,
            "to_era": to_era,
            "transition_type": "era_change",
        },
    }


class EraTransitionSceneAgent:
    """Generates a PrologueScreenplay-shaped transition scene between eras.

    The output is used as a short 3-5 turn interstitial that connects the
    closing arc to the opening of the next era.
    """

    def __init__(self, llm: AgentLLM | None = None) -> None:
        self._llm = llm

    def generate(
        self,
        from_era: str,
        to_era: str,
        arc_consequences: dict[str, Any] | None = None,
        player: dict[str, Any] | None = None,
        setting_rules: Any | None = None,
        transition_bridge: str = "",
        available_locations: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate an era transition scene screenplay.

        Args:
            from_era: The era the campaign is leaving (e.g. "DARK_TIMES").
            to_era: The era the campaign is entering (e.g. "REBELLION").
            arc_consequences: ArcConsequenceTracker snapshot from the closing arc.
            player: Player character dict.
            setting_rules: Optional SettingRules instance.
            transition_bridge: Narrative bridge text from era_transition.py ADJACENT_TRANSITIONS.
            available_locations: Location IDs from the new era pack.
        Returns:
            PrologueScreenplay-shaped dict for the transition scene.
        """
        from backend.app.world.era_pack_models import SettingRules
        sr: SettingRules = (
            setting_rules if isinstance(setting_rules, SettingRules) else SettingRules()
        )

        locs = available_locations or []
        opening_loc = (
            next((l for l in locs if "cantina" in l.lower()), None)
            or (locs[0] if locs else "loc-cantina")
        )
        p = player or {}
        player_name = p.get("name") or "the protagonist"
        consequences = arc_consequences or {}

        def fallback() -> dict[str, Any]:
            return _build_fallback_transition(
                from_era=from_era,
                to_era=to_era,
                transition_bridge=transition_bridge or f"The passage from {from_era} to {to_era}.",
                player_name=player_name,
                opening_location_id=opening_loc,
            )

        # Build context summary for LLM
        dangling = (consequences.get("dangling_hooks") or [])[:3]
        dangling_text = "; ".join(str(h) for h in dangling) or "no unresolved threads"
        major = (consequences.get("major_decisions") or [])[:3]
        major_text = "; ".join(str(d) for d in major) or "no recorded decisions"
        npc_fates = (consequences.get("npc_fates") or [])[:3]
        npc_text = ", ".join(n.get("name", "?") for n in npc_fates if isinstance(n, dict)) or "no notable NPCs"

        system = (
            f"You are {sr.biographer_role}, writing a brief era transition scene for "
            f"a {sr.setting_name} narrative RPG campaign.\n"
            "Output ONLY valid JSON matching this exact structure:\n"
            "{\n"
            '  "prologue_title": "Short chapter title",\n'
            f'  "opening_location_id": "one of: {", ".join(locs[:5] or [opening_loc])}",\n'
            '  "npc_cast": [{"name":"str","role":"str","motivation":"str","location_id":"str or null"}],\n'
            '  "inciting_moment": "The moment that marks the beginning of the new era",\n'
            '  "opening_narration": "2-3 sentences: retrospective + atmosphere of the new era",\n'
            '  "departure_trigger": "What drives the character into the new era",\n'
            '  "tone": "reflective|gritty|hopeful|melancholic|tense",\n'
            '  "origin_context": {"from_era":"str","to_era":"str","transition_type":"era_change"}\n'
            "}\n"
            "Rules:\n"
            "- Acknowledge what was resolved/unresolved from the previous arc\n"
            "- Set up the atmosphere of the new era\n"
            f"- Transition bridge: {transition_bridge or 'Time passes.'}\n"
        )
        user = (
            f"From era: {from_era}\n"
            f"To era: {to_era}\n"
            f"Player: {player_name}\n"
            f"Unresolved threads: {dangling_text}\n"
            f"Major decisions: {major_text}\n"
            f"Notable NPCs: {npc_text}"
        )

        try:
            validated = call_with_json_reliability(
                llm=self._llm,
                role="prologue",  # reuse prologue role
                agent_name="EraTransitionSceneAgent.generate",
                campaign_id=None,
                system_prompt=system,
                user_prompt=user,
                schema_class=PrologueScreenplay,
                fallback_fn=fallback,
            )
            result = (
                validated.model_dump(mode="json")
                if isinstance(validated, PrologueScreenplay)
                else validated
            )
            if locs and result.get("opening_location_id") not in locs:
                result["opening_location_id"] = opening_loc
            return result
        except Exception as e:
            log_error_with_context(
                error=e,
                node_name="era_transition",
                campaign_id=None,
                turn_number=None,
                agent_name="EraTransitionSceneAgent.generate",
                extra_context={"from_era": from_era, "to_era": to_era},
            )
            logger.warning("EraTransitionSceneAgent.generate failed, using fallback: %s", e)
            return fallback()
