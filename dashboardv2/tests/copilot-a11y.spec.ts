import { expect, test } from '@playwright/test';
import { mockLoggedInCopilotApi, mockLoggedOutApi } from './copilot-test-helpers';

test('does not render Copilot for unauthenticated users', async ({ page }) => {
  await mockLoggedOutApi(page);
  await page.goto('/');

  await expect(page.getByRole('heading', { name: 'AppTrail' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Ask AppTrail' })).toHaveCount(0);
});

test('Copilot launcher and panel expose keyboard-friendly controls', async ({ page }) => {
  await mockLoggedInCopilotApi(page);
  await page.goto('/');

  const launcher = page.getByRole('button', { name: 'Ask AppTrail' });
  await expect(launcher).toBeVisible();
  await launcher.focus();
  await page.keyboard.press('Enter');

  const panel = page.getByRole('dialog', { name: 'Ask AppTrail' });
  await expect(panel).toBeVisible();
  await expect(panel.getByLabel('Ask AppTrail a question')).toBeFocused();
  await expect(panel.getByRole('button', { name: 'Start new Copilot chat' })).toBeVisible();
  await expect(panel.getByRole('button', { name: 'Close Copilot' })).toBeVisible();

  await page.keyboard.press('Escape');
  await expect(panel).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Ask AppTrail' })).toBeVisible();
});

test('mobile Copilot panel fits the viewport without horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockLoggedInCopilotApi(page);
  await page.goto('/');

  await page.getByRole('button', { name: 'Ask AppTrail' }).click();
  const panel = page.getByRole('dialog', { name: 'Ask AppTrail' });
  await expect(panel).toBeVisible();

  await panel.getByRole('button', { name: 'Which applications need follow-up?' }).click();
  await expect(panel.getByText('Data Scientist at TestCo')).toBeVisible();

  const fitsViewport = await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);
  expect(fitsViewport).toBeTruthy();

  const box = await panel.boundingBox();
  expect(box?.width || 0).toBeLessThanOrEqual(390);
});
