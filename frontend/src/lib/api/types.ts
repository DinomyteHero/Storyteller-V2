/**
 * TypeScript interfaces matching the FastAPI backend Pydantic models.
 * Source of truth: backend/app/models/state.py + backend/app/api/v2_campaigns.py
 *                  backend/app/models/dialogue_turn.py (V2.17+V2.18 DialogueTurn)
 */

// ---------------------------------------------------------------------------
// V2.17+V2.18: DialogueTurn contract (KOTOR-soul)
// ---------------------------------------------------------------------------

export interface NPCRef {
  id: string;
  name: string;
  role: string;
  voice_profile: Record<string, string>;
}

export interface SceneFrame {
  location_id: string;
  location_name: string;
  present_npcs: NPCRef[];
  immediate_situation: string;
  player_objective: string;
  allowed_scene_type: string; // dialogue | combat | exploration | travel | stealth
  scene_hash: string;
  // V2.18: KOTOR-soul context
  topic_primary: string;
  topic_secondary: string;
  subtext: string;
  npc_agenda: string;
  scene_style_tags: string[];
  pressure: Record<string, string>; // { alert: "Quiet"|"Watchful"|"Lockdown", heat: "Low"|"Noticed"|"Wanted" }
}

export interface NPCUtterance {
  speaker_id: string;
  speaker_name: string;
  text: string;
  subtext_hint: string;
  rhetorical_moves: string[];
}

export interface PlayerAction {
  type: string;   // "say" | "do"
  intent: string;  // ask|agree|bluff|threaten|charm|refuse|observe|leave|attack|bribe|...
  target: string | null;
  tone: string | null; // PARAGON | INVESTIGATE | RENEGADE | NEUTRAL
}

export interface PlayerResponse {
  id: string;            // "resp_1", "resp_2", ...
  display_text: string;  // short punchy line shown in UI (8-16 words)
  action: PlayerAction;
  risk_level: string;    // SAFE | RISKY | DANGEROUS
  consequence_hint: string;
  tone_tag: string;      // PARAGON | INVESTIGATE | RENEGADE | NEUTRAL
  meaning_tag: string;   // reveal_values|probe_belief|challenge_premise|seek_history|set_boundary|pragmatic|deflect
}

export interface ValidationReport {
  checks_passed: string[];
  checks_failed: string[];
  repairs_applied: string[];
}

export interface DialogueTurn {
  turn_id: string;                         // "{campaign_id}_t{turn_number}"
  scene_frame: SceneFrame;
  npc_utterance: NPCUtterance;
  player_responses: PlayerResponse[];      // 3-6 KOTOR-style responses
  narrated_prose: string;                  // full Narrator prose (journal, NOT rendered in dialogue panel)
  validation: ValidationReport | null;
}

// ---------------------------------------------------------------------------
// Legacy interfaces
// ---------------------------------------------------------------------------

export interface ActionSuggestion {
  label: string;
  intent_text: string;
  category: string;
  risk_level: string; // SAFE | RISKY | DANGEROUS
  strategy_tag: string;
  tone_tag: string; // PARAGON | INVESTIGATE | RENEGADE | NEUTRAL
  intent_style: string;
  consequence_hint: string;
  companion_reactions: Record<string, number>;
  risk_factors: string[];
}

export interface PsychProfile {
  current_mood: string;
  stress_level: number;
  active_trauma: string | null;
}

export interface PlayerSheet {
  character_id: string;
  name: string;
  gender: string | null;
  background: string | null;
  planet_id: string | null;
  location_id: string | null;
  credits: number | null;
  stats: Record<string, number>;
  hp_current: number;
  inventory: InventoryItem[];
  psych_profile: PsychProfile;
  cyoa_answers: Record<string, string> | null;
}

export interface InventoryItem {
  item_name: string;
  quantity: number;
}

export interface PartyStatusItem {
  id: string;
  name: string;
  affinity: number;
  loyalty_progress: number;
  mood_tag: string | null;
  affinity_delta: number;
  // V2.20: PartyState fields
  influence: number | null;
  trust: number | null;
  respect: number | null;
  fear: number | null;
}

export interface NewsFeedItem {
  headline: string;
  source_tag: string;
  urgency: string;
  body: string;
  related_factions: string[];
}

export interface TurnResponse {
  narrated_text: string;
  suggested_actions: ActionSuggestion[];
  player_sheet: PlayerSheet;
  inventory: InventoryItem[];
  quest_log: Record<string, unknown>;
  world_time_minutes: number | null;
  canonical_year_label?: string | null;
  party_status: PartyStatusItem[] | null;
  faction_reputation: Record<string, number> | null;
  news_feed: NewsFeedItem[] | null;
  warnings: string[];
  debug?: Record<string, unknown>;
  // V2.17: DialogueTurn contract (primary UI source when available)
  dialogue_turn?: DialogueTurn | null;
  turn_contract?: TurnContract | null;
  // V3.2: Alignment data from backend
  alignment?: { light_dark: number; paragon_renegade: number } | null;
}

export interface TurnContract {
  mode: "SIM"|"PASSAGE"|"HYBRID";
  campaign_id: string;
  turn_id: string;
  display_text: string;
  scene_goal: string;
  obstacle: string;
  stakes: string;
  outcome: { category: string };
  choices: Array<{ id: string; label: string; intent: Intent }>;
}


export interface SetupAutoRequest {
  setting_id?: string | null;
  period_id?: string | null;
  time_period?: string | null;
  genre: string | null;
  themes: string[];
  player_concept: string;
  starting_location: string | null;
  randomize_starting_location: boolean;
  background_id: string | null;
  background_answers: Record<string, number>;
  player_gender: string;
  // V3.1: Campaign scale and mode
  campaign_scale?: string;
  campaign_mode?: string;
  // V3.2: Difficulty selection
  difficulty?: string;
}

export interface SetupAutoResponse {
  campaign_id: string;
  player_id: string;
  skeleton: Record<string, unknown>;
  character_sheet: Record<string, unknown>;
}

export interface Intent {
  intent_type: "TALK"|"MOVE"|"FIGHT"|"SNEAK"|"HACK"|"INVESTIGATE"|"REST"|"BUY"|"USE_ITEM"|"FORCE"|"PASSAGE";
  target_ids: Record<string,string>;
  params: Record<string, unknown>;
  user_utterance?: string | null;
}

export interface TurnRequest {
  user_input?: string;
  intent?: Intent;
  debug?: boolean;
  include_state?: boolean;
}

export interface TranscriptTurn {
  turn_number: number;
  text: string;
  time_cost_minutes: number | null;
}

export interface TranscriptResponse {
  campaign_id: string;
  turns: TranscriptTurn[];
}

export interface SSEEvent {
  type: 'token' | 'done' | 'error';
  text?: string;
  message?: string;
  // done event includes full TurnResponse fields
  narrated_text?: string;
  suggested_actions?: ActionSuggestion[];
  player_sheet?: PlayerSheet;
  inventory?: InventoryItem[];
  quest_log?: Record<string, unknown>;
  world_time_minutes?: number | null;
  canonical_year_label?: string | null;
  party_status?: PartyStatusItem[] | null;
  faction_reputation?: Record<string, number> | null;
  news_feed?: NewsFeedItem[] | null;
  warnings?: string[];
  // V2.17: DialogueTurn contract
  dialogue_turn?: DialogueTurn | null;
  turn_contract?: TurnContract | null;
}

export interface EraBackground {
  id: string;
  name: string;
  description: string;
  starting_stats: Record<string, number>;
  questions: BackgroundQuestion[];
}

export interface BackgroundQuestion {
  id: string;
  title: string;
  subtitle: string;
  condition: string | null;
  choices: BackgroundChoice[];
}

export interface BackgroundChoice {
  label: string;
  concept: string;
  tone: string;
  effects?: Record<string, unknown>;
}

export interface EraLocation {
  id: string;
  name: string;
  description: string;
  planet_id: string;
}
