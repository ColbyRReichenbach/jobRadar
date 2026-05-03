import { devices, expect, test, type Page } from '@playwright/test';

type MockAlert = {
  id: string;
  alert_type: string;
  title: string;
  body: string | null;
  action_url: string | null;
  read: boolean;
  created_at: string | null;
};

type MockProfile = {
  id: string;
  linkedin_url: string | null;
  skills: string[];
  education: Array<string | Record<string, unknown>>;
  experience_years: number | null;
  tools: string[];
  certifications: string[];
  resume_text: string | null;
  updated_at: string | null;
} | null;

type MockContact = {
  id: string;
  name: string | null;
  email: string | null;
  title: string | null;
  company: string | null;
  source: string;
  reached_out: boolean;
  response_received: boolean;
  linkedin_url: string | null;
  phone_number?: string | null;
};

type MockNetworkDetail = {
  contact: {
    id?: string;
    application_id?: string | null;
    name?: string | null;
    title?: string | null;
    email?: string | null;
    company?: string | null;
    company_id?: string | null;
    phone_number?: string | null;
    linkedin_url?: string | null;
    source?: string | null;
  };
  emails: Array<{
    id: string;
    thread_id?: string;
    email_type?: string;
    sender?: string;
    sender_email?: string;
    subject?: string;
    snippet?: string;
    received_at?: string;
    is_from_user?: boolean;
  }>;
  applications: Array<{
    id: string;
    company: string;
    role_title: string;
  }>;
};

type MockState = {
  user?: Record<string, unknown>;
  jobs?: any[];
  emails?: any[];
  profile?: MockProfile;
  alerts?: MockAlert[];
  networkContacts?: MockContact[];
  networkDetails?: Record<string, MockNetworkDetail>;
  contactDistinctPairs?: string[][];
};

async function mockLoggedOutApi(page: Page) {
  await page.route('http://localhost:8000/api/auth/refresh', async (route) => {
    await route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Unauthorized' }),
    });
  });
}

async function mockLoggedInApi(page: Page, initialState: MockState = {}) {
  await page.addInitScript(() => {
    window.localStorage.setItem('apptrail-auth-session', 'true');
  });

  const state = {
    user: {
      id: '00000000-0000-0000-0000-000000000001',
      email: 'test-user@apptrail.test',
      name: 'Test User',
      picture: '',
      gmail_connected: true,
      calendar_connected: false,
      data_consent_accepted_at: '2026-03-12T12:00:00Z',
    },
    jobs: [] as any[],
    emails: [] as any[],
    profile: null as MockProfile,
    alerts: [] as MockAlert[],
    networkContacts: [] as MockContact[],
    networkDetails: {} as Record<string, MockNetworkDetail>,
    contactDistinctPairs: [] as string[][],
    ...initialState,
  };

  await page.route('http://localhost:8000/api/**', async (route) => {
    const url = new URL(route.request().url());
    const method = route.request().method();
    const path = url.pathname;

    const json = async () => {
      try {
        return await route.request().postDataJSON();
      } catch {
        return null;
      }
    };

    if (path === '/api/auth/refresh' && method === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ access_token: 'test-access-token', token_type: 'bearer' }),
      });
      return;
    }

    if (path === '/api/auth/exchange' && method === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ access_token: 'test-access-token', token_type: 'bearer' }),
      });
      return;
    }

    if (path === '/api/auth/me' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(state.user),
      });
      return;
    }

    if (path === '/api/consent' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          consents: {
            core: true,
            ai_processing: true,
            third_party_enrichment: true,
            web_research: false,
          },
          accepted_at: '2026-03-12T12:00:00Z',
        }),
      });
      return;
    }

    if (path === '/api/consent' && method === 'PUT') {
      const body = await json();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          consents: {
            core: body?.core ?? true,
            ai_processing: body?.ai_processing ?? true,
            third_party_enrichment: body?.third_party_enrichment ?? true,
            web_research: body?.web_research ?? false,
          },
          accepted_at: '2026-03-12T12:00:00Z',
        }),
      });
      return;
    }

    if (path === '/api/jobs' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(state.jobs),
      });
      return;
    }

    if (path === '/api/emails' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(state.emails),
      });
      return;
    }

    if (path === '/api/profile' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(state.profile),
      });
      return;
    }

    if (path === '/api/profile' && method === 'PATCH') {
      const body = await json();
      state.profile = {
        id: state.profile?.id || 'profile-1',
        linkedin_url: body?.linkedin_url ?? null,
        skills: body?.skills ?? [],
        education: body?.education ?? [],
        experience_years: body?.experience_years ?? null,
        tools: body?.tools ?? [],
        certifications: body?.certifications ?? [],
        resume_text: body?.resume_text ?? null,
        updated_at: '2026-03-12T12:00:00Z',
      };
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(state.profile),
      });
      return;
    }

    if (path === '/api/profile' && method === 'DELETE') {
      state.profile = null;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok' }),
      });
      return;
    }

    if (path === '/api/resume/parse' && method === 'POST') {
      const body = await json();
      state.profile = {
        id: state.profile?.id || 'profile-1',
        linkedin_url: state.profile?.linkedin_url ?? null,
        skills: ['React', 'TypeScript'],
        education: ['State University — B.S. Computer Science — 2022'],
        experience_years: 4,
        tools: ['Vite', 'Playwright'],
        certifications: [],
        resume_text: body?.text ?? '',
        updated_at: '2026-03-12T12:00:00Z',
      };
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(state.profile),
      });
      return;
    }

    if (path === '/api/alerts' && method === 'GET') {
      const unreadOnly = url.searchParams.get('unread') === 'true';
      const alerts = unreadOnly ? state.alerts.filter((alert) => !alert.read) : state.alerts;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(alerts),
      });
      return;
    }

    if (path === '/api/alerts/count' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ unread: state.alerts.filter((alert) => !alert.read).length }),
      });
      return;
    }

    if (path === '/api/alerts/read-all' && method === 'PATCH') {
      const unread = state.alerts.filter((alert) => !alert.read).length;
      state.alerts = state.alerts.map((alert) => ({ ...alert, read: true }));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ updated: unread }),
      });
      return;
    }

    if (path.startsWith('/api/alerts/') && method === 'PATCH') {
      const alertId = path.split('/').pop();
      state.alerts = state.alerts.map((alert) => (
        alert.id === alertId ? { ...alert, read: true } : alert
      ));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok' }),
      });
      return;
    }

    if (path === '/api/network' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(state.networkContacts),
      });
      return;
    }

    if (path.startsWith('/api/network/') && method === 'GET') {
      const email = decodeURIComponent(path.replace('/api/network/', ''));
      const detail = state.networkDetails[email];
      if (!detail) {
        await route.fulfill({
          status: 404,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Not found' }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(detail),
      });
      return;
    }

    if (path === '/api/contacts/duplicates/check' && method === 'POST') {
      const body = await json();
      const email = body?.email ? String(body.email).trim().toLowerCase() : null;
      const name = body?.name ? String(body.name).trim().toLowerCase() : null;
      const excludeId = body?.contact_id ? String(body.contact_id) : null;
      const contacts = state.networkContacts.filter((contact) => contact.id !== excludeId);

      const hardMatches = email
        ? contacts.filter((contact) => (contact.email || '').toLowerCase() === email)
        : [];
      if (hardMatches.length > 0) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            duplicate_type: 'hard',
            message: 'This email already exists in your contacts.',
            matches: hardMatches,
          }),
        });
        return;
      }

      const softMatches = name
        ? contacts.filter((contact) => {
            if ((contact.name || '').trim().toLowerCase() !== name) return false;
            if (!email || !contact.email) return true;
            const pair = [email, String(contact.email).trim().toLowerCase()].sort();
            return !state.contactDistinctPairs.some((existing) => existing[0] === pair[0] && existing[1] === pair[1]);
          })
        : [];
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          duplicate_type: softMatches.length > 0 ? 'soft' : 'none',
          message: softMatches.length > 0 ? 'We found a similarly named contact.' : null,
          matches: softMatches,
        }),
      });
      return;
    }

    if (path === '/api/contacts/duplicates/keep-separate' && method === 'POST') {
      const body = await json();
      const pair = [
        String(body?.email || '').trim().toLowerCase(),
        String(body?.match_email || '').trim().toLowerCase(),
      ].sort();
      if (pair[0] && pair[1] && pair[0] !== pair[1]) {
        state.contactDistinctPairs.push(pair);
      }
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok' }),
      });
      return;
    }

    if (path === '/api/contacts' && method === 'POST') {
      const body = await json();
      const id = `contact-${state.networkContacts.length + 1}`;
      const created = {
        id,
        name: body?.name ?? null,
        email: body?.email ? String(body.email).trim().toLowerCase() : null,
        title: body?.title ?? null,
        company: body?.company_name ?? null,
        source: 'manual',
        reached_out: false,
        response_received: false,
        linkedin_url: body?.linkedin_url ?? null,
        phone_number: body?.phone_number ?? null,
      };
      state.networkContacts = [created, ...state.networkContacts];
      if (created.email) {
        state.networkDetails[created.email] = {
          contact: {
            id,
            name: created.name,
            email: created.email,
            title: created.title,
            company: created.company,
            phone_number: created.phone_number,
            linkedin_url: created.linkedin_url,
            source: 'manual',
          },
          emails: [],
          applications: [],
        };
      }
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(created),
      });
      return;
    }

    if (path === '/api/contacts/merge' && method === 'POST') {
      const body = await json();
      const targetId = String(body?.target_contact_id);
      const sourceId = body?.source_contact_id ? String(body.source_contact_id) : null;
      const target = state.networkContacts.find((contact) => contact.id === targetId);
      if (!target) {
        await route.fulfill({
          status: 404,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Target contact not found' }),
        });
        return;
      }

      Object.assign(target, {
        name: body?.name ?? target.name,
        title: body?.title ?? target.title,
        email: body?.email ? String(body.email).trim().toLowerCase() : target.email,
        company: body?.company_name ?? target.company,
        phone_number: body?.phone_number ?? target.phone_number,
        linkedin_url: body?.linkedin_url ?? target.linkedin_url,
        source: target.source || 'manual',
      });

      if (sourceId) {
        const source = state.networkContacts.find((contact) => contact.id === sourceId);
        if (source) {
          state.networkContacts = state.networkContacts.filter((contact) => contact.id !== sourceId);
          if (source.email) {
            delete state.networkDetails[source.email];
          }
        }
      }

      if (target.email) {
        state.networkDetails[target.email] = {
          contact: {
            id: target.id,
            name: target.name,
            email: target.email,
            title: target.title,
            company: target.company,
            phone_number: target.phone_number,
            linkedin_url: target.linkedin_url,
            source: target.source,
          },
          emails: [],
          applications: [],
        };
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(target),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  return state;
}

test('renders the login page when unauthenticated', async ({ page }) => {
  await mockLoggedOutApi(page);
  await page.goto('/');

  await expect(page.getByRole('heading', { name: 'AppTrail' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sign in with Google' })).toBeVisible();
  await expect(page.getByText('Track your job applications with ease.')).toBeVisible();
});

test.describe('desktop app flows', () => {
  test('renders the authenticated app shell with mocked API data', async ({ page }) => {
    await mockLoggedInApi(page);
    await page.goto('/');

    await expect(page.getByRole('heading', { name: 'Pipeline' })).toBeVisible();
    await expect(page.getByText('Track and manage your active job applications.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Inbox' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Conversations' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Classifier Audit' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Extraction Reports' })).toHaveCount(0);
    await expect(page.getByText('Test User')).toBeVisible();
  });

  test('shows admin navigation only for admin users', async ({ page }) => {
    await mockLoggedInApi(page, {
      user: {
        id: '00000000-0000-0000-0000-000000000001',
        email: 'admin@apptrail.test',
        name: 'Admin User',
        picture: '',
        gmail_connected: true,
        calendar_connected: false,
        data_consent_accepted_at: '2026-03-12T12:00:00Z',
        is_admin: true,
      },
    });
    await page.goto('/');

    await expect(page.getByRole('button', { name: 'Classifier Audit' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Extraction Reports' })).toBeVisible();
  });

  test('auth callback route bootstraps back into the app shell', async ({ page }) => {
    await mockLoggedInApi(page);
    await page.goto('/auth/callback?code=test-auth-code');

    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole('heading', { name: 'Pipeline' })).toBeVisible();
  });

  test('profile page supports compact display, save, and clear', async ({ page }) => {
    await mockLoggedInApi(page, {
      profile: {
        id: 'profile-1',
        linkedin_url: 'https://linkedin.com/in/test-user',
        skills: ['React', 'TypeScript'],
        education: ['State University — B.S. Computer Science — 2022'],
        experience_years: 4,
        tools: ['Vite'],
        certifications: [],
        resume_text: 'Existing resume text',
        updated_at: '2026-03-12T12:00:00Z',
      },
    });

    await page.goto('/');
    await page.getByRole('button', { name: /Test User/ }).click();

    await expect(page.getByRole('heading', { name: 'Profile' })).toBeVisible();
    await expect(page.getByText('https://linkedin.com/in/test-user')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Certifications' })).toHaveCount(0);

    await page.getByRole('button', { name: 'Edit Profile' }).click();
    await page.getByLabel('LinkedIn URL').fill('https://linkedin.com/in/updated-user');
    await page.getByLabel('Years of Experience').fill('6');
    await page.getByRole('button', { name: 'Save' }).click();

    await expect(page.getByText('Profile saved.')).toBeVisible();
    await expect(page.getByText('https://linkedin.com/in/updated-user')).toBeVisible();
    await expect(page.getByText('6 years')).toBeVisible();

    page.once('dialog', (dialog) => dialog.accept());
    await page.getByRole('button', { name: 'Edit Profile' }).click();
    await page.getByRole('button', { name: 'Clear' }).click();
    await expect(page.getByText('Profile cleared.')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Build your profile' })).toBeVisible();
  });

  test('notification center marks all read and deep-links into a network contact', async ({ page }) => {
    await mockLoggedInApi(page, {
      alerts: [
        {
          id: 'alert-network-1',
          alert_type: 'network_contact',
          title: 'Added Alex Recruiter to your network',
          body: 'Open the contact card to review details.',
          action_url: '/network?email=alex@testco.com',
          read: false,
          created_at: new Date().toISOString(),
        },
        {
          id: 'alert-update-2',
          alert_type: 'job_update',
          title: 'Status update from TestCo',
          body: 'Your application moved to interview review.',
          action_url: '/emails?email_id=email-1&tab=emails',
          read: false,
          created_at: new Date().toISOString(),
        },
      ],
      networkContacts: [
        {
          id: 'contact-1',
          name: 'Alex Recruiter',
          email: 'alex@testco.com',
          title: 'Senior Recruiter',
          company: 'TestCo',
          source: 'email',
          reached_out: false,
          response_received: true,
          linkedin_url: 'https://linkedin.com/in/alex-recruiter',
          phone_number: '555-111-2222',
        },
      ],
      networkDetails: {
        'alex@testco.com': {
          contact: {
            id: 'contact-1',
            name: 'Alex Recruiter',
            title: 'Senior Recruiter',
            email: 'alex@testco.com',
            company: 'TestCo',
            phone_number: '555-111-2222',
            linkedin_url: 'https://linkedin.com/in/alex-recruiter',
            source: 'email',
          },
          emails: [],
          applications: [],
        },
      },
    });

    const alertsLoaded = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname === '/api/alerts' && response.request().method() === 'GET';
    });

    await page.goto('/');
    await alertsLoaded;
    await expect(page.getByText('Open the contact card to review details.')).toHaveCount(0);
    await expect(page.getByText('Status update from TestCo')).toHaveCount(0);

    await page.getByRole('button', { name: 'Open notifications' }).click();
    await expect(page.getByText('Notifications')).toBeVisible();
    await expect(page.getByText('2 unread')).toBeVisible();

    await page.getByRole('button', { name: 'Mark all read' }).click();
    await expect(page.getByText('0 unread')).toBeVisible();

    await page.getByRole('button', { name: /Added Alex Recruiter to your network/ }).click();
    await expect(page.getByRole('heading', { name: 'Network' })).toBeVisible();
    const contactDialog = page.getByRole('dialog');
    await expect(contactDialog.locator('h2', { hasText: 'Alex Recruiter' })).toBeVisible();
    await expect(contactDialog.getByText('Senior Recruiter')).toBeVisible();
    await expect(contactDialog.locator('div').filter({ hasText: /^TestCo$/ }).first()).toBeVisible();
  });

  test('device-local notification settings hydrate from local storage', async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem('apptrail:local-notification-prefs', JSON.stringify({
        browser_notifications_enabled: true,
        quiet_hours_enabled: true,
        quiet_hours_start: 21,
        quiet_hours_end: 6,
      }));
    });
    await mockLoggedInApi(page);

    await page.goto('/');
    await page.getByRole('button', { name: 'Settings' }).click();
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();

    await page.reload();
    const storedPrefs = await page.evaluate(() => window.localStorage.getItem('apptrail:local-notification-prefs'));
    expect(storedPrefs).not.toBeNull();
    expect(JSON.parse(storedPrefs || '{}')).toMatchObject({
      quiet_hours_enabled: true,
      quiet_hours_start: 21,
      quiet_hours_end: 6,
    });
  });

  test('network duplicate review supports keep separate and merge', async ({ page }) => {
    await mockLoggedInApi(page, {
      networkContacts: [
        {
          id: 'contact-existing',
          name: 'Audrey Lane',
          email: 'audrey.one@example.com',
          title: 'Recruiter',
          company: 'Acme',
          source: 'manual',
          reached_out: false,
          response_received: false,
          linkedin_url: null,
          phone_number: null,
        },
      ],
      networkDetails: {
        'audrey.one@example.com': {
          contact: {
            id: 'contact-existing',
            name: 'Audrey Lane',
            title: 'Recruiter',
            email: 'audrey.one@example.com',
            company: 'Acme',
            source: 'manual',
          },
          emails: [],
          applications: [],
        },
      },
    });

    await page.goto('/');
    await page.getByRole('button', { name: 'Network' }).click();
    await page.getByRole('button', { name: 'Add Contact' }).click();
    await page.getByLabel('Name').fill('Audrey Lane');
    await page.getByLabel('Email').fill('audrey.two@example.com');

    await expect(page.getByText('We found a similarly named contact.')).toBeVisible();
    await page.getByRole('button', { name: 'Keep separate' }).click();
    await expect(page.getByText('2 results')).toBeVisible();
    await page.getByLabel('Close contact details').click();

    await page.getByRole('button', { name: 'Add Contact' }).click();
    await page.getByLabel('Name').fill('Audrey Lane');
    await page.getByLabel('Email').fill('audrey.three@example.com');
    await page.getByLabel('Title').fill('Senior Recruiter');
    await page.getByLabel('Company').fill('Acme');

    await expect(page.getByText('We found a similarly named contact.')).toBeVisible();
    await page.getByRole('button', { name: 'Merge with this' }).first().click();
    await expect(page.getByRole('heading', { name: 'Merge Contacts' })).toBeVisible();
    await page.getByRole('radio', { name: /Current form/ }).nth(1).check();
    await page.getByRole('button', { name: 'Confirm Merge' }).click();

    const detail = page.getByRole('dialog');
    await expect(detail.getByText('Senior Recruiter')).toBeVisible();
  });

  test('conversation detail wraps long message bodies without hiding the desktop thread list', async ({ page }) => {
    const longLinkedInUrl = `https://www.linkedin.com/comm/messaging/thread/${'apptrail-long-token-'.repeat(80)}?midToken=${'AQC'.repeat(120)}`;

    await mockLoggedInApi(page, {
      emails: [
        {
          id: 'conversation-long-body-1',
          thread_id: 'thread-long-body',
          application_id: 'job-1',
          sender: 'Sharron Vogler',
          sender_email: 'messaging-digest-noreply@linkedin.com',
          subject: 'Sharron just messaged you',
          snippet: 'You have 1 new message from Sharron Vogler.',
          body: `You have 1 new message\n\nView message: ${longLinkedInUrl}\n\nReply from LinkedIn when you are ready.`,
          received_at: '2026-04-15T16:57:00Z',
          classification: 'conversation',
          email_type: 'conversation',
          action_needed: true,
          is_from_user: false,
          company_name: 'LinkedIn',
          sender_domain: 'linkedin.com',
          resolved: false,
        },
      ],
      jobs: [
        {
          id: 'job-1',
          company: 'LinkedIn',
          role_title: 'Data Scientist',
          status: 'applied',
          created_at: '2026-04-15T16:57:00Z',
        },
      ],
    });

    await page.goto('/');
    await page.getByRole('button', { name: 'Conversations' }).click();
    await page.getByText('Sharron Vogler').first().click();

    await expect(page.getByPlaceholder('Search messages, people, or companies...')).toBeVisible();
    await expect(page.locator('h2', { hasText: 'Sharron just messaged you' })).toBeVisible();
    await expect(page.getByText(longLinkedInUrl)).toBeVisible();

    const fitsViewport = await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);
    expect(fitsViewport).toBeTruthy();
  });
});

test.describe('mobile viewport flows', () => {
  const pixel7 = devices['Pixel 7'];
  test.use({
    viewport: pixel7.viewport,
    userAgent: pixel7.userAgent,
    deviceScaleFactor: pixel7.deviceScaleFactor,
    isMobile: pixel7.isMobile,
    hasTouch: pixel7.hasTouch,
  });

  test('network detail and conversation views stay navigable without horizontal overflow', async ({ page }) => {
    await mockLoggedInApi(page, {
      emails: [
        {
          id: 'conversation-email-1',
          thread_id: 'thread-1',
          application_id: 'job-1',
          sender: 'Alex Recruiter',
          sender_email: 'alex@testco.com',
          subject: 'Interview follow-up for a very long subject that still needs to wrap correctly on mobile',
          snippet: 'Thanks for speaking with us. Here is a long update that should stay inside the card on smaller screens without overflowing the viewport.',
          body: 'Thanks for speaking with us. Here is a long update that should stay inside the card on smaller screens without overflowing the viewport.\n\nPlease review the next steps and let us know if you are available.',
          received_at: '2026-03-12T12:00:00Z',
          classification: 'conversation',
          email_type: 'conversation',
          action_needed: true,
          is_from_user: false,
          company_name: 'TestCo',
          sender_domain: 'testco.com',
          resolved: false,
        },
      ],
      jobs: [
        {
          id: 'job-1',
          company: 'TestCo',
          role_title: 'Platform Engineer',
          status: 'applied',
          created_at: '2026-03-12T12:00:00Z',
        },
      ],
      networkContacts: [
        {
          id: 'contact-1',
          name: 'Alex Recruiter',
          email: 'alex@testco.com',
          title: 'Senior Recruiter',
          company: 'TestCo',
          source: 'email',
          reached_out: false,
          response_received: true,
          linkedin_url: 'https://linkedin.com/in/alex-recruiter',
          phone_number: '555-111-2222',
        },
      ],
      networkDetails: {
        'alex@testco.com': {
          contact: {
            id: 'contact-1',
            name: 'Alex Recruiter',
            title: 'Senior Recruiter',
            email: 'alex@testco.com',
            company: 'TestCo',
            phone_number: '555-111-2222',
            linkedin_url: 'https://linkedin.com/in/alex-recruiter',
            source: 'email',
          },
          emails: [
            {
              id: 'conversation-email-1',
              thread_id: 'thread-1',
              email_type: 'conversation',
              sender: 'Alex Recruiter',
              sender_email: 'alex@testco.com',
              subject: 'Interview follow-up for a very long subject that still needs to wrap correctly on mobile',
              snippet: 'Thanks for speaking with us. Here is a long update that should stay inside the card on smaller screens without overflowing the viewport.',
              received_at: '2026-03-12T12:00:00Z',
            },
          ],
          applications: [
            {
              id: 'job-1',
              company: 'TestCo',
              role_title: 'Platform Engineer',
            },
          ],
        },
      },
    });

    await page.goto('/');

    await page.getByRole('button', { name: 'Open navigation menu' }).click();
    await page.getByRole('button', { name: 'Network' }).click();
    await page.getByRole('button', { name: /Open contact details for Alex Recruiter/ }).click();
    const contactDialog = page.getByRole('dialog');
    await expect(contactDialog.locator('h2', { hasText: 'Alex Recruiter' })).toBeVisible();
    await expect(contactDialog.getByRole('link', { name: /555-111-2222/ })).toBeVisible();

    const networkFitsViewport = await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);
    expect(networkFitsViewport).toBeTruthy();

    await page.getByRole('button', { name: 'Close contact details' }).click();
    await page.getByRole('button', { name: 'Open navigation menu' }).click();
    await page.getByRole('button', { name: 'Conversations' }).click();
    await page.getByText('Alex Recruiter').first().click();
    await expect(page.locator('h2', { hasText: 'Interview follow-up for a very long subject that still needs to wrap correctly on mobile' })).toBeVisible();
    await expect(page.getByText('Please review the next steps and let us know if you are available.')).toBeVisible();

    const conversationFitsViewport = await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);
    expect(conversationFitsViewport).toBeTruthy();
  });
});
