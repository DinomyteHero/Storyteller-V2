"""Centralized tuning constants shared across the app."""
from __future__ import annotations

# Ledger limits
LEDGER_MAX_FACTS = 40
LEDGER_MAX_THREADS = 10
LEDGER_MAX_GOALS = 10
LEDGER_MAX_CONSTRAINTS = 10
LEDGER_MAX_TONE_TAGS = 5

# Memory compression
MEMORY_RECENT_TURNS = 10
MEMORY_COMPRESSION_CHUNK_SIZE = 10
MEMORY_MAX_ERA_SUMMARIES = 5
MEMORY_ERA_SUMMARY_MAX_CHARS = 300

# Mechanic delta clamps
DELTA_CLAMP_MIN = -10
DELTA_CLAMP_MAX = 10

# Token estimation factors (ContextBudget)
TOKEN_ESTIMATE_CHARS_PER_TOKEN = 4
TOKEN_ESTIMATE_WORDS_PER_TOKEN = 1.3

# Retry counts
DIRECTOR_MAX_RETRIES = 2
JSON_RELIABILITY_MAX_RETRIES = 3

# Similarity thresholds
INTENT_JACCARD_THRESHOLD = 0.6

# Suggested actions UX contract:
# - Director may propose a variable number, but the UI expects we pad/trim to TARGET.
SUGGESTED_ACTIONS_MIN = 3
SUGGESTED_ACTIONS_TARGET = 4
SUGGESTED_ACTIONS_MAX = 10

# Knowledge Graph retrieval defaults
KG_MAX_RELATIONSHIPS_PER_CHAR = 8
KG_MAX_EVENTS = 3
KG_DIRECTOR_MAX_TOKENS = 600
KG_NARRATOR_MAX_TOKENS = 800

# Thematic resonance (Phase 3)
LEDGER_MAX_THEMES = 3
THEME_REINFORCEMENT_KEYWORDS: dict[str, list[str]] = {
    "cost_of_loyalty": ["betray", "trust", "loyal", "sacrifice", "faith", "oath"],
    "power_corrupts": ["power", "corrupt", "control", "dominate", "authority"],
    "redemption": ["forgive", "atone", "redeem", "second chance", "regret"],
    "survival_vs_morality": ["survive", "moral", "choice", "cost", "compromise"],
    "identity_and_belonging": ["belong", "identity", "home", "outsider", "accept"],
    "hope_against_darkness": ["hope", "dark", "light", "resist", "endure", "defiance"],
    "duty_vs_desire": ["duty", "desire", "want", "must", "obligation", "freedom"],
}

# Dynamic arc staging (Phase 4)
ARC_MIN_TURNS: dict[str, int] = {"SETUP": 3, "RISING": 5, "CLIMAX": 5, "RESOLUTION": 3}
ARC_MAX_TURNS: dict[str, int] = {"SETUP": 10, "RISING": 25, "CLIMAX": 15, "RESOLUTION": 999}
ARC_SETUP_TO_RISING_MIN_THREADS = 2
ARC_SETUP_TO_RISING_MIN_FACTS = 3
ARC_RISING_TO_CLIMAX_MIN_THREADS = 4
ARC_CLIMAX_RESOLUTION_FLAG_PREFIX = "resolved"

# Deep companion system (Phase 5)
COMPANION_ARC_STRANGER_MAX = -10
COMPANION_ARC_ALLY_MIN = -9
COMPANION_ARC_TRUSTED_MIN = 30
COMPANION_ARC_LOYAL_MIN = 70
COMPANION_MAX_MEMORIES = 10
COMPANION_CONFLICT_SHARP_DROP = -8
COMPANION_CONFLICT_THRESHOLD_CROSS = -30

# Hero's Journey beats mapped to arc stages
# Each main stage contains 3 sub-beats that advance by turn count within the stage.
HERO_JOURNEY_BEATS: dict[str, list[dict[str, str]]] = {
    "SETUP": [
        {
            "beat": "ORDINARY_WORLD",
            "pacing": "Establish the character's normal life, routines, and relationships. Show what they stand to lose.",
        },
        {
            "beat": "CALL_TO_ADVENTURE",
            "pacing": "Introduce the inciting incident. Something disrupts the status quo and demands a response.",
        },
        {
            "beat": "REFUSAL_OF_THE_CALL",
            "pacing": "Show hesitation or doubt. The character resists the call — fear, duty, comfort hold them back.",
        },
    ],
    "RISING": [
        {
            "beat": "MEETING_THE_MENTOR",
            "pacing": "Introduce a guide figure who offers wisdom, training, or a crucial gift. Build trust.",
        },
        {
            "beat": "CROSSING_THE_THRESHOLD",
            "pacing": "The character commits to the journey. There is no going back. Raise stakes dramatically.",
        },
        {
            "beat": "TESTS_ALLIES_ENEMIES",
            "pacing": "Challenge the character with trials. Introduce allies and enemies. Build the world of the adventure.",
        },
    ],
    "CLIMAX": [
        {
            "beat": "APPROACH_INMOST_CAVE",
            "pacing": "Preparation for the central ordeal. Tension builds. Plans are made. Doubts resurface.",
        },
        {
            "beat": "ORDEAL",
            "pacing": "The supreme crisis. Life-or-death stakes. The character faces their greatest fear or enemy.",
        },
        {
            "beat": "REWARD",
            "pacing": "Victory or transformation after the ordeal. The character seizes what they came for.",
        },
    ],
    "RESOLUTION": [
        {
            "beat": "THE_ROAD_BACK",
            "pacing": "The journey home begins but new dangers arise. Consequences of the ordeal ripple outward.",
        },
        {
            "beat": "RESURRECTION",
            "pacing": "A final test that proves the character has truly changed. The last threshold.",
        },
        {
            "beat": "RETURN_WITH_ELIXIR",
            "pacing": "The character returns transformed, bearing gifts or wisdom for their community.",
        },
    ],
}

# NPC archetypes for Hero's Journey-aware generation
NPC_ARCHETYPES: dict[str, str] = {
    "MENTOR": "A wise guide who prepares the hero — offers training, advice, or a crucial artifact.",
    "SHADOW": "The primary antagonist or dark reflection of the hero. Embodies what the hero fears becoming.",
    "THRESHOLD_GUARDIAN": "A gatekeeper who tests the hero's resolve before they can advance. Not necessarily evil.",
    "ALLY": "A loyal friend who supports the hero through trials. Provides skills or knowledge the hero lacks.",
    "SHAPESHIFTER": "An ambiguous figure whose loyalty is uncertain. Keeps the hero (and player) guessing.",
    "HERALD": "The bringer of change — delivers the call to adventure or announces a new challenge.",
    "TRICKSTER": "A comic or chaotic figure who disrupts the status quo. Provides relief and unexpected insight.",
}

# Which NPC archetypes are most relevant at each Hero's Journey beat
BEAT_ARCHETYPE_HINTS: dict[str, list[str]] = {
    "ORDINARY_WORLD": ["ALLY"],
    "CALL_TO_ADVENTURE": ["HERALD"],
    "REFUSAL_OF_THE_CALL": ["THRESHOLD_GUARDIAN"],
    "MEETING_THE_MENTOR": ["MENTOR"],
    "CROSSING_THE_THRESHOLD": ["THRESHOLD_GUARDIAN", "ALLY"],
    "TESTS_ALLIES_ENEMIES": ["ALLY", "SHADOW", "TRICKSTER"],
    "APPROACH_INMOST_CAVE": ["SHAPESHIFTER", "SHADOW"],
    "ORDEAL": ["SHADOW"],
    "REWARD": ["ALLY", "MENTOR"],
    "THE_ROAD_BACK": ["SHADOW", "TRICKSTER"],
    "RESURRECTION": ["SHADOW", "MENTOR"],
    "RETURN_WITH_ELIXIR": ["ALLY", "HERALD"],
}

# Banter pool: pre-written one-liners per (banter_style, tone) for companion reactions.
# Runtime picks from these with seeded RNG instead of 6 hardcoded templates.
BANTER_POOL: dict[str, dict[str, list[str]]] = {
    "warm": {
        "PARAGON": [
            "{name} catches your eye and gives a small, approving nod.",
            '"{name} smiles quietly. \"That was the right call.\""',
            "{name} places a hand briefly on your shoulder — a silent thank-you.",
            '"{name} watches you with something like admiration. \"You remind me why I\'m here.\""',
            "{name} exhales with relief. \"Good. That's who you are.\"",
        ],
        "RENEGADE": [
            "{name} flinches, looking away.",
            '"{name} shakes their head slowly. \"I didn\'t sign up for this.\""',
            "{name}'s jaw tightens, but they say nothing.",
            '"{name} mutters, \"There had to be another way.\""',
            "{name} crosses their arms, disappointment written across their face.",
        ],
        "INVESTIGATE": [
            '"{name} tilts their head, intrigued. \"Smart. Let\'s see where this leads.\""',
            "{name} leans closer, curiosity piqued.",
            '"{name} nods thoughtfully. \"I was wondering about that too.\""',
            "{name} pulls out a datapad, already cross-referencing.",
            '"{name} murmurs, \"Good instinct. Keep digging.\""',
        ],
        "NEUTRAL": [
            "{name} watches the scene unfold with quiet attentiveness.",
            "{name} stays close, ready for whatever comes next.",
            '"{name} gives a noncommittal hum. \"We\'ll see.\""',
        ],
    },
    "snarky": {
        "PARAGON": [
            '"{name} rolls their eyes. \"Saints and martyrs. Fine, I\'ll play along.\""',
            '"{name} smirks. \"The galaxy thanks you. Probably.\""',
            '"{name} slow-claps once. \"Heroic. Truly.\""',
            '"{name} snorts. \"You actually meant that, didn\'t you? Unbelievable.\""',
            '"{name} gives an exaggerated bow. \"After you, noble one.\""',
        ],
        "RENEGADE": [
            '"{name} grins wolfishly. \"Now you\'re speaking my language.\""',
            '"{name} lets out a low whistle. \"Cold. I like it.\""',
            '"{name} cracks their knuckles. \"About time.\""',
            '"{name} chuckles darkly. \"Remind me not to cross you.\""',
            '"{name} raises an eyebrow. \"That\'s one way to handle it.\""',
        ],
        "INVESTIGATE": [
            '"{name} sighs. \"More questions. My favorite.\""',
            '"{name} leans against the wall. \"Wake me when you find something.\""',
            '"{name} smirks. \"Playing detective again? Fine. I\'ll watch the door.\""',
            '"{name} mutters, \"Digging through data. Thrilling.\""',
            '"{name} waves a hand. \"Go on, Sherlock. I\'m riveted.\""',
        ],
        "NEUTRAL": [
            '"{name} picks at their nails, looking bored."',
            '"{name} stifles a yawn. \"Let me know when it gets interesting.\""',
            "{name} watches with the studied indifference of someone who's seen it all.",
        ],
    },
    "stoic": {
        "PARAGON": [
            "{name} inclines their head — the closest thing to praise they offer.",
            "{name} says nothing, but their posture relaxes slightly.",
            '"{name} meets your gaze. \"Noted.\""',
            "{name} stands a little straighter, as if reassured.",
            '"{name} exhales through their nose. \"Acceptable.\""',
        ],
        "RENEGADE": [
            "{name}'s expression hardens, unreadable.",
            "{name} turns away without a word.",
            '"{name} says flatly, \"That wasn\'t necessary.\""',
            "{name} stares at a fixed point on the wall, processing.",
            "{name} draws a slow breath but holds their tongue.",
        ],
        "INVESTIGATE": [
            "{name} scans the room methodically, already cataloguing details.",
            '"{name} nods once. \"Proceed.\""',
            "{name} falls into step beside you, alert and watchful.",
            '"{name} murmurs, \"Data first. Then decisions.\""',
            "{name} produces a scanner without being asked.",
        ],
        "NEUTRAL": [
            "{name} stands watch, expression unreadable.",
            "{name} waits in disciplined silence.",
            "{name} keeps their own counsel, eyes forward.",
        ],
    },
    # --- V2.10: Expanded banter styles for companion personality diversity ---
    "defensive": {
        "PARAGON": [
            "{name} uncrosses their arms — just barely. \"Fine. That was... decent.\"",
            "{name} looks away. \"Don't expect me to say it twice, but — good call.\"",
            "{name} huffs. \"I suppose that's one way to handle it. Not the worst.\"",
        ],
        "RENEGADE": [
            "{name} flinches. \"You're going to get us killed doing things like that.\"",
            "{name} takes a step back, hands up. \"That's on you. Not me.\"",
            "{name} mutters, \"Every time I think you're reasonable...\"",
        ],
        "INVESTIGATE": [
            "{name} peers over your shoulder, reluctantly curious. \"What did you find?\"",
            "{name} crosses their arms but leans in anyway. \"...Go on.\"",
            "{name} sighs. \"Fine. Show me. But I'm not promising anything.\"",
        ],
        "NEUTRAL": [
            "{name} keeps their distance, watchful.",
            "{name} shifts their weight, ready to move if needed.",
            "{name} scans the exits, a habit they never shake.",
        ],
    },
    "wise": {
        "PARAGON": [
            "{name} nods slowly. \"Wisdom is choosing the harder right over the easier wrong.\"",
            "{name} closes their eyes briefly. \"The Force approves. I can feel it.\"",
            "{name} places their hands together. \"You chose well. Remember this feeling.\"",
        ],
        "RENEGADE": [
            "{name} opens their eyes, sadness in them. \"That path leads to suffering.\"",
            "{name} sighs deeply. \"I have seen this choice before. It did not end well.\"",
            "{name} says quietly, \"The dark is patient. It waits for moments like these.\"",
        ],
        "INVESTIGATE": [
            "{name} strokes their chin. \"Seek the truth, but be ready for what you find.\"",
            "{name} nods. \"Questions are the beginning of wisdom. Ask freely.\"",
            "{name} watches with approval. \"Patience and observation — the Jedi way.\"",
        ],
        "NEUTRAL": [
            "{name} meditates in stillness, content to wait.",
            "{name} observes the scene with centuries of perspective.",
            "{name} breathes evenly, centered and present.",
        ],
    },
    "calculating": {
        "PARAGON": [
            "{name} makes a mental note. \"That earns you leverage. Spend it wisely.\"",
            "{name} arches an eyebrow. \"Interesting. Generosity as strategy. Not bad.\"",
            "{name} nods once. \"A sound investment in goodwill. I approve.\"",
        ],
        "RENEGADE": [
            "{name} smirks. \"Ruthless. I can work with ruthless.\"",
            "{name} files the information away. \"Useful to know your limits.\"",
            "{name} tilts their head. \"That was... efficient. If messy.\"",
        ],
        "INVESTIGATE": [
            "{name} pulls up a datapad. \"Let me run the numbers on that.\"",
            "{name} narrows their eyes. \"There's an angle here. I can smell it.\"",
            "{name} murmurs, \"Data. I need data before I form an opinion.\"",
        ],
        "NEUTRAL": [
            "{name} weighs options in silence, eyes darting between possibilities.",
            "{name} watches the exchange like a dejarik player studying the board.",
            "{name} says nothing, but you can see the gears turning.",
        ],
    },
    "terse": {
        "PARAGON": [
            "{name}: \"Good.\"",
            "{name} nods. Once.",
            "{name} grunts approval.",
        ],
        "RENEGADE": [
            "{name}: \"Bad idea.\"",
            "{name} shakes their head.",
            "{name}: \"Don't.\"",
        ],
        "INVESTIGATE": [
            "{name}: \"Hmm.\"",
            "{name} looks. Waits.",
            "{name}: \"And?\"",
        ],
        "NEUTRAL": [
            "{name} stands ready.",
            "{name} waits.",
            "{name} watches.",
        ],
    },
    "academic": {
        "PARAGON": [
            "{name} adjusts their spectacles. \"Ethically sound. I'll note that for my records.\"",
            "{name} nods with scholarly approval. \"The altruistic choice — statistically correlated with long-term alliance stability.\"",
            "{name} scribbles in a journal. \"Fascinating. A genuine moral actor in the field.\"",
        ],
        "RENEGADE": [
            "{name} frowns. \"Historically, that approach has a high collateral damage coefficient.\"",
            "{name} taps a stylus against their chin. \"Concerning. The data on that tactic is... grim.\"",
            "{name} mutters, \"I'll note 'aggressive deviation from protocol' in my report.\"",
        ],
        "INVESTIGATE": [
            "{name} brightens. \"Now that is a worthy research question. Let's collect evidence.\"",
            "{name} pulls out a scanner. \"The empirical approach. Excellent. Let me take readings.\"",
            "{name} leans forward eagerly. \"Cross-referencing now. Give me a moment.\"",
        ],
        "NEUTRAL": [
            "{name} records observations in their datapad, ever the scientist.",
            "{name} hums thoughtfully, cataloguing details.",
            "{name} watches with clinical detachment.",
        ],
    },
    "gruff": {
        "PARAGON": [
            "{name} grunts. \"Not bad, kid.\"",
            "{name} claps you on the back — hard. \"That'll do.\"",
            "{name} nods grudgingly. \"Alright. You earned that one.\"",
        ],
        "RENEGADE": [
            "{name} growls. \"You're going to regret that.\"",
            "{name} spits to one side. \"Bah. Sloppy.\"",
            "{name} grabs your arm. \"Listen here — that's not how we do things.\"",
        ],
        "INVESTIGATE": [
            "{name} scratches their stubble. \"What're you poking around for now?\"",
            "{name} folds their arms. \"Get to the point.\"",
            "{name} rumbles, \"Less talking. More doing.\"",
        ],
        "NEUTRAL": [
            "{name} leans against the wall, arms crossed.",
            "{name} keeps watch, jaw set.",
            "{name} stands like a wall, impassive.",
        ],
    },
    "apologetic": {
        "PARAGON": [
            "{name} winces. \"At least this time nobody got hurt because of me.\"",
            "{name} wrings their hands. \"Good. That's... that's good. I'm glad you did that.\"",
            "{name} exhales shakily. \"Thank you for being better than I was.\"",
        ],
        "RENEGADE": [
            "{name} looks stricken. \"I — I'm sorry. I know I should say something, but...\"",
            "{name} turns away. \"That... I've seen that before. I was the one who...\"",
            "{name} whispers, \"Please. Not again. I can't watch this again.\"",
        ],
        "INVESTIGATE": [
            "{name} fidgets. \"I might know something about this. If you want to hear it. Sorry.\"",
            "{name} offers hesitantly, \"I don't want to overstep, but — have you checked...?\"",
            "{name} mumbles, \"Sorry, I just — I noticed something. Probably nothing.\"",
        ],
        "NEUTRAL": [
            "{name} hovers nearby, trying not to get in the way.",
            "{name} shifts from foot to foot, uncertain.",
            "{name} stays close but quiet, guilt in their eyes.",
        ],
    },
    "weary": {
        "PARAGON": [
            "{name} sighs. \"For once, something went right. Don't get used to it.\"",
            "{name} manages a tired smile. \"Hope. Haven't felt that in a while.\"",
            "{name} rubs their eyes. \"Maybe there's still something worth saving.\"",
        ],
        "RENEGADE": [
            "{name} closes their eyes. \"And so it goes. Again.\"",
            "{name} shakes their head slowly. \"I'm too old for this.\"",
            "{name} mutters, \"Another scar on the conscience. Add it to the collection.\"",
        ],
        "INVESTIGATE": [
            "{name} yawns. \"More mysteries. Fine. Let's see what the galaxy's hiding now.\"",
            "{name} drags a hand down their face. \"Alright. One more thread to pull.\"",
            "{name} squints at the evidence. \"Nothing surprises me anymore. Almost.\"",
        ],
        "NEUTRAL": [
            "{name} leans heavily against the nearest surface.",
            "{name} stares into the middle distance, miles away.",
            "{name} breathes. Just breathes. It's enough for now.",
        ],
    },
    "earnest": {
        "PARAGON": [
            "{name} beams. \"That's exactly what I would have done.\"",
            "{name} grabs your hand. \"You're a good person. Don't ever doubt that.\"",
            "{name} practically glows. \"See? The galaxy rewards kindness.\"",
        ],
        "RENEGADE": [
            "{name}'s face falls. \"Why? Why would you do that?\"",
            "{name} looks at you like you've changed. \"That's not... that's not who I thought you were.\"",
            "{name} blinks hard, fighting tears. \"I believed in you.\"",
        ],
        "INVESTIGATE": [
            "{name} bounces on their heels. \"Ooh, are we investigating? I love investigating.\"",
            "{name} peers over your shoulder eagerly. \"What did you find? Show me!\"",
            "{name} claps their hands. \"This is just like the mysteries in the holonovels!\"",
        ],
        "NEUTRAL": [
            "{name} watches attentively, ready to help at a moment's notice.",
            "{name} fidgets with excitement, barely contained.",
            "{name} stays close, eager and open.",
        ],
    },
    "diplomatic": {
        "PARAGON": [
            "{name} inclines their head. \"A decision that will be remembered favorably.\"",
            "{name} offers a measured smile. \"That is the kind of leadership the galaxy needs.\"",
            "{name} nods. \"Consensus is built on moments like this.\"",
        ],
        "RENEGADE": [
            "{name} clasps their hands behind their back, expression carefully neutral.",
            "{name} says evenly, \"I would counsel a different approach next time.\"",
            "{name} takes a measured breath. \"There will be... repercussions to navigate.\"",
        ],
        "INVESTIGATE": [
            "{name} produces a datapad. \"Let me consult the intelligence briefings.\"",
            "{name} nods. \"Knowledge is the foundation of good diplomacy. Proceed.\"",
            "{name} murmurs, \"Understanding the situation fully before acting — wise.\"",
        ],
        "NEUTRAL": [
            "{name} maintains a composed, diplomatic bearing.",
            "{name} observes the dynamics of the room with practiced attention.",
            "{name} waits for the right moment to contribute.",
        ],
    },
    "beeps": {
        "PARAGON": [
            "{name} trills an upbeat sequence of chirps and whistles.",
            "{name} rocks back and forth happily, emitting a cheerful boop.",
            "{name} projects a tiny holographic thumbs-up and beeps twice.",
        ],
        "RENEGADE": [
            "{name} lets out a low, descending series of worried warbles.",
            "{name} rocks backward, blurting a sharp electronic raspberry.",
            "{name} emits a distressed sequence that needs no translation.",
        ],
        "INVESTIGATE": [
            "{name} extends a sensor probe, chittering with electronic curiosity.",
            "{name} beeps rapidly, already running diagnostics.",
            "{name} swivels their dome eagerly, scanners whirring.",
        ],
        "NEUTRAL": [
            "{name} hums softly in standby mode.",
            "{name} rotates their dome, observing the surroundings.",
            "{name} emits a quiet, steady tone — content to be present.",
        ],
    },
    "analytical": {
        "PARAGON": [
            "{name} nods. \"Statistically favorable outcome. Well chosen.\"",
            "{name} processes for a moment. \"Optimal result. Probability of allied cooperation increased.\"",
            "{name} tilts their head. \"The logical choice, and the compassionate one. Unusual alignment.\"",
        ],
        "RENEGADE": [
            "{name} calculates silently. \"Risk factor elevated by 34%. Noted.\"",
            "{name} blinks. \"That approach introduces significant variables I cannot predict.\"",
            "{name} states flatly, \"Suboptimal. But I record, not judge.\"",
        ],
        "INVESTIGATE": [
            "{name} activates multiple scanners simultaneously. \"Collecting data.\"",
            "{name} processes information at visible speed. \"Interesting anomaly detected.\"",
            "{name} cross-references databases. \"Several relevant entries found. Shall I summarize?\"",
        ],
        "NEUTRAL": [
            "{name} observes and records, ever the analyst.",
            "{name} processes ambient data in silence.",
            "{name} monitors the situation with mechanical precision.",
        ],
    },
    "mystical": {
        "PARAGON": [
            "{name} closes their eyes. \"The current flows true through your choice.\"",
            "{name} inhales deeply. \"The spirits whisper approval.\"",
            "{name} traces a symbol in the air. \"Balance is restored. For now.\"",
        ],
        "RENEGADE": [
            "{name} opens their eyes wide. \"The threads grow dark. Tread carefully.\"",
            "{name} shudders. \"The Force cries out. Something has been... wounded.\"",
            "{name} whispers, \"The shadows deepen. Can you not feel it?\"",
        ],
        "INVESTIGATE": [
            "{name} reaches out with unseen senses. \"There is more here than meets the eye.\"",
            "{name} traces patterns in the dust. \"The answer lies hidden. We must look deeper.\"",
            "{name} murmurs, \"The Force reveals to those who are patient enough to listen.\"",
        ],
        "NEUTRAL": [
            "{name} meditates quietly, present but elsewhere.",
            "{name} seems to listen to something only they can hear.",
            "{name} gazes at nothing, communing with forces unseen.",
        ],
    },
    "formal": {
        "PARAGON": [
            "{name} salutes crisply. \"Well executed. Command would approve.\"",
            "{name} stands at attention. \"Noted in the log as exemplary conduct.\"",
            "{name} nods with military precision. \"That is how it's done. By the book.\"",
        ],
        "RENEGADE": [
            "{name} stiffens. \"That action is... irregular. I am obligated to note my objection.\"",
            "{name} clasps their hands behind their back. \"I will follow orders. Under protest.\"",
            "{name} says crisply, \"Deviation from protocol noted. I trust you accept responsibility.\"",
        ],
        "INVESTIGATE": [
            "{name} consults a regulation manual. \"Section 7.3 covers reconnaissance procedures.\"",
            "{name} nods. \"Intelligence gathering. Standard protocol. Proceed.\"",
            "{name} produces a holocomm. \"I'll file the preliminary report while you investigate.\"",
        ],
        "NEUTRAL": [
            "{name} stands at parade rest, awaiting orders.",
            "{name} maintains proper bearing, eyes forward.",
            "{name} checks their equipment with practiced efficiency.",
        ],
    },
}

# Banter pool for memory-referencing lines (TRUSTED/LOYAL companions)
BANTER_MEMORY_POOL: dict[str, list[str]] = {
    "warm": [
        '"{name} glances at you, a flicker of memory in their eyes. \"Like {memory}... only different.\""',
        '"{name} smiles softly. \"After {memory}, I thought I knew what to expect from you.\""',
        '"{name} reaches for your arm. \"Remember {memory}? We made it through that. We\'ll make it through this.\""',
    ],
    "snarky": [
        '"{name} snorts. \"Last time — {memory} — that worked out brilliantly, didn\'t it?\""',
        '"{name} raises a finger. \"Before you do anything, remember {memory}. Just... remember.\""',
        '"{name} grins. \"Déjà vu. {memory}, all over again.\""',
    ],
    "stoic": [
        '"{name} pauses. The silence carries the weight of {memory}."',
        '"{name} says quietly, \"{memory}. I haven\'t forgotten.\""',
        '"{name} gazes into the distance, briefly lost in the echo of {memory}."',
    ],
    "defensive": [
        '"{name} stiffens. \"Like {memory}. Don\'t — don\'t make me remember that.\""',
        '"{name} mutters, \"After {memory}, I thought we had an understanding.\""',
    ],
    "wise": [
        '"{name} nods sagely. \"As with {memory}, the lesson reveals itself in time.\""',
        '"{name} closes their eyes. \"{memory}. The Force works in patterns, young one.\""',
    ],
    "calculating": [
        '"{name} consults a mental ledger. \"{memory}. The returns on that were... mixed.\""',
        '"{name} arches an eyebrow. \"Like {memory}? I remember the odds. And the outcome.\""',
    ],
    "terse": [
        '"{name}: \"{memory}. Remember.\""',
        '"{name} glances at you. One word: \"{memory}.\""',
    ],
    "academic": [
        '"{name} references their notes. \"Similar to {memory} — case study 47-B in my journal.\""',
        '"{name} adjusts their spectacles. \"{memory}. A data point I frequently revisit.\""',
    ],
    "gruff": [
        '"{name} grunts. \"Like {memory}. Only stupider.\""',
        '"{name} growls, \"Don\'t make me drag up {memory} again.\""',
    ],
    "apologetic": [
        '"{name} winces. \"Like {memory}. I\'m still sorry about my part in that.\""',
        '"{name} fidgets. \"After {memory}... I promised I\'d do better.\""',
    ],
    "weary": [
        '"{name} sighs. \"{memory}. Another lifetime ago.\""',
        '"{name} rubs their temples. \"Haven\'t we done this before? {memory}...\""',
    ],
    "earnest": [
        '"{name} lights up. \"Just like {memory}! That was amazing!\""',
        '"{name} grabs your arm. \"Remember {memory}? We can do it again!\""',
    ],
    "diplomatic": [
        '"{name} nods thoughtfully. \"Reminiscent of {memory}. Lessons were learned.\""',
        '"{name} offers carefully, \"After {memory}, perhaps a different approach?\""',
    ],
    "beeps": [
        '"{name} plays back an audio recording of {memory} and warbles hopefully."',
        '"{name} projects a hologram of a key moment from {memory} and chirps."',
    ],
    "analytical": [
        '"{name} cross-references. \"Pattern match: {memory}. Correlation: 87%.\""',
        '"{name} processes. \"Similar parameters to {memory}. Adjusting predictions.\""',
    ],
    "mystical": [
        '"{name} whispers, \"The threads of {memory} still echo in the Force.\""',
        '"{name} traces a symbol. \"{memory}. The vision was clear then, as now.\""',
    ],
    "formal": [
        '"{name} references their log. \"Per incident {memory} — standing orders apply.\""',
        '"{name} notes, \"Situation mirrors {memory}. Protocol recommends caution.\""',
    ],
}

# Director entity guard stop-words (lowercase)
DIRECTOR_ENTITY_STOP_WORDS = frozenset({
    "the", "a", "an", "say", "ask", "look", "go", "investigate", "talk", "take", "try",
    "press", "move", "check", "scan", "gather", "intel", "about", "with", "toward",
    "your", "my", "i", "you", "me", "we", "our", "what", "where", "who", "how",
    "can", "could", "would", "should", "will", "do", "it", "is", "are", "this",
    "that", "for", "from", "into", "around", "through", "on", "in", "at", "to",
    "of", "and", "or", "but", "up", "out", "off", "something", "someone", "here",
    "there", "area", "place", "situation", "objective", "goal", "action", "forward",
    "force", "details", "clues", "question", "more", "else", "risky", "carefully",
    "decisive", "firmly", "subtly", "quietly", "openly", "nearby", "local", "current",
    "new", "old", "safe", "dangerous", "approach", "confront", "explore", "commit",
    "social", "hi", "hello", "advance",
})
