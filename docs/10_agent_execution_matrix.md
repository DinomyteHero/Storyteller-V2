# Agent Execution Matrix

Source of truth: `backend/app/core/graph.py`, `backend/app/core/nodes/world_sim.py`, `backend/app/core/nodes/arc_planner.py`, `backend/app/core/nodes/commit.py`.

## Pipeline Order

- `ACTION`: `router -> mechanic -> encounter -> world_sim -> companion_reaction -> moments -> arc_planner -> scene_frame -> director -> narrator -> narrative_validator -> choice_crafter -> commit`
- `TALK`: `router -> encounter -> world_sim -> companion_reaction -> moments -> arc_planner -> scene_frame -> director -> narrator -> narrative_validator -> choice_crafter -> commit`
- `META`: `router -> meta -> commit`

## Matrix

| Agent / Node | Turn Type | Frequency | LLM? | Authoritative? |
|---|---|---|---|---|
| `router` (Intent Router) | ALL | Every turn | No | Yes (routing gate) |
| `meta` | META | Every META turn | No | Yes (META output) |
| `MechanicAgent` | ACTION | Every ACTION turn | No | Yes (mechanical outcome) |
| `encounter` | ACTION, TALK | Every ACTION/TALK turn | No | Yes (scene participants/context) |
| `WorldMindAgent` (`world_sim`) | ACTION, TALK | Conditional: when world tick boundary crossed OR travel occurred OR `world_reaction_needed` | Yes | Yes (world sim outputs) |
| `CompanionSystemAgent` (`companion_reaction`) | ACTION, TALK | Every ACTION/TALK turn when party exists | Yes | Yes (affinity/reaction updates) |
| `moments` | ACTION, TALK | Every ACTION/TALK turn | No | Yes |
| `ArcWeaver` evaluation (inside `arc_planner`) | ACTION, TALK | Conditional: only in arc transition window (after min-turn guard) | Yes | Yes (arc transition recommendation within hard guards) |
| `arc_planner` deterministic logic | ACTION, TALK | Every ACTION/TALK turn | No | Yes |
| `scene_frame` | ACTION, TALK | Every ACTION/TALK turn | No | Yes |
| `DirectorAgent` | ACTION, TALK | Every ACTION/TALK turn | Yes | Yes |
| `NarratorAgent` | ACTION, TALK | Every ACTION/TALK turn | Yes | Yes |
| `narrative_validator` | ACTION, TALK | Every ACTION/TALK turn | No | Yes |
| `ChoiceCrafterAgent` (`choice_crafter`) | ACTION, TALK | Every ACTION/TALK turn | Yes | Yes |
| `CommitNode` | ALL | Every turn | Mixed | Yes (DB boundary) |
| `ContinuityAgent` (in commit) | ACTION, TALK | Every `MAINTENANCE_AGENT_FREQUENCY` turns (currently 5), non-META | Yes | Yes |
| `MemoryAgent` (in commit) | ACTION, TALK | Every ACTION/TALK turn with narrator prose + present NPCs | Yes | Yes |
| `QuestWeaverAgent.evaluate` (in commit) | ACTION, TALK | Maintenance turns only, when active dynamic quests exist | Yes | Yes |
| `QuestWeaverAgent.generate` (in commit) | ACTION, TALK | Maintenance turns only, and (`turn % 10 == 0` OR active dynamic quests == 0) | Yes | Yes |
| `ProgressionAgent` (in commit) | ACTION, TALK | Maintenance turns only, plus stage-dependent cadence: every 5 turns in `RISING`/`CLIMAX`, else every 10 | Yes | Yes |
| `PsychArchivistAgent` (in commit) | ACTION, TALK | Maintenance turns only, non-META | Yes | Yes |

## LLM Call Counts (Current)

- Typical ACTION/TALK turn: `Director + Narrator + ChoiceCrafter + CompanionSystem` plus optional `WorldMind` and optional `ArcWeaver`.
- Maintenance ACTION/TALK turn (`turn % 5 == 0`): above plus `Continuity`, `QuestWeaver` (evaluate and/or generate), optional `Progression`, and `PsychArchivist`.
- META turn: deterministic (`meta + commit`) with no required LLM path.

## Notes

- `MAINTENANCE_AGENT_FREQUENCY` is defined in `backend/app/constants.py` and currently set to `5`.
- Commit Group 2 runs `MemoryAgent` and `QuestWeaverAgent` in parallel.
- Authoritative here means the output is used directly in game state/projections, not merely advisory UI text.
