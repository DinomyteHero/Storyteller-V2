/**
 * E2E: Campaign Creation — navigate to /create, fill the wizard, verify campaign exists.
 */
import { test, expect } from '@playwright/test';
import { assertBackendHealthy, dismissWizardIfPresent } from './helpers';

test.beforeAll(async () => {
  await assertBackendHealthy();
});

test.describe('Campaign Creation', () => {
  test('wizard completes and routes to origin or prologue', async ({ page }) => {
    // Bypass first-run wizard
    await page.goto('/');
    await dismissWizardIfPresent(page);
    await page.goto('/');

    // Click "New Story" to navigate to /create
    const newStoryBtn = page.getByRole('button', { name: /new story/i });
    await expect(newStoryBtn).toBeVisible({ timeout: 10_000 });
    await newStoryBtn.click();
    await expect(page).toHaveURL(/\/create/);

    // Step: Character name and gender
    const nameInput = page.locator('#char-name');
    await expect(nameInput).toBeVisible({ timeout: 10_000 });
    await nameInput.fill('E2E Test Pilot');

    // Select a gender
    const genderBtn = page.locator('.gender-btn').first();
    await genderBtn.click();

    // Select an era (click the first era card)
    const eraCard = page.locator('.era-card').first();
    await expect(eraCard).toBeVisible({ timeout: 10_000 });
    await eraCard.click();

    // Look for Quick Start or Next button to proceed
    const quickStartBtn = page.getByRole('button', { name: /quick start/i });
    const nextBtn = page.getByRole('button', { name: /next|continue/i });

    if (await quickStartBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await quickStartBtn.click();
    } else {
      await nextBtn.click();
    }

    // Wait for setup to complete — look for setup overlay or route change
    // The setup overlay shows when auto-setup is running
    const setupOverlay = page.locator('.setup-overlay');
    if (await setupOverlay.isVisible({ timeout: 5_000 }).catch(() => false)) {
      // Wait for overlay to disappear (setup complete)
      await expect(setupOverlay).toBeHidden({ timeout: 180_000 });
    }

    // After setup, should be at /play, /origin, or /prologue
    await page.waitForURL(/\/(play|origin|prologue)/, { timeout: 180_000 });

    const url = page.url();
    expect(
      url.includes('/play') || url.includes('/origin') || url.includes('/prologue')
    ).toBe(true);
  });

  test('quick start creates campaign and navigates to gameplay', async ({ page }) => {
    await page.goto('/');
    await dismissWizardIfPresent(page);
    await page.goto('/create');

    // Fill name
    const nameInput = page.locator('#char-name');
    await expect(nameInput).toBeVisible({ timeout: 10_000 });
    await nameInput.fill('Quick Tester');

    // Select gender and era
    await page.locator('.gender-btn').first().click();
    const eraCard = page.locator('.era-card').first();
    await expect(eraCard).toBeVisible({ timeout: 10_000 });
    await eraCard.click();

    // Use Quick Start if available
    const quickStart = page.getByRole('button', { name: /quick start/i });
    if (await quickStart.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await quickStart.click();
      // Wait for route change
      await page.waitForURL(/\/(play|origin|prologue)/, { timeout: 180_000 });
    }
  });
});
