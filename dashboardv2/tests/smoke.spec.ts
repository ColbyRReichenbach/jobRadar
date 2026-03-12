import { expect, test } from '@playwright/test';

async function mockLoggedOutApi(page: import('@playwright/test').Page) {
  await page.route('http://localhost:8000/api/auth/refresh', async (route) => {
    await route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Unauthorized' }),
    });
  });
}

async function mockLoggedInApi(page: import('@playwright/test').Page) {
  await page.route('http://localhost:8000/api/auth/refresh', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ access_token: 'test-access-token', token_type: 'bearer' }),
    });
  });

  await page.route('http://localhost:8000/api/auth/me', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: '00000000-0000-0000-0000-000000000001',
        email: 'test-user@apptrail.test',
        name: 'Test User',
        picture: '',
        gmail_connected: true,
        calendar_connected: false,
      }),
    });
  });

  await page.route(/http:\/\/localhost:8000\/api\/jobs(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  await page.route(/http:\/\/localhost:8000\/api\/emails(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });
}

test('renders the login page when unauthenticated', async ({ page }) => {
  await mockLoggedOutApi(page);
  await page.goto('/');

  await expect(page.getByRole('heading', { name: 'AppTrail' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sign in with Google' })).toBeVisible();
  await expect(page.getByText('Track your job applications with ease.')).toBeVisible();
});

test('renders the authenticated app shell with mocked API data', async ({ page }) => {
  await mockLoggedInApi(page);
  await page.goto('/');

  await expect(page.getByRole('heading', { name: 'Pipeline' })).toBeVisible();
  await expect(page.getByText('Track and manage your active job applications.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Inbox' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Conversations' })).toBeVisible();
  await expect(page.getByText('Test User')).toBeVisible();
});

test('auth callback route bootstraps back into the app shell', async ({ page }) => {
  await mockLoggedInApi(page);
  await page.goto('/auth/callback');

  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole('heading', { name: 'Pipeline' })).toBeVisible();
});
