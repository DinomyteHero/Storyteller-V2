"""Controlled vocabulary of relationship predicates for the Knowledge Graph.

Using a fixed set prevents the LLM from inventing arbitrary relationship types,
keeping queries predictable and output compact.
"""
from __future__ import annotations

# Character relationships
TRAINED_BY = "TRAINED_BY"
TRAINS = "TRAINS"
FATHER_OF = "FATHER_OF"
MOTHER_OF = "MOTHER_OF"
CHILD_OF = "CHILD_OF"
SIBLING_OF = "SIBLING_OF"
MARRIED_TO = "MARRIED_TO"
FRIEND_OF = "FRIEND_OF"
RIVAL_OF = "RIVAL_OF"
ENEMY_OF = "ENEMY_OF"
APPRENTICE_OF = "APPRENTICE_OF"
MASTER_OF = "MASTER_OF"
SERVES = "SERVES"
COMMANDS = "COMMANDS"
BETRAYED_BY = "BETRAYED_BY"
BETRAYS = "BETRAYS"
RESCUED_BY = "RESCUED_BY"
RESCUES = "RESCUES"

# Faction membership
MEMBER_OF = "MEMBER_OF"
LEADS = "LEADS"
FOUNDED = "FOUNDED"

# Location associations
LOCATED_ON = "LOCATED_ON"
LOCATED_AT = "LOCATED_AT"
HOMEWORLD_OF = "HOMEWORLD_OF"
CONTROLS = "CONTROLS"
STATIONED_AT = "STATIONED_AT"
TRAVELED_TO = "TRAVELED_TO"

# Event participation
PARTICIPATED_IN = "PARTICIPATED_IN"
INITIATED = "INITIATED"
CONCLUDED = "CONCLUDED"

# Faction dynamics
ALLIED_WITH = "ALLIED_WITH"
OPPOSES = "OPPOSES"
NEUTRAL_TO = "NEUTRAL_TO"
SUBGROUP_OF = "SUBGROUP_OF"

# Object ownership
OWNS = "OWNS"
PILOTS = "PILOTS"
BUILT = "BUILT"

# All valid predicates as a frozenset for validation
VALID_PREDICATES: frozenset[str] = frozenset({
    TRAINED_BY, TRAINS, FATHER_OF, MOTHER_OF, CHILD_OF,
    SIBLING_OF, MARRIED_TO, FRIEND_OF, RIVAL_OF, ENEMY_OF,
    APPRENTICE_OF, MASTER_OF, SERVES, COMMANDS,
    BETRAYED_BY, BETRAYS, RESCUED_BY, RESCUES,
    MEMBER_OF, LEADS, FOUNDED,
    LOCATED_ON, LOCATED_AT, HOMEWORLD_OF, CONTROLS,
    STATIONED_AT, TRAVELED_TO,
    PARTICIPATED_IN, INITIATED, CONCLUDED,
    ALLIED_WITH, OPPOSES, NEUTRAL_TO, SUBGROUP_OF,
    OWNS, PILOTS, BUILT,
})

# Human-readable labels for prompt formatting
PREDICATE_LABELS: dict[str, str] = {
    TRAINED_BY: "trained by",
    TRAINS: "trains",
    FATHER_OF: "father of",
    MOTHER_OF: "mother of",
    CHILD_OF: "child of",
    SIBLING_OF: "sibling of",
    MARRIED_TO: "married to",
    FRIEND_OF: "friend of",
    RIVAL_OF: "rival of",
    ENEMY_OF: "enemy of",
    APPRENTICE_OF: "apprentice of",
    MASTER_OF: "master of",
    SERVES: "serves",
    COMMANDS: "commands",
    BETRAYED_BY: "betrayed by",
    BETRAYS: "betrays",
    RESCUED_BY: "rescued by",
    RESCUES: "rescues",
    MEMBER_OF: "member of",
    LEADS: "leads",
    FOUNDED: "founded",
    LOCATED_ON: "located on",
    LOCATED_AT: "located at",
    HOMEWORLD_OF: "homeworld of",
    CONTROLS: "controls",
    STATIONED_AT: "stationed at",
    TRAVELED_TO: "traveled to",
    PARTICIPATED_IN: "participated in",
    INITIATED: "initiated",
    CONCLUDED: "concluded",
    ALLIED_WITH: "allied with",
    OPPOSES: "opposes",
    NEUTRAL_TO: "neutral to",
    SUBGROUP_OF: "subgroup of",
    OWNS: "owns",
    PILOTS: "pilots",
    BUILT: "built",
}

# Entity types
ENTITY_TYPES: frozenset[str] = frozenset({
    "CHARACTER", "LOCATION", "FACTION", "SHIP", "ARTIFACT", "EVENT",
})
