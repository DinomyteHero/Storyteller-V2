"""Deterministic NPC personality profile builder.

Transforms existing NPC data (voice_tags, traits, archetype, motivation) into
structured prompt blocks for Director and Narrator context injection.

No LLM calls — pure Python string assembly from constant mappings.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Voice tag → speech pattern description
# ---------------------------------------------------------------------------
VOICE_TAG_SPEECH_PATTERNS: dict[str, str] = {
    # Emotional registers
    "earnest": "Speaks plainly and sincerely. Asks questions. Doesn't hide feelings.",
    "hopeful": "Voice lifts when talking about the future. Believes things can improve.",
    "warm": "Gentle tone. Uses encouraging words. Comfortable with silence.",
    "weary": "Heavy sighs. Short responses. Sounds tired of fighting.",
    "nervous": "Stammers. Over-explains. Fills silences. Voice rises under pressure.",
    "defensive": "Quick to justify. Deflects with counter-questions. Guards personal details.",
    "apologetic": "Softens statements. Hedges opinions. Over-qualifies everything.",

    # Authority registers
    "commanding": "Declarative statements. Expects compliance. Rarely asks — orders.",
    "authoritative": "Speaks with weight and finality. Pauses after key points.",
    "regal": "Precise diction. Measured cadence. Never vulgar. Every word chosen.",
    "formal": "Proper grammar. No contractions. Addresses others by title.",
    "diplomatic": "Careful phrasing. Acknowledges all sides. Avoids absolutes.",

    # Humor/wit registers
    "sarcastic": "Uses deflecting humor. Short sentences. Avoids emotional honesty.",
    "wry": "Dry observations. Understatement. Favors contractions and spacer slang.",
    "snarky": "Quick retorts. Finds the absurd angle. Laughs at danger.",
    "dry": "Deadpan delivery. Says more with less. Lets silences do the work.",

    # Intensity registers
    "menacing": "Low, deliberate voice. Lets threats hang in the air. Never raises volume.",
    "cold": "Emotionally flat. Clinical word choice. Treats people like variables.",
    "icy": "Cutting precision. Quiet contempt. Makes warmth feel like weakness.",
    "fierce": "Sharp and direct. Challenges instantly. Voice carries physical intensity.",
    "passionate": "Volume rises with conviction. Gestures while speaking. Emotional crescendos.",

    # Tempo/delivery registers
    "fast": "Rapid-fire delivery. Jumps between topics. Thinks out loud.",
    "measured": "Deliberate pacing. Weighs each word. Never rushed.",
    "deliberate": "Slow, precise delivery. Each sentence carefully constructed.",
    "clipped": "Short, sharp sentences. No wasted words. Military precision.",
    "terse": "Minimal words. Communicates in fragments. Silence is the default.",

    # Character-specific registers
    "growling": "Communicates through tone and gesture. Few words, much meaning.",
    "mechanical": "Filtered or modulated voice. Rhythm is inhuman. Pauses feel calculated.",
    "rasping": "Rough, strained voice. Every word costs effort. Speaks only when necessary.",
    "hissing": "Whispered menace. Sibilant emphasis. Voice slides between words.",
    "deep": "Resonant bass. Words carry physical weight. Gravitas in every syllable.",
    "smooth": "Velvet tone. Every word polished. Charm is a weapon.",
    "serene": "Unshakeable calm. Speaks as if from a great distance. Meditative rhythm.",
    "mystical": "Speaks in metaphor and riddle. Pauses for effect. References the unseen.",
    "expressive": "Voice mirrors emotion. Tone shifts constantly. Transparent feelings.",

    # Intelligence registers
    "calculating": "Precise language. Evaluates before speaking. Reveals nothing by accident.",
    "analytical": "Breaks problems into components. Uses data and evidence. Emotionally detached.",
    "academic": "References theory and history. Qualifies statements. Enjoys complexity.",
    "tactical": "Speaks in objectives and contingencies. Maps conversations like battlefields.",
    "professional": "Competent and composed. Sticks to facts. Minimal personal disclosure.",

    # Authenticity registers
    "young": "Vocal uncertainty mixed with enthusiasm. Still finding their voice.",
    "grave": "Weight of responsibility in every word. Speaks as someone who has buried friends.",
    "uncertain": "Hesitant. Qualifies everything. Seeks reassurance from others.",
    "disdainful": "Barely conceals contempt. Speaks down. Treats others as beneath notice.",
    "clear": "Crystal-sharp enunciation. Confident without arrogance. Voice cuts through noise.",
    "gravelly": "Rough-edged. Battle-worn voice. Speaks from hard experience.",
    "gruff": "Blunt and rough. Says what needs saying without polish.",
    "beeps": "Communicates through electronic tones and sequences. Meaning conveyed by context.",

    # Ethical registers
    "wise": "Speaks from experience. Offers perspective rather than answers. Patient.",

    # Extended registers (V3.0) — covers era-pack companion voice diversity
    # Determination & drive
    "determined": "Unwavering tone. Pushes through objections. Voice hardens under pressure.",
    "driven": "Focused intensity. Steers every conversation toward the goal.",
    "resolute": "Once decided, immovable. Voice carries the weight of commitment.",
    "relentless": "Never lets go of a thread. Circles back. Persistence in every syllable.",
    "ambitious": "Eyes on the prize. Frames everything in terms of opportunity and advancement.",
    "disciplined": "Controlled cadence. Never wastes words. Follows internal protocol.",

    # Emotional depth
    "haunted": "Pauses mid-sentence. Eyes go distant. Past bleeds into present speech.",
    "traumatized": "Flinches at certain words. Voice drops to whisper at triggers.",
    "conflicted": "Contradicts self. Starts sentences over. Wrestles aloud with decisions.",
    "scared": "Voice trembles. Speaks too fast or too slow. Seeks reassurance constantly.",
    "frightened": "Breath catches. Words tumble out. Fight-or-flight colors every phrase.",
    "bitter": "Acid undertone. Past grievances flavor every observation.",
    "desperate": "Urgency overrides composure. Pleads between the lines.",
    "gentle": "Soft volume. Careful word choice. Never wants to cause harm with speech.",
    "calm": "Even tempo regardless of chaos. Unruffled. Steadying presence.",
    "bright": "Upbeat energy. Finds the positive angle. Voice lifts others.",

    # Intellect & precision
    "precise": "Exact word choice. Corrects imprecision in others. Values accuracy.",
    "scholarly": "References texts and precedents. Academic cadence. Enjoys nuance.",
    "enthusiastic": "Lights up at discoveries. Voice rises with excitement. Infectious curiosity.",
    "curious": "Asks probing questions. Genuinely interested. Follows tangents willingly.",
    "knowing": "Implies awareness of secrets. Speaks as if already knowing the answer.",

    # Social style
    "polished": "Rehearsed smoothness. Every interaction feels curated. Diplomatic veneer.",
    "quiet": "Speaks softly and rarely. When they talk, people lean in to listen.",
    "reserved": "Holds back. Reveals little. Watches more than participates.",
    "guarded": "Careful about what slips out. Tests trust before sharing.",
    "humble": "Deflects praise. Credits others. Uncomfortable in the spotlight.",
    "alert": "Hyperaware. Comments on surroundings. Notices things others miss.",
    "watchful": "Observes before engaging. Reads people before speaking to them.",
    "amused": "Finds humor in situations. Light tone. Smiles audibly.",

    # Physical/cultural voice
    "rough": "Unpolished diction. Spacer slang. Sounds like they grew up on docking bays.",
    "direct": "No preamble. States the point. Impatient with circumlocution.",
    "flat": "Monotone delivery. Emotion suppressed or absent. Clinical detachment.",
    "guttural": "Deep, rumbling speech. Words shaped by alien physiology.",
    "ritual": "Speaks in formal patterns. References tradition and ceremony.",
    "ancient": "Cadence of ages. Pauses as if remembering millennia. Weight of deep time.",
    "cryptic": "Speaks in riddles and implications. Meaning always layered beneath words.",

    # Military & tactical
    "military": "Rank-and-file cadence. Reports facts. Awaits orders. Crisp diction.",
    "strategic": "Thinks in moves and countermoves. Frames situations as campaigns.",
    "practical": "Focused on what works. Dismisses theory. Hands-on problem solver.",

    # Urgency & intensity
    "urgent": "Time pressure in every word. Pushes for immediate action.",
    "intense": "Locks eyes. Leans forward. Every word carries concentrated force.",
    "explosive": "Bursts of volume. Passion erupts suddenly. Calm before the storm.",

    # Street & survival
    "streetwise": "Speaks the language of alleys and cantinas. Knows the angles.",
    "street-smart": "Reads situations fast. Uses slang. Trusts instinct over protocol.",

    # Other voice qualities
    "incisive": "Cuts to the heart of matters. No wasted analysis. Surgical observations.",
    "melodic": "Musical quality to speech. Rises and falls like a song.",
    "stubborn": "Repeats position. Refuses to yield. Digs in verbally.",
    "quick": "Rapid processing. Answers before the question finishes. Impatient.",
    "honest": "Says uncomfortable truths. No sugar-coating. Transparent to a fault.",
    "kind": "Softens hard truths. Leads with empathy. Voice carries genuine care.",
    "proud": "Speaks of heritage and accomplishment. Stands tall in every word.",

    # Specialized registers
    "prophetic": "Speaks of what will be, not what is. Visions color vocabulary.",
    "cutting": "Words designed to wound. Precise emotional targeting. Verbal scalpel.",
    "harsh": "Abrasive delivery. No comfort offered. Truth delivered bluntly.",
    "judgmental": "Weighs and finds wanting. Moral authority assumed. Disapproval radiates.",
    "sad": "Melancholy undertone. Speaks as if mourning something always.",
    "soft": "Barely above a whisper. Intimate. Creates a private space in conversation.",
    "deflecting": "Redirects personal questions. Uses humor or topic changes as shields.",
    "thoughtful": "Long pauses before responding. Considers angles. Values depth over speed.",
    "probing": "Asks the question behind the question. Peels back layers.",
    "cheeky": "Playful irreverence. Pokes at authority. Grins through serious moments.",
    "violent": "Words carry threat of physical force. Language of impact and destruction.",
    "beeping": "Communicates through electronic chirps and whistles. Binary emotion.",

    # Cross-registered (also in TRAIT_BEHAVIOR_MAP — valid as both voice and trait)
    "tired": "Words trail off. Pauses grow longer. Speaks as if carrying heavy weight.",
    "raw": "Unfiltered emotion. Voice cracks. No polish — everything is exposed.",
    "confused": "Sentences start and stop. Questions own statements. Searching for clarity.",
    "powerful": "Voice fills the space. Speaks with absolute certainty. Gravity in every word.",
    "loyal": "References bonds and debts. Stands firm when allies are questioned.",
    "honorable": "Weighs words for fairness. Speaks of duty and respect. Values given word.",
    "cynical": "Sardonic edge. Questions motives. Expects the worst from people.",
    "sharp": "Quick verbal reactions. Catches inconsistencies. Precise and pointed.",
    "cautious": "Hedges statements. Considers risks aloud. Prefers certainty over speed.",
    "principled": "Frames decisions in terms of right and wrong. Holds firm to a code.",

    # Compound voice descriptors (used in era pack companion definitions)
    "tech_jargon": "Speaks in technical terms and acronyms. Comfortable with specifications.",
    "sardonic_wit": "Biting humor delivered with a half-smile. Finds dark amusement in situations.",
}

# ---------------------------------------------------------------------------
# Trait keyword → behavioral description
# ---------------------------------------------------------------------------
TRAIT_BEHAVIOR_MAP: dict[str, str] = {
    # Moral axis
    "idealistic": "Appeals to the greater good. Believes in people's best nature.",
    "principled": "Holds firm to a code. Will sacrifice advantage for integrity.",
    "honorable": "Keeps promises. Treats enemies with respect. Values fair play.",
    "merciful": "Offers second chances. Dislikes unnecessary violence.",
    "ruthless": "No half-measures. Removes obstacles — including people.",
    "cynical": "Questions motives. Expects betrayal. Trusts actions over words.",
    "deceptive": "Lies fluently. Tells people what they want to hear. Multiple agendas.",
    "corrupt": "Exploits power for personal gain. Justifies everything.",

    # Temperament axis
    "brave": "Doesn't back down from threats. Steps forward when others retreat.",
    "fearless": "Acts without hesitation in danger. May not recognize risk.",
    "cautious": "Thinks before acting. Prefers information to impulse.",
    "impulsive": "Acts before thinking. Interrupts. Follows gut instinct.",
    "composed": "Maintains control under pressure. Rarely shows disturbance.",
    "fierce": "Channels emotion into action. Protective rage. Intensity in everything.",
    "patient": "Waits for the right moment. Never rushes. Plays the long game.",
    "volatile": "Mood swings. Unpredictable reactions. Intensity varies wildly.",

    # Social axis
    "charming": "Puts people at ease. Reads the room. Uses warmth strategically.",
    "charismatic": "Natural leader. People follow without being asked. Presence fills a room.",
    "diplomatic": "Navigates conflict through negotiation. Sees all perspectives.",
    "sharp": "Quick mind. Catches lies and inconsistencies. Verbal precision.",
    "manipulative": "Steers conversations toward desired outcomes. Exploits vulnerabilities.",
    "humble": "Downplays achievements. Uncomfortable with praise. Leads by example.",
    "arrogant": "Assumes superiority. Dismisses others' contributions. Expects deference.",
    "cocky": "Overestimates own ability. Challenges authority with a smirk.",

    # Loyalty axis
    "loyal": "Stands by allies even when disadvantageous. Takes offense at betrayal.",
    "protective": "Shields others from harm. Places companions' safety above mission.",
    "independent": "Resists authority. Makes own decisions. Uncomfortable following orders.",
    "rebellious": "Challenges systems. Questions orders. Thrives in defiance.",
    "obedient": "Follows chain of command. Finds comfort in structure.",
    "devoted": "Single-minded loyalty to a cause or person. Sacrifice is expected.",

    # Competence axis
    "brilliant": "Solves complex problems quickly. Sees patterns others miss.",
    "calculating": "Plans several moves ahead. Never acts without considering outcomes.",
    "resolute": "Once decided, immovable. Commitment doesn't waver.",
    "skilled": "Quiet competence. Lets results speak. Professional pride.",
    "cunning": "Uses misdirection and surprise. Thinks around obstacles, not through them.",
    "resourceful": "Improvises solutions from limited options. Thrives in adversity.",
    "powerful": "Overwhelming capability. Restraint is a choice, not a limitation.",
    "implacable": "Cannot be reasoned with or deterred. An unstoppable force.",
    "tenacious": "Never gives up. Outlasts opposition through sheer persistence.",
    "fanatical": "Absolute conviction. No compromise. The cause justifies everything.",
    "pragmatic": "Results over principles. Does what works, not what's ideal.",
    "stoic": "Bears hardship without complaint. Emotions are internal, never displayed.",
    "spiritual": "Guided by faith or the Force. Sees meaning in events others call random.",
    "vengeful": "Remembers wrongs. Plans retribution. Debts must be paid.",
    "secretive": "Reveals nothing voluntarily. Guards information as currency.",
}

# ---------------------------------------------------------------------------
# Archetype keyword → interaction style
# ---------------------------------------------------------------------------
ARCHETYPE_INTERACTION_MAP: dict[str, str] = {
    # Hero archetypes
    "Idealistic hero": "Inspires others. Struggles when ideals meet harsh reality.",
    "Reluctant hero": "Initially refuses calls to action. Comes through in the clutch.",
    "Tragic hero": "Driven by past failure. Seeks redemption through sacrifice.",
    "Chosen one": "Burdened by destiny. Others project expectations they never asked for.",

    # Mentor/guide archetypes
    "Wise mentor": "Teaches through questions, not answers. Patience masks urgency.",
    "Fallen mentor": "Once great, now diminished. Wisdom comes wrapped in regret.",
    "Reluctant teacher": "Resists the role. Teaches by accident through example.",

    # Villain/antagonist archetypes
    "Relentless hunter": "Single-minded. Creates dread through persistence. Never stops.",
    "Calculating schemer": "Moves pieces from the shadows. Victory is inevitable in their mind.",
    "Tragic villain": "Believes they're right. Their fall came from noble intentions corrupted.",
    "Tyrant": "Rules through fear. Sees mercy as weakness. Order above all.",

    # Ally archetypes
    "Loyal protector": "Speaks through actions. Violence is protective, never cruel.",
    "Diplomatic warrior": "Leads through persuasion first, force second.",
    "Reluctant ally": "Helps grudgingly. Trust is earned inch by inch.",
    "Wild card": "Unpredictable loyalty. Might help, might betray — depends on the moment.",

    # Specialist archetypes
    "Smuggler captain": "Talks fast, acts faster. Every situation is a deal to negotiate.",
    "Military commander": "Thinks in terms of assets, positions, and acceptable losses.",
    "Intelligence operative": "Everyone is a potential asset or threat. Trust no one fully.",
    "Scoundrel with a heart": "Pretends not to care. Acts selfishly but does the right thing.",
    "Religious zealot": "Absolute faith. Every event confirms their worldview.",
    "Grizzled veteran": "Seen it all. Nothing surprises them. Dark humor masks deep scars.",
    "Political manipulator": "Information is power. Conversations are chess matches.",
}


def build_personality_block(npc: dict[str, Any]) -> str:
    """Build a personality prompt block from NPC data.

    Accepts an NPC dict from era pack (EraNpcEntry fields) or companion YAML.
    Returns a formatted string block suitable for injection into Director/Narrator prompts.

    Returns empty string if NPC has no usable personality data.
    """
    name = npc.get("name", "Unknown")
    voice_tags: list[str] = npc.get("voice_tags") or []
    traits: list[str] = npc.get("traits") or []
    archetype: str = npc.get("archetype") or ""
    motivation: str = npc.get("motivation") or ""
    speech_quirk: str = npc.get("speech_quirk") or ""
    banter_style: str = npc.get("banter_style") or ""

    # Skip NPCs with no personality data at all
    if not voice_tags and not traits and not archetype and not motivation:
        return ""

    lines: list[str] = [f"[{name.upper()} — Personality]"]

    # Archetype line
    if archetype:
        lines.append(f"Archetype: {archetype}")

    # Voice tags
    if voice_tags:
        lines.append(f"Voice: {', '.join(voice_tags)}")

    # Traits
    if traits:
        lines.append(f"Traits: {', '.join(traits)}")

    # Banter style (from companion YAML)
    if banter_style and banter_style not in ("warm", "stoic", "snarky"):
        # Only add non-generic banter styles as they carry specific meaning
        lines.append(f"Banter style: {banter_style}")

    # Speech pattern — assemble from voice_tags
    speech_parts: list[str] = []
    for tag in voice_tags:
        tag_lower = tag.lower().strip()
        if tag_lower in VOICE_TAG_SPEECH_PATTERNS:
            speech_parts.append(VOICE_TAG_SPEECH_PATTERNS[tag_lower])
    if speech_parts:
        # Take up to 2 speech patterns to keep it concise
        lines.append(f"Speech pattern: {' '.join(speech_parts[:2])}")

    # Behavioral notes — assemble from traits
    behavior_parts: list[str] = []
    for trait in traits:
        trait_lower = trait.lower().strip()
        if trait_lower in TRAIT_BEHAVIOR_MAP:
            behavior_parts.append(TRAIT_BEHAVIOR_MAP[trait_lower])
    if behavior_parts:
        # Take up to 2 behavioral notes
        lines.append(f"Behavior: {' '.join(behavior_parts[:2])}")

    # Archetype interaction style
    if archetype:
        # Try exact match first, then partial match on key words
        interaction = ARCHETYPE_INTERACTION_MAP.get(archetype)
        if not interaction:
            archetype_lower = archetype.lower()
            for key, desc in ARCHETYPE_INTERACTION_MAP.items():
                if key.lower() in archetype_lower or archetype_lower in key.lower():
                    interaction = desc
                    break
        if interaction:
            lines.append(f"Interaction: {interaction}")

    # Speech quirk (from companion YAML — unique verbal tics)
    if speech_quirk:
        lines.append(f"Quirk: {speech_quirk}")

    # Motivation
    if motivation:
        lines.append(f"Drives: {motivation}")

    return "\n".join(lines)


def build_scene_personality_context(
    present_npcs: list[dict[str, Any]],
    era_npc_lookup: dict[str, dict[str, Any]] | None = None,
    companion_lookup: dict[str, dict[str, Any]] | None = None,
    companion_state_lookup: dict[str, dict[str, Any]] | None = None,
    max_npcs: int = 4,
) -> str:
    """Build combined personality context for all NPCs in a scene.

    Args:
        present_npcs: List of NPC dicts from game state (name, role, etc.)
        era_npc_lookup: Optional dict mapping NPC id/name to era pack NPC data
        companion_lookup: Optional dict mapping companion id/name to companion YAML data
        max_npcs: Maximum number of NPCs to include (token budget constraint)

    Returns:
        Combined personality blocks string, or empty string if no data.
    """
    blocks: list[str] = []

    for npc in present_npcs[:max_npcs]:
        npc_id = npc.get("id", "") or npc.get("character_id", "")
        npc_name = npc.get("name", "")

        # Try to find rich personality data from era pack or companion lookup
        rich_data: dict[str, Any] | None = None

        if era_npc_lookup:
            rich_data = era_npc_lookup.get(npc_id) or era_npc_lookup.get(npc_name)

        if not rich_data and companion_lookup:
            rich_data = companion_lookup.get(npc_id) or companion_lookup.get(npc_name)

        if rich_data:
            # Merge rich data with present_npc state (name, role from state take priority)
            merged = {**rich_data}
            if npc_name:
                merged["name"] = npc_name
            block = build_personality_block(merged)
        else:
            # Fall back to whatever personality data is on the NPC state dict itself
            block = build_personality_block(npc)

        if block:
            state_data = {}
            if companion_state_lookup:
                state_data = (
                    companion_state_lookup.get(npc_id)
                    or companion_state_lookup.get(npc_name)
                    or {}
                )
            if state_data:
                try:
                    influence = int(state_data.get("influence", 0) or 0)
                    trust = int(state_data.get("trust", 0) or 0)
                    fear = int(state_data.get("fear", 0) or 0)
                    respect = int(state_data.get("respect", 0) or 0)
                except (TypeError, ValueError):
                    influence = trust = fear = respect = 0

                if influence >= 50 or trust >= 60:
                    block += "\nCurrent stance: Warm and trusting toward the player."
                elif influence <= -40 or fear >= 60:
                    block += "\nCurrent stance: Cold, guarded, and openly hostile toward the player."
                elif respect >= 60:
                    block += "\nCurrent stance: Respectful but measured; expects competence."

                if fear >= 70:
                    block += "\nTension: Speaks cautiously, watching for betrayal or sudden violence."

            blocks.append(block)

    return "\n\n".join(blocks)
