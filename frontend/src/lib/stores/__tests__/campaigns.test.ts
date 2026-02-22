import { beforeEach, describe, expect, it, vi } from 'vitest';

// Mock $app/environment so `browser` is true in jsdom test context.
// Without this, every store function short-circuits with `if (!browser) return`.
vi.mock('$app/environment', () => ({ browser: true }));

import {
  getSavedCampaignMap,
  getSavedCampaigns,
  patchCampaignCache,
  removeCampaign,
  saveCampaign,
  touchCampaign,
} from '$lib/stores/campaigns';

const STORAGE_KEY = 'storyteller-saved-campaigns';

describe('campaigns store cache behavior', () => {
  beforeEach(() => {
    // Clear localStorage AND any in-memory residue so stores don't leak between tests.
    localStorage.clear();
  });

  it('upserts and merges backend campaign metadata', () => {
    patchCampaignCache({
      campaignId: 'camp-1',
      playerId: 'player-1',
      playerName: 'Ari',
      era: 'REBELLION',
      turnCount: 3,
    });

    patchCampaignCache({
      campaignId: 'camp-1',
      sagaId: 'saga-1',
      sagaChapter: 2,
      turnCount: 4,
    });

    const map = getSavedCampaignMap();
    expect(map['camp-1']).toBeDefined();
    expect(map['camp-1'].playerId).toBe('player-1');
    expect(map['camp-1'].sagaId).toBe('saga-1');
    expect(map['camp-1'].sagaChapter).toBe(2);
    expect(map['camp-1'].turnCount).toBe(4);
  });

  it('sorts campaigns by lastPlayedAt descending', () => {
    saveCampaign({
      campaignId: 'older',
      playerId: 'p1',
      playerName: 'Older',
      era: 'REBELLION',
      background: null,
      createdAt: '2026-01-01T00:00:00.000Z',
      lastPlayedAt: '2026-01-02T00:00:00.000Z',
      turnCount: 1,
    });
    saveCampaign({
      campaignId: 'newer',
      playerId: 'p2',
      playerName: 'Newer',
      era: 'LOTF',
      background: null,
      createdAt: '2026-01-01T00:00:00.000Z',
      lastPlayedAt: '2026-01-03T00:00:00.000Z',
      turnCount: 2,
    });

    const list = getSavedCampaigns();
    expect(list[0].campaignId).toBe('newer');
    expect(list[1].campaignId).toBe('older');
  });

  it('touchCampaign updates recency and turn count, and removeCampaign deletes', () => {
    saveCampaign({
      campaignId: 'camp-2',
      playerId: 'player-2',
      playerName: 'Mina',
      era: 'NEW_REPUBLIC',
      background: null,
      createdAt: '2026-01-01T00:00:00.000Z',
      lastPlayedAt: '2026-01-01T00:00:00.000Z',
      turnCount: 1,
    });

    touchCampaign('camp-2', 9);
    let map = getSavedCampaignMap();
    expect(map['camp-2'].turnCount).toBe(9);

    removeCampaign('camp-2');
    map = getSavedCampaignMap();
    expect(map['camp-2']).toBeUndefined();
  });
});
