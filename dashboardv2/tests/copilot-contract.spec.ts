import { expect, test } from '@playwright/test';
import { mockLoggedInCopilotApi } from './copilot-test-helpers';

test('opens Copilot, sends a backend-backed message, renders citations, and records feedback', async ({ page }) => {
  const requests = await mockLoggedInCopilotApi(page);
  await page.goto('/');

  await expect(page.getByRole('heading', { name: 'Pipeline' })).toBeVisible();
  await page.getByRole('button', { name: 'Ask AppTrail' }).click();

  const panel = page.getByRole('dialog', { name: 'Ask AppTrail' });
  await expect(panel).toBeVisible();
  await expect(panel.getByRole('heading', { name: 'Where should you focus next?' })).toBeVisible();

  await panel.getByLabel('Ask AppTrail a question').fill('Which applications need follow-up?');
  await panel.getByRole('button', { name: 'Send message' }).click();

  await expect(panel.locator('.whitespace-pre-wrap').filter({ hasText: 'Which applications need follow-up?' })).toBeVisible();
  await expect(panel.getByText('TestCo has an application with no recent recruiter response.')).toBeVisible();
  await expect(panel.getByRole('button', { name: 'Open Application: Data Scientist at TestCo' })).toBeVisible();
  await expect(panel.getByText('Review follow-up timing')).toBeVisible();
  await expect(panel.getByText('Review only')).toBeVisible();

  await panel.getByRole('button', { name: 'Mark answer as helpful' }).click();
  await expect(panel.getByText('Feedback saved')).toBeVisible();

  expect(requests.messages).toEqual([
    {
      content: 'Which applications need follow-up?',
    },
  ]);
  expect(requests.feedback).toEqual([
    {
      rating: 'thumbs_up',
    },
  ]);
});

test('shows a clear limited-state message when backend guardrails reject a request', async ({ page }) => {
  await mockLoggedInCopilotApi(page, {
    messageStatus: 429,
    messageDetail: 'Too many Copilot requests',
  });
  await page.goto('/');

  await page.getByRole('button', { name: 'Ask AppTrail' }).click();
  const panel = page.getByRole('dialog', { name: 'Ask AppTrail' });
  await panel.getByLabel('Ask AppTrail a question').fill('Summarize recruiter conversations');
  await panel.getByRole('button', { name: 'Send message' }).click();

  await expect(panel.getByText('Copilot is paused by request or budget limits. Try again later.')).toBeVisible();
  await expect(panel.getByLabel('Ask AppTrail a question')).toHaveValue('Summarize recruiter conversations');
});
