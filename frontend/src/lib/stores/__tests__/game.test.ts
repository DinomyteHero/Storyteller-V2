import { beforeEach, describe, expect, it } from 'vitest';
import { get } from 'svelte/store';
import {
  activeObligations,
  campaignId,
  isGameActive,
  lastSeenFeedLength,
  lastTurnResponse,
  markIntelRead,
  playerId,
  resetGame,
  suggestedActions,
  transcript,
  turnNumber,
  unreadIntelCount,
} from '$lib/stores/game';
import type { TurnResponse } from '$lib/api/types';

function makeTurnResponse(): TurnResponse {
  return {
    narrated_text: 'Scene text',
    suggested_actions: [],
    player_sheet: {
      character_id: 'player-1',
      name: 'Test Hero',
      gender: 'male',
      background: null,
      planet_id: null,
      location_id: 'loc-cantina',
      credits: 0,
      stats: {},
      hp_current: 10,
      inventory: [],
      psych_profile: { current_mood: 'steady', stress_level: 0, active_trauma: null },
      cyoa_answers: null,
    },
    inventory: [],
    quest_log: {},
    world_time_minutes: 0,
    party_status: null,
    faction_reputation: null,
    news_feed: null,
    warnings: [],
  };
}

describe('game store', () => {
  beforeEach(() => {
    resetGame();
  });

  it('derives turn number from transcript length', () => {
    transcript.set([]);
    expect(get(turnNumber)).toBe(0);
    transcript.set([{ turn_number: 1, text: 'A', time_cost_minutes: 5 }]);
    expect(get(turnNumber)).toBe(1);
    transcript.set([
      { turn_number: 1, text: 'A', time_cost_minutes: 5 },
      { turn_number: 2, text: 'B', time_cost_minutes: 5 },
    ]);
    expect(get(turnNumber)).toBe(2);
  });

  it('isGameActive requires both campaignId and playerId', () => {
    campaignId.set(null);
    playerId.set(null);
    expect(get(isGameActive)).toBe(false);
    campaignId.set('camp-1');
    expect(get(isGameActive)).toBe(false);
    playerId.set('player-1');
    expect(get(isGameActive)).toBe(true);
  });

  it('surfaces suggested actions and obligations from last turn response', () => {
    const resp = makeTurnResponse();
    resp.suggested_actions = [
      {
        label: 'Investigate',
        intent_text: 'I investigate the room',
        category: 'EXPLORE',
        risk_level: 'SAFE',
        strategy_tag: 'OPTIMAL',
        tone_tag: 'INVESTIGATE',
        intent_style: 'careful',
        consequence_hint: 'You may find clues.',
        companion_reactions: {},
        risk_factors: [],
      },
    ];
    resp.active_obligations = ['Resolve the smuggler debt'];
    lastTurnResponse.set(resp);
    expect(get(suggestedActions)).toHaveLength(1);
    expect(get(activeObligations)).toEqual(['Resolve the smuggler debt']);
  });

  it('tracks unread intel and clears it when comms are marked read', () => {
    const resp = makeTurnResponse();
    resp.news_feed = [
      { headline: 'A', source_tag: 'HoloNet', urgency: 'low', body: 'a', related_factions: [] },
      { headline: 'B', source_tag: 'HoloNet', urgency: 'low', body: 'b', related_factions: [] },
    ];
    lastTurnResponse.set(resp);
    lastSeenFeedLength.set(0);
    expect(get(unreadIntelCount)).toBe(2);
    markIntelRead();
    expect(get(unreadIntelCount)).toBe(0);
  });
});
