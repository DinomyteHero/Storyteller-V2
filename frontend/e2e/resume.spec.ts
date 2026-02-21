/**
 * E2E: Resume Campaign — create campaign, play a turn, navigate away,
 * then resume and verify state is restored.
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

let campaignId: string;
let playerId: string;

test.beforeAll(async () => {
  await assertBackendHealthy();
  const campaign = await createCampaignViaApi();
  campaignId = campaign.campaignId;
  playerId = campaign.playerId;
});

test.describe('Resume Campaign', () => {
  test('resuming a campaign restores game state', async ({ page }) => {
    await dismissWizardIfPresent(page);

    // Play one turn
    await navigateToPlay(page, campaignId, playerId);
    await waitForNarrative(page);
    await waitForChoices(page);

    // Submit a turn
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

    // Navigate away to home page
    await page.goto('/');

    // Check that "Continue Story" button appears (campaign was last played)
    const continueBtn = page.getByRole('button', { name: /continue story/i });
    await expect(continueBtn).toBeVisible({ timeout: 10_000 });

    // Click Continue Story
    await continueBtn.click();

    // Should route to /play
    await page.waitForURL(/\/play/, { timeout: 30_000 });

    // Verify narrative loads (state restored)
    const text = await waitForNarrative(page);
    expect(text.length).toBeGreaterThan(0);

    // Verify choices appear
    await waitForChoices(page);
  });

  test('load campaign modal shows saved campaigns', async ({ page }) => {
    await dismissWizardIfPresent(page);
    await page.goto('/');

    // Set lastPlayedCampaign so the home page knows about it
    await page.evaluate(
      ({ cid, pid }) => {
        localStorage.setItem('lastPlayedCampaign', cid);
        localStorage.setItem('activeCampaignId', cid);
        localStorage.setItem('activePlayerId', pid);
      },
      { cid: campaignId, pid: playerId }
    );
    await page.goto('/');

    // Click "Load Campaign" button
    const loadBtn = page.getByRole('button', { name: /load campaign/i });
    if (await loadBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await loadBtn.click();

      // Modal should appear
      const modal = page.locator('.modal-overlay');
      await expect(modal).toBeVisible({ timeout: 5_000 });

      // Should show at least one campaign entry
      const entry = page.locator('.campaign-entry, .campaign-card').first();
      await expect(entry).toBeVisible({ timeout: 10_000 });
    }
  });
});
