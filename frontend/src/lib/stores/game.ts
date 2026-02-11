/**
 * Game state store — campaign session data.
 *
 * Holds the current campaign ID, player ID, and the last turn response.
 * Memory only — not persisted to localStorage.
 */
import { writable, derived } from 'svelte/store';
import type {
  TurnResponse, TranscriptTurn,
  DialogueTurn, SceneFrame, NPCUtterance, PlayerResponse
} from '$lib/api/types';

/** Active campaign ID. */
export const campaignId = writable<string | null>(null);

/** Active player ID. */
export const playerId = writable<string | null>(null);

/** The full TurnResponse from the last completed turn. */
export const lastTurnResponse = writable<TurnResponse | null>(null);

/** Turn transcript (array of past turns for journal). */
export const transcript = writable<TranscriptTurn[]>([]);

/** Current turn number (derived from transcript length). */
export const turnNumber = derived(transcript, ($transcript) => $transcript.length);

/** Whether a game is currently active. */
export const isGameActive = derived(
  [campaignId, playerId],
  ([$campaignId, $playerId]) => !!$campaignId && !!$playerId
);

/** Derived: suggested actions from last turn. */
export const suggestedActions = derived(
  lastTurnResponse,
  ($resp) => $resp?.suggested_actions ?? []
);

/** Derived: player sheet from last turn. */
export const playerSheet = derived(
  lastTurnResponse,
  ($resp) => $resp?.player_sheet ?? null
);

/** Derived: inventory from last turn. */
export const inventory = derived(
  lastTurnResponse,
  ($resp) => $resp?.inventory ?? []
);

/** Derived: party status from last turn. */
export const partyStatus = derived(
  lastTurnResponse,
  ($resp) => $resp?.party_status ?? null
);

/** Derived: faction reputation from last turn. */
export const factionReputation = derived(
  lastTurnResponse,
  ($resp) => $resp?.faction_reputation ?? null
);

/** Derived: news feed from last turn. */
export const newsFeed = derived(
  lastTurnResponse,
  ($resp) => $resp?.news_feed ?? null
);

/** Derived: warnings from last turn. */
export const warnings = derived(
  lastTurnResponse,
  ($resp) => $resp?.warnings ?? []
);

// ---------------------------------------------------------------------------
// V2.17+V2.18: DialogueTurn stores (KOTOR-soul)
// ---------------------------------------------------------------------------

/** Derived: full DialogueTurn from last turn (primary UI source when available). */
export const dialogueTurn = derived<typeof lastTurnResponse, DialogueTurn | null>(
  lastTurnResponse,
  ($resp) => ($resp?.dialogue_turn as DialogueTurn | undefined) ?? null
);

/** Derived: SceneFrame snapshot (location, NPCs, topic, pressure). */
export const sceneFrame = derived<typeof dialogueTurn, SceneFrame | null>(
  dialogueTurn,
  ($dt) => $dt?.scene_frame ?? null
);

/** Derived: NPC speech for this turn. */
export const npcUtterance = derived<typeof dialogueTurn, NPCUtterance | null>(
  dialogueTurn,
  ($dt) => $dt?.npc_utterance ?? null
);

/** Derived: KOTOR-style player responses (primary source for dialogue choices).
 *  Falls back to empty array — caller should check and fall back to suggestedActions. */
export const playerResponses = derived<typeof dialogueTurn, PlayerResponse[]>(
  dialogueTurn,
  ($dt) => $dt?.player_responses ?? []
);

// ---------------------------------------------------------------------------
// V3.0: Quest log store
// ---------------------------------------------------------------------------

/** Derived: quest log from last turn (populated by QuestTracker). */
export const questLog = derived(
  lastTurnResponse,
  ($resp) => $resp?.quest_log ?? {}
);

/** Reset all game state (e.g., when returning to main menu). */
export function resetGame(): void {
  campaignId.set(null);
  playerId.set(null);
  lastTurnResponse.set(null);
  transcript.set([]);
}
