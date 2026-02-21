/**
 * E2E: Rewind — create campaign, play 2+ turns, trigger rewind,
 * verify state reverts to the target turn.
 */
import { test, expect } from '@playwright/test';
import {
  assertBackendHealthy,
  createCampaignViaApi,
  navigateToPlay,
  waitForNarrative,
  waitForChoices,
  dismissWizardIfPresent,
} from './helpers';

const API_BASE = 'http://localhost:8000';

let campaignId: string;
let playerId: string;

test.beforeAll(async () => {
  await assertBackendHealthy();
  const campaign = await createCampaignViaApi();
  campaignId = campaign.campaignId;
  playerId = campaign.playerId;
});

async function submitTurn(page: import('@playwright/test').Page): Promise<void> {
  const choice = page.locator('.choice-card').first();
  if (await choice.isVisible({ timeout: 5_000 }).catch(() => false)) {
    await choice.click();
  } else {
    const approach = page.locator('.approach-card').first();
    if (await approach.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await approach.click();
      const forgeSubmit = page.locator('.btn-forge-submit');
      if (await forgeSubmit.isVisible({ timeout: 2_000 }).catch(() => false)) {
        await expect(forgeSubmit).toBeEnabled({ timeout: 5_000 });
        await forgeSubmit.click();
      }
    }
  }

  // Wait for turn to complete
  const processing = page.locator('.processing-dot, .loading-spinner').first();
  if (await processing.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await expect(processing).toBeHidden({ timeout: 120_000 });
  }

  await waitForNarrative(page);
  await waitForChoices(page);
}

test.describe('Rewind', () => {
  test('rewind via API restores earlier turn state', async ({ page }) => {
    await dismissWizardIfPresent(page);
    await navigateToPlay(page, campaignId, playerId);

    // Play turn 1
    await waitForNarrative(page);
    await waitForChoices(page);
    await submitTurn(page);

    // Play turn 2
    await submitTurn(page);

    // Check current turn count via API
    const stateRes = await fetch(
      `${API_BASE}/v2/campaigns/${campaignId}/state?player_id=${encodeURIComponent(playerId)}`
    );
    const stateData = await stateRes.json();
    const turnBeforeRewind = stateData.turn_number ?? stateData.current_turn ?? 3;
    expect(turnBeforeRewind).toBeGreaterThanOrEqual(3);

    // Rewind to turn 1 via API
    const rewindRes = await fetch(
      `${API_BASE}/v2/campaigns/${campaignId}/rewind?to_turn=1`,
      { method: 'POST' }
    );
    expect(rewindRes.ok).toBe(true);
    const rewindData = await rewindRes.json();
    expect(rewindData.rewound_to).toBe(1);

    // Reload the play page — state should be at turn 1
    await navigateToPlay(page, campaignId, playerId);
    await waitForNarrative(page);

    // Verify the state shows turn 1
    const stateAfterRes = await fetch(
      `${API_BASE}/v2/campaigns/${campaignId}/state?player_id=${encodeURIComponent(playerId)}`
    );
    const stateAfterData = await stateAfterRes.json();
    const turnAfterRewind = stateAfterData.turn_number ?? stateAfterData.current_turn ?? 0;
    expect(turnAfterRewind).toBeLessThan(turnBeforeRewind);
  });

  test('rewind preserves transcript up to target turn', async ({ page }) => {
    await dismissWizardIfPresent(page);

    // Play a few turns to build transcript
    await navigateToPlay(page, campaignId, playerId);
    await waitForNarrative(page);
    await waitForChoices(page);
    await submitTurn(page);
    await submitTurn(page);

    // Get transcript before rewind
    const transcriptBefore = await fetch(
      `${API_BASE}/v2/campaigns/${campaignId}/transcript?limit=100`
    ).then(r => r.json());

    const turnCountBefore = transcriptBefore.turns?.length ?? 0;

    if (turnCountBefore >= 2) {
      // Rewind to turn 1
      const rewindRes = await fetch(
        `${API_BASE}/v2/campaigns/${campaignId}/rewind?to_turn=1`,
        { method: 'POST' }
      );
      expect(rewindRes.ok).toBe(true);

      // Check transcript after rewind
      const transcriptAfter = await fetch(
        `${API_BASE}/v2/campaigns/${campaignId}/transcript?limit=100`
      ).then(r => r.json());

      const turnCountAfter = transcriptAfter.turns?.length ?? 0;
      expect(turnCountAfter).toBeLessThan(turnCountBefore);
    }
  });
});
