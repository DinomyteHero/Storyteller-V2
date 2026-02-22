"""CompanionDeepGenAgent: LLM-powered deep companion data generator.

Generates personal_banter, opinion_triggers, personal_quest, dialogue_samples,
wound, and revelation_stages from basic companion/NPC data.

Three generation tiers:
- Curated: Hand-authored in companions.yaml (depth_tier: deep) -- no agent needed
- Generated: Auto-generated at campaign init for era-pack companions without depth data
- Emergent: Auto-generated at recruitment for NPCs promoted to companions at runtime

Cloud LLM override (recommended for quality):
    STORYTELLER_COMPANION_DEEP_GEN_PROVIDER=anthropic
    STORYTELLER_COMPANION_DEEP_GEN_MODEL=claude-sonnet-4-6
Local fallback: deterministic generation from trait axes.
"""
from __future__ import annotations

import logging
from typing import Any

from backend.app.core.agents.base import AgentLLM
from backend.app.core.json_reliability import call_with_json_reliability
from backend.app.core.error_handling import log_error_with_context
from backend.app.constants import (
    COMPANION_DEEP_GEN_MAX_PER_CAMPAIGN,
    COMPANION_DEEP_GEN_OPINION_TRIGGERS_MAX,
    COMPANION_DEEP_GEN_BANTER_CAP,
    COMPANION_DEEP_GEN_DIALOGUE_CAP,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Trait interpretation helpers
# ---------------------------------------------------------------------------


def _trait_description(traits: dict[str, int]) -> str:
    """Convert numeric trait axes to human-readable personality description."""
    parts = []
    ip = int(traits.get("idealist_pragmatic", 0))
    if ip > 30:
        parts.append("idealistic")
    elif ip < -30:
        parts.append("pragmatic")
    else:
        parts.append("balanced between idealism and pragmatism")

    mr = int(traits.get("merciful_ruthless", 0))
    if mr > 30:
        parts.append("merciful")
    elif mr < -30:
        parts.append("ruthless")
    else:
        parts.append("measured in mercy")

    lr = int(traits.get("lawful_rebellious", 0))
    if lr > 30:
        parts.append("rebellious")
    elif lr < -30:
        parts.append("lawful")
    else:
        parts.append("pragmatic about rules")

    return ", ".join(parts)


def _map_freetext_traits_to_axes(traits: list[str]) -> dict[str, int]:
    """Map free-text NPC trait words to numeric companion trait axes.

    Used when promoting NPCs (which have list[str] traits) to companions
    (which need dict[str, int] trait axes).
    """
    # Keyword → (axis, delta) mapping
    TRAIT_KEYWORDS: dict[str, tuple[str, int]] = {
        "idealistic": ("idealist_pragmatic", 40),
        "noble": ("idealist_pragmatic", 30),
        "heroic": ("idealist_pragmatic", 30),
        "hopeful": ("idealist_pragmatic", 20),
        "determined": ("idealist_pragmatic", 20),
        "pragmatic": ("idealist_pragmatic", -40),
        "shrewd": ("idealist_pragmatic", -30),
        "calculating": ("idealist_pragmatic", -30),
        "resourceful": ("idealist_pragmatic", -20),
        "merciful": ("merciful_ruthless", 40),
        "compassionate": ("merciful_ruthless", 40),
        "kind": ("merciful_ruthless", 30),
        "gentle": ("merciful_ruthless", 20),
        "wise": ("merciful_ruthless", 20),
        "ruthless": ("merciful_ruthless", -40),
        "cruel": ("merciful_ruthless", -40),
        "intimidating": ("merciful_ruthless", -30),
        "efficient": ("merciful_ruthless", -20),
        "rebellious": ("lawful_rebellious", 40),
        "daring": ("lawful_rebellious", 30),
        "reckless": ("lawful_rebellious", 30),
        "witty": ("lawful_rebellious", 20),
        "charming": ("lawful_rebellious", 10),
        "lawful": ("lawful_rebellious", -40),
        "strict": ("lawful_rebellious", -40),
        "honorable": ("lawful_rebellious", -30),
        "loyal": ("lawful_rebellious", -20),
        "cautious": ("lawful_rebellious", -20),
        "observant": ("idealist_pragmatic", -10),
        "curious": ("idealist_pragmatic", 10),
        "deceptive": ("lawful_rebellious", 20),
        "intelligent": ("idealist_pragmatic", -10),
        "eccentric": ("lawful_rebellious", 20),
        "skilled": ("idealist_pragmatic", -10),
        "grumpy": ("merciful_ruthless", -10),
    }
    axes: dict[str, int] = {
        "idealist_pragmatic": 0,
        "merciful_ruthless": 0,
        "lawful_rebellious": 0,
    }
    for trait in traits:
        for keyword, (axis, delta) in TRAIT_KEYWORDS.items():
            if keyword in trait.lower():
                axes[axis] = max(-100, min(100, axes[axis] + delta))
    return axes


# ---------------------------------------------------------------------------
# Deterministic fallback
# ---------------------------------------------------------------------------


def _deterministic_deep_data(companion: dict[str, Any]) -> dict[str, Any]:
    """Generate deterministic fallback deep data when LLM is unavailable."""
    name = companion.get("name", "Unknown")
    archetype = companion.get("archetype", companion.get("role", "traveler"))
    traits = companion.get("traits") or {}
    motivation = companion.get("motivation", "Find their place in the world")
    wound_data = companion.get("wound")

    # Handle both dict traits (companion) and list traits (NPC)
    if isinstance(traits, list):
        traits = _map_freetext_traits_to_axes(traits)

    ip = int(traits.get("idealist_pragmatic", 0))
    mr = int(traits.get("merciful_ruthless", 0))
    lr = int(traits.get("lawful_rebellious", 0))

    # -- Personal banter varies by trait axis --
    if ip > 0:  # Idealistic
        paragon_lines = [
            f"{name} nods with quiet conviction. 'That's the way it should be done.'",
            f"A look of genuine respect crosses {name}'s face.",
        ]
        renegade_lines = [
            f"{name} looks away, jaw tight. The silence speaks volumes.",
            f"'Was that really necessary?' {name}'s voice is carefully neutral.",
        ]
    else:  # Pragmatic
        paragon_lines = [
            f"{name} raises an eyebrow. 'Noble. Let's hope it doesn't get us killed.'",
            f"A flicker of something — respect, maybe — crosses {name}'s face.",
        ]
        renegade_lines = [
            f"{name} gives a curt nod. 'Efficient. I can work with that.'",
            f"'Sometimes the ugly choice is the right one.' {name} sounds almost relieved.",
        ]

    investigate_lines = [
        f"'Smart.' {name} looks thoughtful. 'Knowledge before action.'",
        f"{name} tilts their head, considering. 'I'd have done the same.'",
    ]
    general_lines = [
        f"{name} adjusts their gear absently, eyes scanning the surroundings.",
        f"A distant look crosses {name}'s face — remembering something, perhaps.",
    ]

    # -- Opinion triggers based on traits --
    opinion_triggers: list[dict[str, Any]] = []
    if mr > 0:  # Merciful
        opinion_triggers.append({
            "situation": "player_shows_mercy",
            "reaction": f"{name}'s expression softens. This is who they want to follow.",
            "affinity_bonus": 3,
            "tags": ["mercy", "compassion"],
        })
        opinion_triggers.append({
            "situation": "player_kills_unarmed",
            "reaction": f"{name} turns away. Something has broken between you.",
            "affinity_bonus": -4,
            "tags": ["violence", "cruelty"],
        })
    else:  # Ruthless
        opinion_triggers.append({
            "situation": "player_shows_strength",
            "reaction": f"{name} watches with approval. Strength they can respect.",
            "affinity_bonus": 3,
            "tags": ["strength", "combat"],
        })
        opinion_triggers.append({
            "situation": "player_shows_weakness",
            "reaction": f"Disappointment flickers across {name}'s face.",
            "affinity_bonus": -2,
            "tags": ["weakness", "hesitation"],
        })

    if ip > 0:  # Idealistic
        opinion_triggers.append({
            "situation": "player_helps_innocent",
            "reaction": f"This is why {name} stays. Moments like this.",
            "affinity_bonus": 2,
            "tags": ["protection", "innocent"],
        })
    else:  # Pragmatic
        opinion_triggers.append({
            "situation": "player_makes_deal",
            "reaction": f"{name} nods approvingly. 'Good business.'",
            "affinity_bonus": 2,
            "tags": ["negotiation", "pragmatism"],
        })

    if lr > 0:  # Rebellious
        opinion_triggers.append({
            "situation": "player_defies_authority",
            "reaction": f"A grin — rare and genuine — crosses {name}'s face.",
            "affinity_bonus": 2,
            "tags": ["rebellion", "authority"],
        })
    else:  # Lawful
        opinion_triggers.append({
            "situation": "player_follows_law",
            "reaction": f"{name} gives a small nod of approval. Order matters.",
            "affinity_bonus": 2,
            "tags": ["law", "order"],
        })

    # -- Personal quest from motivation --
    quest = {
        "title": f"{name}'s Reckoning",
        "hook": f"{name} has unfinished business connected to their past as a {archetype}.",
        "trigger_affinity": 40,
        "stages": [
            f"{name} reveals a lead connected to their past",
            f"Travel to investigate what {name} has uncovered",
            f"Confront the truth — it may not be what {name} expected",
        ],
        "resolution_paths": [
            f"Help {name} find closure — their wound begins to heal",
            f"The truth is worse than expected — {name} must choose who they become",
        ],
    }

    # -- Dialogue samples --
    dialogue_samples = [
        {"context": "greeting", "line": f"'Ready when you are.' {name} checks their gear."},
        {"context": "disagreement", "line": f"'I hear you. I just don't agree.' {name}'s voice is level but firm."},
        {"context": "vulnerable", "line": f"'I don't talk about before. Not yet.' {name} looks at their hands."},
        {"context": "combat", "line": f"'Stay sharp. Let's finish this.' {name} moves to position."},
    ]

    result: dict[str, Any] = {
        "personal_banter": {
            "PARAGON": paragon_lines,
            "RENEGADE": renegade_lines,
            "INVESTIGATE": investigate_lines,
            "general": general_lines,
        },
        "opinion_triggers": opinion_triggers,
        "personal_quest": quest,
        "dialogue_samples": dialogue_samples,
    }

    # Only generate wound/revelations if not already present
    if not wound_data:
        result["wound"] = {
            "surface": f"A {archetype} carrying visible weight from their past.",
            "deep": (
                f"Something happened that changed {name} — they don't speak of it, "
                "but it shapes every decision."
            ),
            "core": (
                f"What {name} really wants isn't revenge or justice — it's forgiveness. "
                "From themselves."
            ),
        }
        result["revelation_stages"] = [
            {
                "affinity_threshold": 20,
                "stage": "surface",
                "trigger": (
                    f"A quiet moment — {name} mentions their past for the first time."
                ),
            },
            {
                "affinity_threshold": 40,
                "stage": "deep",
                "trigger": (
                    f"Under stress, the truth slips out. {name} was there when it happened."
                ),
            },
            {
                "affinity_threshold": 60,
                "stage": "core",
                "trigger": (
                    f"After a shared hardship, {name} finally says what they've been carrying."
                ),
            },
        ]

    return result


# ---------------------------------------------------------------------------
# LLM prompt construction
# ---------------------------------------------------------------------------


def _build_system_prompt(
    companion: dict[str, Any],
    setting_context: dict[str, Any],
    needs_wound: bool,
) -> str:
    """Build the system prompt for the deep gen LLM call."""
    setting_desc = ""
    if setting_context:
        setting_desc = (
            "\nSETTING CONTEXT:\n"
            f"  Era: {setting_context.get('era', 'unknown')}\n"
            f"  Genre: {setting_context.get('genre', 'unknown')}\n"
            f"  Tone: {setting_context.get('tone', 'unknown')}\n"
            f"  Setting: {setting_context.get('setting_name', 'unknown')}\n"
        )

    # Build the schema description
    wound_schema = ""
    if needs_wound:
        wound_schema = """
  "wound": {
    "surface": "string -- what the world sees (visible behavior, mask)",
    "deep": "string -- what really happened (the truth beneath)",
    "core": "string -- what they won't admit (the need they're hiding)"
  },
  "revelation_stages": [
    {"affinity_threshold": 20, "stage": "surface", "trigger": "string -- scene description"},
    {"affinity_threshold": 40, "stage": "deep", "trigger": "string -- scene description"},
    {"affinity_threshold": 60, "stage": "core", "trigger": "string -- scene description"}
  ],"""

    wound_instruction = (
        "- Generate wound (3 layers) and revelation_stages (3 thresholds).\n"
        if needs_wound
        else "- DO NOT include wound or revelation_stages (already defined for this character).\n"
    )

    return f"""You are a character psychologist for a narrative RPG engine. Given a character's \
basic profile, generate rich personal depth data that makes them feel real and reactive \
during gameplay.
{setting_desc}
CRITICAL RULES:
- ALL text must be in-character for THIS specific person. No generic reactions.
- Banter lines are 1-2 sentences max, shown as brief companion reactions during gameplay.
- Opinion triggers fire when specific scene situations match their tags.
- The personal quest must connect to the character's wound/motivation.
- Dialogue samples capture the character's unique voice and speech patterns.
- Wound layers: "what everyone sees" -> "what really happened" -> "what they won't admit."
- Revelation stages show HOW the character opens up at trust milestones.
{wound_instruction}
OUTPUT RULES:
- Output ONLY valid JSON matching the schema below. No markdown, no explanation.
- personal_banter: 2 lines per tone (PARAGON, RENEGADE, INVESTIGATE) + 2 general lines.
- opinion_triggers: 4-6 entries with realistic affinity_bonus values (-4 to +4).
- personal_quest: Must have 3 stages and 2 resolution paths.
- dialogue_samples: 4 entries (greeting, disagreement, vulnerable, combat).

JSON SCHEMA:
{{
  "personal_banter": {{
    "PARAGON": ["string -- reaction to heroic/merciful player action", "string"],
    "RENEGADE": ["string -- reaction to aggressive/ruthless player action", "string"],
    "INVESTIGATE": ["string -- reaction to cautious/analytical player action", "string"],
    "general": ["string -- ambient character moment", "string"]
  }},
  "opinion_triggers": [
    {{
      "situation": "string -- lowercase_snake_case (e.g. player_helps_refugees)",
      "reaction": "string -- 1-2 sentence in-character reaction",
      "affinity_bonus": "int -- -4 to +4",
      "tags": ["string -- scene tag for matching"]
    }}
  ],
  "personal_quest": {{
    "title": "string",
    "hook": "string -- what the character reveals at trigger_affinity threshold",
    "trigger_affinity": 40,
    "stages": ["string", "string", "string"],
    "resolution_paths": ["string -- positive outcome", "string -- complex/negative outcome"]
  }},
  "dialogue_samples": [
    {{"context": "greeting", "line": "string"}},
    {{"context": "disagreement", "line": "string"}},
    {{"context": "vulnerable", "line": "string"}},
    {{"context": "combat", "line": "string"}}
  ],{wound_schema}
}}"""


def _build_user_prompt(companion: dict[str, Any]) -> str:
    """Build the user prompt describing the companion to enrich."""
    name = companion.get("name", "Unknown")
    archetype = companion.get("archetype", companion.get("role", "traveler"))
    traits = companion.get("traits") or {}
    motivation = companion.get("motivation", "")
    wound = companion.get("wound")
    voice = companion.get("voice") or {}
    faction_interest = companion.get("faction_interest") or []
    speech_quirk = companion.get("speech_quirk", "")
    banter_style = companion.get("banter_style", "")

    # Build trait description
    if isinstance(traits, dict):
        trait_desc = _trait_description(traits)
    else:
        trait_desc = ", ".join(str(t) for t in traits) if traits else "unspecified"

    parts = [
        "CHARACTER PROFILE:",
        f"  Name: {name}",
        f"  Archetype: {archetype}",
        f"  Personality: {trait_desc}",
        f"  Motivation: {motivation}",
        f"  Banter style: {banter_style or 'unspecified'}",
        f"  Speech quirk: {speech_quirk or 'none'}",
        f"  Faction interests: {', '.join(faction_interest) if faction_interest else 'none'}",
        f"  Voice belief: {voice.get('belief', 'unspecified')}",
        f"  Voice wound: {voice.get('wound', 'unspecified')}",
    ]

    if wound:
        parts.extend([
            "",
            "EXISTING WOUND (preserve this -- generate matching revelations):",
            f"  Surface: {wound.get('surface', '')}",
            f"  Deep: {wound.get('deep', '')}",
            f"  Core: {wound.get('core', '')}",
        ])

    parts.extend([
        "",
        "Generate deep companion data that captures this character's unique personality, "
        "wound psychology, and dramatic potential. Every line should sound like THIS person, "
        "not a generic RPG companion.",
    ])

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# CompanionDeepGenAgent
# ---------------------------------------------------------------------------


class CompanionDeepGenAgent:
    """Generates deep companion tier data from basic companion/NPC info.

    Uses LLM when available, falls back to deterministic generation from traits.
    """

    def __init__(self, llm: AgentLLM | None = None) -> None:
        self._llm = llm

    def generate(
        self,
        companion: dict[str, Any],
        setting_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate deep tier data for a single companion.

        Args:
            companion: Basic companion dict (name, archetype, traits, motivation, etc.)
            setting_context: Optional setting info (era, tone, genre, setting_name)

        Returns:
            Dict with: personal_banter, opinion_triggers, personal_quest,
            dialogue_samples, and optionally wound + revelation_stages.
        """
        ctx = setting_context or {}
        name = companion.get("name", "Unknown")
        needs_wound = not bool(companion.get("wound"))

        def fallback() -> dict[str, Any]:
            return _deterministic_deep_data(companion)

        system = _build_system_prompt(companion, ctx, needs_wound)
        user = _build_user_prompt(companion)

        def validator_fn(data: Any) -> tuple[bool, str]:
            d = (
                data
                if isinstance(data, dict)
                else (
                    data.model_dump(mode="json")
                    if hasattr(data, "model_dump")
                    else {}
                )
            )
            pb = d.get("personal_banter")
            if not isinstance(pb, dict):
                return False, "personal_banter must be a dict"
            for tone in ("PARAGON", "RENEGADE", "INVESTIGATE", "general"):
                if not isinstance(pb.get(tone), list) or len(pb[tone]) < 1:
                    return False, f"personal_banter.{tone} must have at least 1 entry"
            ot = d.get("opinion_triggers")
            if not isinstance(ot, list) or len(ot) < 3:
                return (
                    False,
                    f"Need at least 3 opinion_triggers, got "
                    f"{len(ot) if isinstance(ot, list) else 0}",
                )
            pq = d.get("personal_quest")
            if not isinstance(pq, dict) or not pq.get("title"):
                return False, "personal_quest must have a title"
            ds = d.get("dialogue_samples")
            if not isinstance(ds, list) or len(ds) < 3:
                return (
                    False,
                    f"Need at least 3 dialogue_samples, got "
                    f"{len(ds) if isinstance(ds, list) else 0}",
                )
            return True, ""

        try:
            result = call_with_json_reliability(
                llm=self._llm,
                role="companion_deep_gen",
                agent_name="CompanionDeepGenAgent.generate",
                campaign_id=None,
                system_prompt=system,
                user_prompt=user,
                validator_fn=validator_fn,
                fallback_fn=fallback,
            )
            data = (
                result
                if isinstance(result, dict)
                else (
                    result.model_dump(mode="json")
                    if hasattr(result, "model_dump")
                    else fallback()
                )
            )
            return _normalize_deep_data(data, companion)
        except Exception as e:
            log_error_with_context(
                error=e,
                node_name="companion_deep_gen",
                campaign_id=None,
                turn_number=None,
                agent_name="CompanionDeepGenAgent.generate",
                extra_context={"companion_name": name},
            )
            logger.warning(
                "CompanionDeepGenAgent.generate failed for %s; using fallback.", name
            )
            return fallback()

    def generate_batch(
        self,
        companions: list[dict[str, Any]],
        setting_context: dict[str, Any] | None = None,
        max_count: int | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Generate deep data for multiple companions.

        Args:
            companions: List of companion dicts to enrich
            setting_context: Optional setting info
            max_count: Maximum companions to process (None = use constant)

        Returns:
            Dict mapping companion_id -> deep_data
        """
        limit = max_count or COMPANION_DEEP_GEN_MAX_PER_CAMPAIGN

        results: dict[str, dict[str, Any]] = {}
        for comp in companions[:limit]:
            comp_id = comp.get("id")
            if not comp_id:
                continue
            # Skip companions that already have curated deep tier data
            if str(comp.get("depth_tier", "")).lower() == "deep":
                continue
            try:
                deep_data = self.generate(comp, setting_context)
                results[comp_id] = deep_data
                logger.info(
                    "Generated deep data for companion: %s",
                    comp.get("name", comp_id),
                )
            except Exception as e:
                logger.warning(
                    "Failed to generate deep data for %s: %s", comp_id, e
                )

        return results


# ---------------------------------------------------------------------------
# Normalization / clamping
# ---------------------------------------------------------------------------


def _normalize_deep_data(
    data: dict[str, Any], companion: dict[str, Any]
) -> dict[str, Any]:
    """Normalize and clamp generated deep data to match the expected schema."""
    result: dict[str, Any] = {}

    # Personal banter
    pb = data.get("personal_banter") or {}
    result["personal_banter"] = {
        "PARAGON": [str(s) for s in (pb.get("PARAGON") or []) if s][
            :COMPANION_DEEP_GEN_BANTER_CAP
        ],
        "RENEGADE": [str(s) for s in (pb.get("RENEGADE") or []) if s][
            :COMPANION_DEEP_GEN_BANTER_CAP
        ],
        "INVESTIGATE": [str(s) for s in (pb.get("INVESTIGATE") or []) if s][
            :COMPANION_DEEP_GEN_BANTER_CAP
        ],
        "general": [str(s) for s in (pb.get("general") or []) if s][
            :COMPANION_DEEP_GEN_BANTER_CAP
        ],
    }

    # Opinion triggers
    ot = data.get("opinion_triggers") or []
    result["opinion_triggers"] = []
    for trigger in ot[:COMPANION_DEEP_GEN_OPINION_TRIGGERS_MAX]:
        if not isinstance(trigger, dict):
            continue
        result["opinion_triggers"].append(
            {
                "situation": str(trigger.get("situation", ""))
                .lower()
                .replace(" ", "_")[:50],
                "reaction": str(trigger.get("reaction", ""))[:200],
                "affinity_bonus": max(
                    -5, min(5, int(trigger.get("affinity_bonus", 0)))
                ),
                "tags": [str(t).lower() for t in (trigger.get("tags") or []) if t][
                    :5
                ],
            }
        )

    # Personal quest
    pq = data.get("personal_quest") or {}
    name = companion.get("name", "Unknown")
    result["personal_quest"] = {
        "title": str(pq.get("title", f"{name}'s Quest"))[:80],
        "hook": str(pq.get("hook", ""))[:300],
        "trigger_affinity": max(20, min(80, int(pq.get("trigger_affinity", 40)))),
        "stages": [str(s)[:200] for s in (pq.get("stages") or []) if s][:5],
        "resolution_paths": [
            str(s)[:200] for s in (pq.get("resolution_paths") or []) if s
        ][:3],
    }

    # Dialogue samples
    ds = data.get("dialogue_samples") or []
    result["dialogue_samples"] = []
    for sample in ds[:COMPANION_DEEP_GEN_DIALOGUE_CAP]:
        if not isinstance(sample, dict):
            continue
        result["dialogue_samples"].append(
            {
                "context": str(sample.get("context", "general"))[:30],
                "line": str(sample.get("line", ""))[:200],
            }
        )

    # Wound (optional -- only if generated, not if companion already has one)
    if "wound" in data and isinstance(data["wound"], dict):
        result["wound"] = {
            "surface": str(data["wound"].get("surface", ""))[:300],
            "deep": str(data["wound"].get("deep", ""))[:300],
            "core": str(data["wound"].get("core", ""))[:300],
        }

    # Revelation stages (optional -- only if generated)
    if "revelation_stages" in data and isinstance(data["revelation_stages"], list):
        result["revelation_stages"] = []
        for rs in data["revelation_stages"][:3]:
            if not isinstance(rs, dict):
                continue
            result["revelation_stages"].append(
                {
                    "affinity_threshold": int(rs.get("affinity_threshold", 20)),
                    "stage": str(rs.get("stage", "surface")),
                    "trigger": str(rs.get("trigger", ""))[:200],
                }
            )

    return result
