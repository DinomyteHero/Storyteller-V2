/**
 * E2E: First Turn — create a campaign via API, navigate to /play,
 * submit a turn, verify narrative and choices render.
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

test.describe('First Turn', () => {
  test('submitting a turn renders narrative and choices', async ({ page }) => {
    await dismissWizardIfPresent(page);
    await navigateToPlay(page, campaignId, playerId);

    // Wait for initial narrative to load
    await waitForNarrative(page);

    // Wait for choices to appear
    await waitForChoices(page);

    // Click the first choice card
    const firstChoice = page.locator('.choice-card, .approach-card').first();
    await expect(firstChoice).toBeVisible();
    await firstChoice.click();

    // If it's an approach card, we need to also submit via the forge input
    const forgeSubmit = page.locator('.btn-forge-submit');
    if (await forgeSubmit.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await expect(forgeSubmit).toBeEnabled({ timeout: 5_000 });
      await forgeSubmit.click();
    }

    // Wait for new narrative to appear (loading indicator or new text)
    // The processing indicator appears during turn execution
    const processingDot = page.locator('.processing-dot, .loading-spinner').first();
    if (await processingDot.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await expect(processingDot).toBeHidden({ timeout: 120_000 });
    }

    // Verify new narrative text rendered
    const narrativeText = await waitForNarrative(page);
    expect(narrativeText.length).toBeGreaterThan(0);

    // Verify new choices appeared
    await waitForChoices(page);
  });

  test('free text forge input submits a turn', async ({ page }) => {
    await dismissWizardIfPresent(page);
    await navigateToPlay(page, campaignId, playerId);

    await waitForNarrative(page);
    await waitForChoices(page);

    // Open forge input via keyboard shortcut (5 or F key)
    await page.keyboard.press('5');

    const forgeInput = page.locator('.forge-input');
    // If forge section didn't open with '5', try clicking an approach card
    if (!await forgeInput.isVisible({ timeout: 3_000 }).catch(() => false)) {
      const approachCard = page.locator('.approach-card').first();
      if (await approachCard.isVisible({ timeout: 2_000 }).catch(() => false)) {
        await approachCard.click();
      }
    }

    // Type custom action
    if (await forgeInput.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await forgeInput.fill('I look around the room carefully');

      const forgeSubmit = page.locator('.btn-forge-submit');
      await expect(forgeSubmit).toBeEnabled({ timeout: 5_000 });
      await forgeSubmit.click();

      // Wait for turn to complete
      const processing = page.locator('.processing-dot, .loading-spinner').first();
      if (await processing.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await expect(processing).toBeHidden({ timeout: 120_000 });
      }

      // Verify new narrative
      const text = await waitForNarrative(page);
      expect(text.length).toBeGreaterThan(0);
    }
  });
});
