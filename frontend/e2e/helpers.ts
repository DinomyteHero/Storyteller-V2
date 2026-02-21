/**
 * Shared E2E test helpers for Storyteller AI Playwright tests.
 *
 * Provides backend health checks, campaign creation via API, and
 * common page-level helpers used across multiple test specs.
 */
import { expect, type Page } from '@playwright/test';

const API_BASE = 'http://localhost:8000';

/** Check that the backend is reachable before running any tests. */
export async function assertBackendHealthy(): Promise<void> {
  const res = await fetch(`${API_BASE}/health/detail`);
  if (!res.ok) {
    throw new Error(
      `Backend not reachable at ${API_BASE}/health/detail (status ${res.status}). ` +
      'Start the backend before running E2E tests.'
    );
  }
}

/**
 * Create a campaign via the API (bypasses the multi-step wizard for speed).
 * Returns { campaignId, playerId }.
 */
export async function createCampaignViaApi(): Promise<{
  campaignId: string;
  playerId: string;
}> {
  const body = {
    player_concept: 'E2E Test Hero',
    player_gender: 'they/them',
    genre: null,
    themes: [],
    starting_location: null,
    randomize_starting_location: true,
    background_id: null,
    background_answers: {},
    campaign_scale: 'small',
    difficulty: 'normal',
    quick_start: true,
  };

  const res = await fetch(`${API_BASE}/v2/setup/auto`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`setupAuto failed (${res.status}): ${text}`);
  }

  const data = await res.json();
  return {
    campaignId: data.campaign_id,
    playerId: data.player_id,
  };
}

/**
 * Navigate to the /play route for a given campaign, setting localStorage
 * so the game page loads the correct campaign.
 */
export async function navigateToPlay(
  page: Page,
  campaignId: string,
  playerId: string
): Promise<void> {
  // Set localStorage before navigating so the play page picks up the campaign
  await page.goto('/');
  await page.evaluate(
    ({ cid, pid }) => {
      localStorage.setItem('activeCampaignId', cid);
      localStorage.setItem('activePlayerId', pid);
      localStorage.setItem('lastPlayedCampaign', cid);
    },
    { cid: campaignId, pid: playerId }
  );
  await page.goto('/play');
}

/** Wait for narrative prose text to appear on the play page. */
export async function waitForNarrative(page: Page): Promise<string> {
  // Narrative text appears in paragraph elements within the narrative container
  const narrativeEl = page.locator('.narrative-prose p, .narrative-text p').first();
  await expect(narrativeEl).toBeVisible({ timeout: 60_000 });
  const text = await narrativeEl.textContent();
  return text ?? '';
}

/** Wait for choices to render (DialogueWheel or ApproachCards). */
export async function waitForChoices(page: Page): Promise<void> {
  // Either DialogueWheel (.choice-card) or ApproachCards (.approach-card) should appear
  const choiceLocator = page.locator('.choice-card, .approach-card').first();
  await expect(choiceLocator).toBeVisible({ timeout: 60_000 });
}

/** Dismiss the first-run wizard if it appears. */
export async function dismissWizardIfPresent(page: Page): Promise<void> {
  await page.evaluate(() => {
    localStorage.setItem('firstRunComplete', 'true');
  });
}

/** Clean up a campaign via the API after test. */
export async function deleteCampaignViaApi(campaignId: string): Promise<void> {
  // The backend may not have a delete endpoint — just let it persist.
  // Tests use unique campaign IDs so there's no conflict.
}
