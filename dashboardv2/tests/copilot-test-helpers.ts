import { type Page } from '@playwright/test';

type MockCopilotOptions = {
  user?: Record<string, unknown>;
  messageStatus?: number;
  messageDetail?: string;
  assistantContent?: string;
};

export type CopilotMockRequests = {
  messages: Array<Record<string, unknown>>;
  feedback: Array<Record<string, unknown>>;
};

export async function mockLoggedOutApi(page: Page) {
  await page.route('http://localhost:8000/api/**', async (route) => {
    await route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Unauthorized' }),
    });
  });
}

export async function mockLoggedInCopilotApi(
  page: Page,
  options: MockCopilotOptions = {}
): Promise<CopilotMockRequests> {
  await page.addInitScript(() => {
    window.localStorage.setItem('apptrail-auth-session', 'true');
  });

  const requests: CopilotMockRequests = {
    messages: [],
    feedback: [],
  };

  const now = '2026-05-02T14:30:00Z';
  const user = {
    id: '00000000-0000-0000-0000-000000000001',
    email: 'test-user@apptrail.test',
    name: 'Test User',
    picture: '',
    gmail_connected: true,
    calendar_connected: false,
    data_consent_accepted_at: '2026-03-12T12:00:00Z',
    ...options.user,
  };
  const conversation = {
    id: 'copilot-conversation-1',
    title: 'Which applications need follow-up?',
    status: 'active',
    created_at: now,
    updated_at: now,
    last_message_at: now,
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

    if (path === '/api/auth/me' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(user),
      });
      return;
    }

    if (path === '/api/jobs' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
      return;
    }

    if (path === '/api/emails' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
      return;
    }

    if (path === '/api/alerts/count' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ unread: 0 }),
      });
      return;
    }

    if (path === '/api/alerts' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
      return;
    }

    if (path === '/api/copilot/conversations' && method === 'POST') {
      const body = await json();
      conversation.title = body?.title || conversation.title;
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({ conversation }),
      });
      return;
    }

    if (path === '/api/copilot/conversations' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ conversations: [conversation] }),
      });
      return;
    }

    if (path === '/api/copilot/conversations/copilot-conversation-1/messages' && method === 'POST') {
      const body = await json();
      requests.messages.push(body || {});

      if (options.messageStatus) {
        await route.fulfill({
          status: options.messageStatus,
          contentType: 'application/json',
          body: JSON.stringify({ detail: options.messageDetail || 'Copilot request failed.' }),
        });
        return;
      }

      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          conversation: {
            ...conversation,
            title: String(body?.content || conversation.title).slice(0, 80),
            last_message_at: now,
            updated_at: now,
          },
          user_message: {
            id: 'copilot-user-1',
            conversation_id: conversation.id,
            role: 'user',
            content: body?.content,
            citations: [],
            suggested_actions: [],
            metadata: {},
            model_call_id: null,
            created_at: now,
          },
          assistant_message: {
            id: 'copilot-assistant-1',
            conversation_id: conversation.id,
            role: 'assistant',
            content: options.assistantContent || 'TestCo has an application with no recent recruiter response. Prioritize a short follow-up.',
            citations: [
              {
                document_id: 'search-doc-1',
                source_type: 'application',
                source_id: 'job-1',
                title: 'Data Scientist at TestCo',
                snippet: 'Applied three weeks ago; no follow-up logged yet.',
              },
            ],
            suggested_actions: [
              {
                title: 'Review follow-up timing',
                description: 'Check the application and decide whether to draft a recruiter note.',
                action_type: 'read_only_suggestion',
                requires_confirmation: true,
                read_only: true,
              },
            ],
            metadata: {
              mode: 'search_fallback',
              model: null,
              prompt_version: null,
            },
            model_call_id: null,
            created_at: now,
          },
        }),
      });
      return;
    }

    if (path === '/api/copilot/messages/copilot-assistant-1/feedback' && method === 'POST') {
      const body = await json();
      requests.feedback.push(body || {});
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          feedback: {
            id: 'feedback-1',
            message_id: 'copilot-assistant-1',
            rating: body?.rating,
            notes: body?.notes || null,
            created_at: now,
          },
        }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  return requests;
}
