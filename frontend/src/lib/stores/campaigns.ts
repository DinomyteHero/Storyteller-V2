/**
 * Campaign local cache metadata (supplemental to backend list API).
 *
 * Backend `/v2/campaigns` is the source of truth for campaign existence and
 * resume identifiers. This store only persists lightweight UI metadata.
 */
import { browser } from '$app/environment';

const STORAGE_KEY = 'storyteller-saved-campaigns';
const LAST_PLAYED_KEY = 'storyteller-last-played';
const MAX_SAVED = 20;

export interface SavedCampaign {
  campaignId: string;
  playerId: string;
  playerName: string;
  era: string;
  background: string | null;
  sagaId?: string | null;
  sagaChapter?: number | null;
  sagaTitle?: string | null;
  createdAt: string; // ISO timestamp
  lastPlayedAt: string; // ISO timestamp
  turnCount: number;
}

export interface CampaignCachePatch {
  campaignId: string;
  playerId?: string;
  playerName?: string;
  era?: string;
  background?: string | null;
  sagaId?: string | null;
  sagaChapter?: number | null;
  sagaTitle?: string | null;
  createdAt?: string;
  lastPlayedAt?: string;
  turnCount?: number;
}

function loadRegistry(): SavedCampaign[] {
  if (!browser) return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch {
    // Corrupt storage
  }
  return [];
}

function saveRegistry(campaigns: SavedCampaign[]): void {
  if (!browser) return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(campaigns.slice(0, MAX_SAVED)));
  } catch {
    // Quota exceeded
  }
}

/** Get all saved campaigns, sorted by lastPlayedAt (most recent first). */
export function getSavedCampaigns(): SavedCampaign[] {
  return loadRegistry().sort(
    (a, b) => new Date(b.lastPlayedAt).getTime() - new Date(a.lastPlayedAt).getTime()
  );
}

/**
 * Save or update a campaign entry.
 * Called after setup_auto (new campaign) and after each turn (update lastPlayedAt + turnCount).
 */
export function saveCampaign(entry: SavedCampaign): void {
  const campaigns = loadRegistry();
  const idx = campaigns.findIndex((c) => c.campaignId === entry.campaignId);
  if (idx >= 0) {
    campaigns[idx] = entry;
  } else {
    campaigns.unshift(entry);
  }
  saveRegistry(campaigns);
}

/** Update just the lastPlayedAt and turnCount for an existing campaign. */
export function touchCampaign(campaignId: string, turnCount: number): void {
  const campaigns = loadRegistry();
  const campaign = campaigns.find((c) => c.campaignId === campaignId);
  if (campaign) {
    campaign.lastPlayedAt = new Date().toISOString();
    campaign.turnCount = turnCount;
    saveRegistry(campaigns);
  }
}

/** Remove a campaign from the local registry. */
export function removeCampaign(campaignId: string): void {
  const campaigns = loadRegistry().filter((c) => c.campaignId !== campaignId);
  saveRegistry(campaigns);
}

/** Get campaigns keyed by campaignId for fast merge with backend API data. */
export function getSavedCampaignMap(): Record<string, SavedCampaign> {
  const out: Record<string, SavedCampaign> = {};
  for (const c of loadRegistry()) out[c.campaignId] = c;
  return out;
}

/** Get the most recently played campaign (for "Continue Story" button). */
export function getLastPlayed(): SavedCampaign | null {
  if (!browser) return null;
  try {
    const raw = localStorage.getItem(LAST_PLAYED_KEY);
    if (!raw) return null;
    const id = JSON.parse(raw) as string;
    const campaigns = loadRegistry();
    return campaigns.find((c) => c.campaignId === id) ?? null;
  } catch {
    return null;
  }
}

/** Record a campaign as the most recently played (for quick resume). */
export function setLastPlayed(campaignId: string): void {
  if (!browser) return;
  try {
    localStorage.setItem(LAST_PLAYED_KEY, JSON.stringify(campaignId));
  } catch {
    // Quota exceeded
  }
}

/** Upsert partial metadata for a campaign into local cache. */
export function patchCampaignCache(patch: CampaignCachePatch): void {
  const campaigns = loadRegistry();
  const idx = campaigns.findIndex((c) => c.campaignId === patch.campaignId);
  const now = new Date().toISOString();

  const fallback: SavedCampaign = {
    campaignId: patch.campaignId,
    playerId: patch.playerId ?? '',
    playerName: patch.playerName ?? 'Unknown',
    era: patch.era ?? '',
    background: patch.background ?? null,
    sagaId: patch.sagaId ?? null,
    sagaChapter: patch.sagaChapter ?? null,
    sagaTitle: patch.sagaTitle ?? null,
    createdAt: patch.createdAt ?? now,
    lastPlayedAt: patch.lastPlayedAt ?? now,
    turnCount: patch.turnCount ?? 0,
  };

  if (idx >= 0) {
    campaigns[idx] = {
      ...campaigns[idx],
      ...patch,
      campaignId: campaigns[idx].campaignId,
      playerId: patch.playerId ?? campaigns[idx].playerId,
      playerName: patch.playerName ?? campaigns[idx].playerName,
      era: patch.era ?? campaigns[idx].era,
      background: patch.background ?? campaigns[idx].background,
      createdAt: patch.createdAt ?? campaigns[idx].createdAt,
      lastPlayedAt: patch.lastPlayedAt ?? campaigns[idx].lastPlayedAt,
      turnCount: patch.turnCount ?? campaigns[idx].turnCount,
    };
  } else {
    campaigns.unshift(fallback);
  }
  saveRegistry(campaigns);
}
