/**
 * Campaign save/load — localStorage-backed campaign registry.
 *
 * Since there's no backend "list campaigns" endpoint, we track
 * campaign IDs locally. Each entry stores just enough info to
 * display in a "Load Campaign" list and resume via the state endpoint.
 */
import { browser } from '$app/environment';

const STORAGE_KEY = 'storyteller-saved-campaigns';
const MAX_SAVED = 20;

export interface SavedCampaign {
  campaignId: string;
  playerId: string;
  playerName: string;
  era: string;
  background: string | null;
  createdAt: string; // ISO timestamp
  lastPlayedAt: string; // ISO timestamp
  turnCount: number;
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
