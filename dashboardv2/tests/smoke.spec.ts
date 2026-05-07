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
  researchProfiles?: any[];
  researchRuns?: any[];
  interviews?: any[];
  interviewSuggestions?: any[];
  gmailAuditRows?: any[];
  sourcePrivateLinks?: any[];
  adminJobSources?: any[];
  adminSourceHealth?: any;
  adminSourceUsage?: any[];
  searchResponse?: any;
  profile?: MockProfile;
  alerts?: MockAlert[];
  networkContacts?: MockContact[];
  networkSuggestions?: any[];
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
    researchProfiles: [] as any[],
    researchRuns: [] as any[],
    interviews: [] as any[],
    interviewSuggestions: [] as any[],
    gmailAuditRows: [] as any[],
    sourcePrivateLinks: [] as any[],
    adminJobSources: [] as any[],
    adminSourceHealth: null as any,
    adminSourceUsage: [] as any[],
    searchResponse: null as any,
    profile: null as MockProfile,
    alerts: [] as MockAlert[],
    networkContacts: [] as MockContact[],
    networkSuggestions: [] as any[],
    networkDetails: {} as Record<string, MockNetworkDetail>,
    contactDistinctPairs: [] as string[][],
    ...initialState,
  };
  const copilotConversation = {
    id: 'radar-setup-conversation',
    title: 'Help me set up a Radar tracker.',
    status: 'active',
    created_at: '2026-05-02T14:30:00Z',
    updated_at: '2026-05-02T14:30:00Z',
    last_message_at: '2026-05-02T14:30:00Z',
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
            source_intelligence: false,
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
            source_intelligence: body?.source_intelligence ?? false,
          },
          accepted_at: '2026-03-12T12:00:00Z',
        }),
      });
      return;
    }

    if (path === '/api/settings/source-intelligence/private-links' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(state.sourcePrivateLinks),
      });
      return;
    }

    if (path.startsWith('/api/settings/source-intelligence/private-links/') && method === 'DELETE') {
      const linkId = path.split('/').pop();
      state.sourcePrivateLinks = state.sourcePrivateLinks.filter((link) => link.id !== linkId);
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok' }),
      });
      return;
    }

    if (path === '/api/settings/source-intelligence/reprocess' && method === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ links_stored: state.sourcePrivateLinks.length, discovery_events: 0 }),
      });
      return;
    }

    if (path === '/api/notifications/preferences' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          sms_enabled: false,
          sms_phone: null,
          weekly_digest_enabled: false,
          radar_updates_enabled: true,
          inbox_updates_enabled: true,
          conversations_enabled: true,
          network_enabled: true,
          interviews_enabled: true,
          followups_enabled: true,
          listings_enabled: true,
          browser_notifications_enabled: false,
          quiet_hours_enabled: false,
          quiet_hours_start: null,
          quiet_hours_end: null,
        }),
      });
      return;
    }

    if (path === '/api/notifications/preferences' && method === 'PUT') {
      const body = await json();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body || {}),
      });
      return;
    }

    if (path === '/api/auth/api-key' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ has_api_key: false, last4: null, created_at: null, last_used_at: null }),
      });
      return;
    }

    if (path === '/api/gmail/sync/audit' && method === 'GET') {
      const limit = Number(url.searchParams.get('limit') || '50');
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(state.gmailAuditRows.slice(0, limit)),
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

    if (path === '/api/emails/feedback' && method === 'POST') {
      const body = await json();
      state.emails = state.emails.map((email) => {
        if (email.id !== body?.email_id) return email;
        if (body?.corrected_route === 'filter') {
          return { ...email, hidden: true, collapsed: true, classification: 'not_relevant', email_type: null };
        }
        if (body?.corrected_route === 'conversation') {
          return { ...email, hidden: true, email_type: 'conversation', classification: 'conversation' };
        }
        if (body?.corrected_route === 'application_inbox') {
          return {
            ...email,
            hidden: true,
            email_type: 'decision',
            classification: body?.corrected_subtype === 'interview_request' ? 'interview_request' : 'job_update',
          };
        }
        return email;
      });
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok', feedback_id: 'feedback-1' }),
      });
      return;
    }

    if (path === '/api/interviews' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(state.interviews),
      });
      return;
    }

    if (path === '/api/interviews' && method === 'POST') {
      const body = await json();
      const created = {
        id: `interview-${state.interviews.length + 1}`,
        application_id: body?.application_id ?? null,
        interview_type: body?.interview_type ?? 'phone',
        scheduled_at: body?.scheduled_at ?? null,
        duration_minutes: body?.duration_minutes ?? null,
        interviewer_name: body?.interviewer_name ?? null,
        interviewer_email: body?.interviewer_email ?? null,
        location_or_link: body?.location_or_link ?? null,
        notes: body?.notes ?? null,
        outcome: 'pending',
        created_at: '2026-05-03T12:00:00Z',
      };
      state.interviews = [...state.interviews, created];
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(created),
      });
      return;
    }

    if (path === '/api/interviews/past-due' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
      return;
    }

    if (path === '/api/interview-suggestions' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(state.interviewSuggestions),
      });
      return;
    }

    if (path.startsWith('/api/interview-suggestions/') && path.endsWith('/accept') && method === 'POST') {
      const emailId = path.split('/')[3];
      const body = await json();
      if (!body?.scheduled_at) {
        await route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Choose a date and time before adding this interview to your calendar.' }),
        });
        return;
      }
      const suggestion = state.interviewSuggestions.find((item) => item.email_id === emailId);
      const created = {
        id: `interview-${state.interviews.length + 1}`,
        application_id: body?.application_id ?? suggestion?.application_id ?? null,
        interview_type: body?.interview_type ?? suggestion?.interview_type ?? 'phone',
        scheduled_at: body.scheduled_at,
        duration_minutes: body?.duration_minutes ?? suggestion?.duration_minutes ?? null,
        interviewer_name: body?.interviewer_name ?? suggestion?.sender ?? null,
        interviewer_email: body?.interviewer_email ?? suggestion?.sender_email ?? null,
        location_or_link: body?.location_or_link ?? suggestion?.location_or_link ?? null,
        notes: body?.notes ?? null,
        outcome: 'pending',
        created_at: '2026-05-03T12:00:00Z',
      };
      state.interviews = [...state.interviews, created];
      state.interviewSuggestions = state.interviewSuggestions.filter((item) => item.email_id !== emailId);
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(created),
      });
      return;
    }

    if (path.startsWith('/api/interview-suggestions/') && path.endsWith('/dismiss') && method === 'POST') {
      const emailId = path.split('/')[3];
      state.interviewSuggestions = state.interviewSuggestions.filter((item) => item.email_id !== emailId);
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok' }),
      });
      return;
    }

    if (path === '/api/admin/job-sources' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ sources: state.adminJobSources }),
      });
      return;
    }

    if (path === '/api/admin/job-sources/health' && method === 'GET') {
      const health = state.adminSourceHealth || {
        totals: {
          verified: state.adminJobSources.filter((source) => source.verification_status === 'verified').length,
          pending_review: state.adminJobSources.filter((source) => ['pending', 'needs_review'].includes(source.verification_status)).length,
          failed_stale: state.adminJobSources.filter((source) => ['failed', 'stale'].includes(source.verification_status)).length,
          blocked: state.adminJobSources.filter((source) => source.verification_status === 'blocked').length,
          private_links_rejected_from_sharing: 0,
        },
        by_provider: {},
      };
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(health),
      });
      return;
    }

    if (path === '/api/admin/job-sources/usage' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ usage: state.adminSourceUsage }),
      });
      return;
    }

    if (path.startsWith('/api/admin/job-sources/') && method === 'POST') {
      const parts = path.split('/');
      const sourceId = parts[4];
      const action = parts[5];
      state.adminJobSources = state.adminJobSources.map((source) => {
        if (source.id !== sourceId) return source;
        if (action === 'verify') return { ...source, verification_status: 'verified', last_verified_at: '2026-05-04T12:00:00Z' };
        if (action === 'approve') return { ...source, verification_status: 'verified', access_mode: 'public' };
        if (action === 'block') return { ...source, verification_status: 'blocked', active: false, failure_reason: 'admin_blocked' };
        return source;
      });
      const updated = state.adminJobSources.find((source) => source.id === sourceId);
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ source: updated }),
      });
      return;
    }

    if (path === '/api/search' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(state.searchResponse || {
          results: [],
          cached: false,
          provider_status: {
            serpapi_configured: false,
            greenhouse_targets: ['captech', 'draftkings', 'twitch'],
            greenhouse_targets_searched: [],
            degraded: true,
            degraded_reasons: ['Broad job search is not configured, so external job board results are unavailable.'],
            mode: 'provider_limited',
          },
          source_summary: {
            direct_sources: [],
            broad_provider_used: false,
            verified_source_count: 0,
            stale_source_count: 0,
            blocked_source_count: 0,
          },
        }),
      });
      return;
    }

    if (path === '/api/search/match-preview' && method === 'POST') {
      const body = await json();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          profile_available: false,
          jobs: (body?.jobs || []).map((job: any) => ({ id: job.id, url: job.url, score: null, fit_label: null, matched_skills: [] })),
        }),
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

    if (path === '/api/research/feedback/stats' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          total_feedback: 0,
          useful: 0,
          not_useful: 0,
          notes_count: 0,
          usefulness_rate: 0,
          recent_feedback: [],
        }),
      });
      return;
    }

    if (path === '/api/research/profiles' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(state.researchProfiles),
      });
      return;
    }

    if (path === '/api/research/profiles' && method === 'POST') {
      const body = await json();
      const created = {
        id: `profile-${state.researchProfiles.length + 1}`,
        name: body?.name || 'Tracked source',
        objective: body?.objective || null,
        selected_domains: body?.selected_domains || [],
        selected_roles: body?.selected_roles || [],
        selected_companies: body?.selected_companies || [],
        keywords: body?.keywords || [],
        excluded_keywords: body?.excluded_keywords || [],
        source_types: body?.source_types || [],
        mode: body?.mode || 'internal',
        frequency: body?.frequency || 'weekly',
        depth: body?.depth || 'standard',
        notification_mode: body?.notification_mode || 'in_app',
        minimum_score: body?.minimum_score ?? 70,
        target_locations: body?.target_locations || [],
        remote_types: body?.remote_types || [],
        seniority_levels: body?.seniority_levels || [],
        research_source_scopes: body?.research_source_scopes || [],
        use_profile_context: body?.use_profile_context ?? true,
        include_public_web_research: body?.include_public_web_research ?? false,
        report_prompt_notes: body?.report_prompt_notes || null,
        max_search_queries: body?.max_search_queries ?? 8,
        max_sources_per_run: body?.max_sources_per_run ?? 20,
        active: body?.active ?? true,
        last_run_at: null,
        next_run_at: '2026-05-11T12:00:00Z',
        last_successful_run_at: null,
        created_at: '2026-05-04T12:00:00Z',
        updated_at: '2026-05-04T12:00:00Z',
      };
      state.researchProfiles = [created, ...state.researchProfiles];
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(created),
      });
      return;
    }

    if (/^\/api\/research\/profiles\/[^/]+\/run$/.test(path) && method === 'POST') {
      const profileId = path.split('/')[4];
      const run = {
        id: `run-${state.researchRuns.length + 1}`,
        profile_id: profileId,
        run_type: 'manual',
        mode: state.researchProfiles.find((profile) => profile.id === profileId)?.mode || 'internal',
        trigger_reason: 'manual_run',
        status: 'queued',
        current_step: null,
        report_id: null,
        started_at: null,
        completed_at: null,
        source_counts: { total: 0 },
        signal_counts: {},
        error_message: null,
        created_at: '2026-05-04T12:01:00Z',
      };
      state.researchRuns = [run, ...state.researchRuns];
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify(run),
      });
      return;
    }

    if (path.startsWith('/api/research/profiles/') && method === 'PATCH') {
      const profileId = path.split('/').pop();
      const body = await json();
      const profile = state.researchProfiles.find((row) => row.id === profileId);
      if (!profile) {
        await route.fulfill({
          status: 404,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Profile not found' }),
        });
        return;
      }

      Object.assign(profile, body || {}, {
        updated_at: '2026-05-02T14:45:00Z',
        next_run_at: body?.active === false ? null : profile.next_run_at,
      });
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(profile),
      });
      return;
    }

    if (path === '/api/research/runs' && method === 'GET') {
      const profileId = url.searchParams.get('profile_id');
      const rows = profileId
        ? state.researchRuns.filter((run) => run.profile_id === profileId)
        : state.researchRuns;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(rows),
      });
      return;
    }

    if (
      [
        '/api/research/signals',
        '/api/research/briefs',
        '/api/research/actions',
        '/api/research/reports',
      ].includes(path) &&
      method === 'GET'
    ) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
      return;
    }

    if (path === '/api/copilot/conversations' && method === 'POST') {
      const body = await json();
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          conversation: {
            ...copilotConversation,
            title: String(body?.title || copilotConversation.title),
          },
        }),
      });
      return;
    }

    if (path === '/api/copilot/conversations/radar-setup-conversation/messages' && method === 'POST') {
      const body = await json();
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          conversation: copilotConversation,
          user_message: {
            id: 'radar-setup-user-message',
            conversation_id: copilotConversation.id,
            role: 'user',
            content: body?.content || '',
            citations: [],
            suggested_actions: [],
            metadata: {},
            model_call_id: null,
            created_at: '2026-05-02T14:30:00Z',
          },
          assistant_message: {
            id: 'radar-setup-assistant-message',
            conversation_id: copilotConversation.id,
            role: 'assistant',
            content: [
              'Tracker name: AI/ML Data Science Radar',
              'What Radar should watch: AI and ML data science roles across banks, fintech, search, and virtual assistant teams.',
              'Watch sources: Activity + research',
              'Cadence: Weekly',
              'Avoid: Internships and unpaid roles',
            ].join('\n'),
            citations: [],
            suggested_actions: [],
            metadata: { mode: 'model', model: 'test-model', prompt_version: 'test-v1' },
            model_call_id: 'radar-setup-model-call',
            created_at: '2026-05-02T14:30:00Z',
          },
        }),
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

    if (path === '/api/network-suggestions' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(state.networkSuggestions),
      });
      return;
    }

    if (path === '/api/network-suggestions/accept' && method === 'POST') {
      const body = await json();
      const suggestion = state.networkSuggestions.find((item) => item.email_id === body?.email_id || item.email === body?.email);
      if (!suggestion) {
        await route.fulfill({
          status: 404,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Network suggestion not found' }),
        });
        return;
      }
      const contact = {
        id: `contact-${state.networkContacts.length + 1}`,
        name: suggestion.name,
        email: suggestion.email,
        title: suggestion.title,
        company: suggestion.company,
        source: 'email',
        reached_out: false,
        response_received: false,
        linkedin_url: suggestion.linkedin_url,
      };
      state.networkContacts = [...state.networkContacts, contact];
      state.networkSuggestions = state.networkSuggestions.filter((item) => item.email !== suggestion.email);
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(contact),
      });
      return;
    }

    if (path === '/api/network-suggestions/dismiss' && method === 'POST') {
      const body = await json();
      state.networkSuggestions = state.networkSuggestions.filter((item) => item.email_id !== body?.email_id && item.email !== body?.email);
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok' }),
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

  await expect(page.getByRole('heading', { name: 'Opportunity Radar' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sign in with Google' })).toBeVisible();
  await expect(page.getByText('Turn job-search signals into your next move.')).toBeVisible();
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
    await expect(page.getByRole('button', { name: 'Source Intelligence' })).toHaveCount(0);
    await expect(page.getByText('Test User')).toBeVisible();
  });

  test('Gmail inbox actions require explicit calendar details and capture route corrections', async ({ page }) => {
    await mockLoggedInApi(page, {
      emails: [
        {
          id: 'email-interview-action',
          sender: 'BankCo Recruiting',
          sender_email: 'recruiting@bankco.example',
          subject: 'Schedule your interview with BankCo',
          snippet: 'Please choose a time for your interview.',
          body: 'Please choose a time for your interview.',
          received_at: '2026-05-07T12:00:00Z',
          classification: 'interview_request',
          email_type: 'decision',
          company_name: 'BankCo',
          sender_domain: 'bankco.example',
          resolved: false,
        },
        {
          id: 'email-move-conversation',
          sender: 'Taylor Recruiter',
          sender_email: 'taylor@talent.example',
          subject: 'Quick recruiter intro',
          snippet: 'Open to talking about data roles?',
          body: 'Open to talking about data roles?',
          received_at: '2026-05-06T12:00:00Z',
          classification: 'job_update',
          email_type: 'decision',
          company_name: 'TalentCo',
          sender_domain: 'talent.example',
          resolved: false,
        },
      ],
    });

    await page.goto('/');
    await page.getByRole('button', { name: 'Inbox' }).click();
    await page.getByText('Schedule your interview with BankCo').first().click();

    await page.getByRole('button', { name: 'Add to Calendar' }).click();
    const interviewDialog = page.getByRole('dialog', { name: 'Add Interview' });
    await expect(interviewDialog).toBeVisible();
    await expect(interviewDialog.getByText('Confirm the date and details before adding this to your calendar.')).toBeVisible();
    await expect(interviewDialog.getByRole('button', { name: 'Add to Calendar' })).toBeDisabled();
    await interviewDialog.locator('input[type="datetime-local"]').fill('2026-05-08T10:30');
    await interviewDialog.getByRole('button', { name: 'Add to Calendar' }).click();
    await expect(interviewDialog).toHaveCount(0);

    await page.getByText('Quick recruiter intro').first().click();
    await page.getByRole('button', { name: 'Move to Conversations' }).click();
    const correctionDialog = page.getByRole('dialog', { name: 'Move to Conversations' });
    await expect(correctionDialog).toBeVisible();
    await correctionDialog.getByRole('button', { name: /Other/ }).click();
    await correctionDialog.getByRole('button', { name: 'Move to Conversations' }).click();
    await expect(correctionDialog).toHaveCount(0);

    const fitsViewport = await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);
    expect(fitsViewport).toBeTruthy();
  });

  test('Gmail conversations suggest network contacts and capture non-conversation feedback', async ({ page }) => {
    await mockLoggedInApi(page, {
      emails: [
        {
          id: 'email-conversation-action',
          sender: 'Jamie Recruiter',
          sender_email: 'jamie@matchco.example',
          subject: 'Following up on the analyst role',
          snippet: 'Can you send availability next week?',
          body: 'Can you send availability next week?',
          received_at: '2026-05-07T12:00:00Z',
          classification: 'conversation',
          email_type: 'conversation',
          company_name: 'MatchCo',
          sender_domain: 'matchco.example',
          is_human: true,
          resolved: false,
        },
      ],
      networkSuggestions: [
        {
          email_id: 'email-conversation-action',
          name: 'Jamie Recruiter',
          email: 'jamie@matchco.example',
          title: 'Recruiter',
          company: 'MatchCo',
          linkedin_url: null,
          email_count: 1,
          last_interaction_at: '2026-05-07T12:00:00Z',
          subject: 'Following up on the analyst role',
          snippet: 'Can you send availability next week?',
        },
      ],
    });

    await page.goto('/');
    await page.getByRole('button', { name: 'Conversations' }).click();
    await page.getByText('Jamie Recruiter').first().click();

    await page.getByRole('button', { name: 'Add to Network' }).click();
    await expect(page.getByText('Contact added to your network.')).toBeVisible();

    await page.getByRole('button', { name: 'Not Conversation Related' }).click();
    const correctionDialog = page.getByRole('dialog', { name: 'Not Conversation Related' });
    await expect(correctionDialog).toBeVisible();
    await correctionDialog.getByRole('button', { name: 'External job board alert' }).click();
    await correctionDialog.getByRole('button', { name: 'Filter from Conversations' }).click();
    await expect(correctionDialog).toHaveCount(0);

    const fitsViewport = await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);
    expect(fitsViewport).toBeTruthy();
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
    await expect(page.getByRole('button', { name: 'Source Intelligence' })).toBeVisible();
  });

  test('admin source intelligence page shows redacted source governance data', async ({ page }) => {
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
      adminJobSources: [
        {
          id: 'source-greenhouse-1',
          company_name: 'Acme',
          company_domain: 'acme.com',
          provider_type: 'greenhouse',
          provider_key: 'acme',
          access_mode: 'public',
          career_url: 'https://boards.greenhouse.io/acme',
          public_jobs_endpoint: 'https://boards-api.greenhouse.io/v1/boards/acme/jobs',
          source_config: { hostname_hash: 'hosthash_123' },
          verification_status: 'needs_review',
          active: true,
          terms_risk: 'low',
          discovered_from: 'gmail_application',
          evidence_count: 2,
          failure_count: 0,
          failure_reason: null,
          last_verified_at: null,
          updated_at: '2026-05-04T12:00:00Z',
        },
      ],
      adminSourceUsage: [
        { provider: 'serpapi', month_bucket: '2026-05-01', request_count: 3, result_count: 14 },
      ],
      adminSourceHealth: {
        totals: {
          verified: 0,
          pending_review: 1,
          failed_stale: 0,
          blocked: 0,
          private_links_rejected_from_sharing: 4,
        },
        by_provider: { greenhouse: { needs_review: 1 } },
      },
    });

    await page.goto('/');
    await page.getByRole('button', { name: 'Source Intelligence' }).click();

    await expect(page.getByRole('heading', { name: 'Source Intelligence' })).toBeVisible();
    await expect(page.getByText('Source Registry')).toBeVisible();
    await expect(page.getByText('Acme', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('greenhouse')).toBeVisible();
    await expect(page.getByText('Private Rejected')).toBeVisible();
    await expect(page.getByText('serpapi')).toBeVisible();
    await expect(page.getByText(/token|candidateId|applicationId|secret-token/i)).toHaveCount(0);

    await page.getByRole('button', { name: 'Approve' }).click();
    await expect(page.getByText('verified')).toBeVisible();
    await page.getByRole('button', { name: 'Block' }).click();
    await expect(page.getByText('blocked')).toBeVisible();
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

  test('settings keeps Gmail sync diagnostics collapsed until expanded', async ({ page }) => {
    await mockLoggedInApi(page, {
      gmailAuditRows: Array.from({ length: 5 }, (_, index) => ({
        id: `audit-${index + 1}`,
        sync_run_id: 'sync-run-1',
        email_event_id: null,
        gmail_message_id: `gmail-${index + 1}`,
        thread_id: `thread-${index + 1}`,
        sender: 'Recruiting Team',
        sender_email: `recruiting-${index + 1}@example.com`,
        sender_domain: 'example.com',
        subject: `Checked Gmail message ${index + 1}`,
        received_at: '2026-05-03T12:00:00Z',
        decision: index % 2 === 0 ? 'stored' : 'filtered',
        reason: index % 2 === 0 ? 'job_related' : 'not_job_related',
        classification: index % 2 === 0 ? 'interview_request' : null,
        created_at: `2026-05-03T12:0${index}:00Z`,
      })),
    });

    await page.goto('/');
    await page.getByRole('button', { name: 'Settings' }).click();

    await expect(page.getByRole('heading', { name: 'Gmail Sync Diagnostics' })).toBeVisible();
    await expect(page.getByText('Checked Gmail message 1')).toBeVisible();
    await expect(page.getByText('Checked Gmail message 3')).toBeVisible();
    await expect(page.getByText('Checked Gmail message 4')).toHaveCount(0);

    await page.getByRole('button', { name: 'Show all checked messages' }).click();
    await expect(page.getByText('Checked Gmail message 5')).toBeVisible();

    await page.getByRole('button', { name: 'Show fewer' }).click();
    await expect(page.getByText('Checked Gmail message 4')).toHaveCount(0);
  });

  test('settings source intelligence manages private links without exposing raw URLs', async ({ page }) => {
    await mockLoggedInApi(page, {
      sourcePrivateLinks: [
        {
          id: 'private-link-1',
          provider: 'workday',
          link_type: 'interview_scheduler',
          company_domain: 'bank.example',
          created_at: '2026-05-04T12:00:00Z',
          sanitization_status: 'private_user_only',
          raw_url: 'https://candidate.example/schedule?token=secret-token',
        },
      ],
    });

    await page.goto('/');
    await page.getByRole('button', { name: 'Settings' }).click();

    await expect(page.getByText('Source Intelligence').first()).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Private Application Links' })).toBeVisible();
    await expect(page.getByText('workday')).toBeVisible();
    await expect(page.getByText('interview scheduler')).toBeVisible();
    await expect(page.getByText(/secret-token|candidate\\.example|token=/i)).toHaveCount(0);

    await page.getByRole('button', { name: 'Reprocess' }).click();
    await expect(page.getByText('Reprocessed 1 application links.')).toBeVisible();
    await page.getByRole('button', { name: 'Delete', exact: true }).click();
    await expect(page.getByText('Private link deleted.')).toBeVisible();
    await expect(page.getByText('workday')).toHaveCount(0);
  });

  test('calendar asks for a time before accepting unscheduled Gmail interview suggestions', async ({ page }) => {
    await mockLoggedInApi(page, {
      interviewSuggestions: [
        {
          email_id: 'email-interview-unscheduled',
          subject: 'Select a timeslot for your BankCo interview',
          sender: 'BankCo Scheduling',
          sender_email: 'scheduling@bankco.com',
          company_name: 'BankCo',
          role_title: 'Data Scientist',
          application_id: null,
          interview_type: 'phone',
          scheduled_at: null,
          duration_minutes: 30,
          location_or_link: null,
          snippet: 'Please select a timeslot for your interview.',
          received_at: '2026-05-03T12:00:00Z',
          confidence: 0.9,
        },
      ],
    });

    await page.goto('/');
    await page.getByRole('button', { name: 'Calendar' }).click();

    await expect(page.getByText('Time not detected')).toBeVisible();
    await page.getByRole('button', { name: 'Add details' }).click();
    const dialog = page.getByRole('dialog', { name: 'Add Interview' });
    await expect(dialog).toBeVisible();
    await expect(page.getByText('Choose a date and time before adding this interview to your calendar.')).toBeVisible();

    await dialog.getByLabel('Date & Time').fill('2026-05-07T14:30');
    await dialog.getByRole('button', { name: 'Add Interview', exact: true }).click();

    await expect(page.getByText('Interview added from Gmail.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'BankCo Scheduling', exact: true })).toBeVisible();
  });

  test('job search explains provider-limited empty results', async ({ page }) => {
    await mockLoggedInApi(page);

    await page.goto('/');
    await page.getByRole('button', { name: 'Job Search' }).click();
    await page.getByPlaceholder('Search roles, companies, or keywords...').fill('Bank of America');
    await page.getByRole('button', { name: 'Search', exact: true }).click();

    await expect(page.getByText('No jobs returned')).toBeVisible();
    await expect(page.getByText(/Broad job search is not configured/)).toBeVisible();
  });

  test('job search shows direct source summary and provider badges', async ({ page }) => {
    await mockLoggedInApi(page, {
      searchResponse: {
        results: [
          {
            id: 'job-acme-analyst',
            title: 'Data Analyst',
            company: 'Acme',
            location: 'Remote',
            source: 'greenhouse',
            freshness: 'seen_today',
            url: 'https://boards.greenhouse.io/acme/jobs/123',
            posted_at: '2026-05-04T00:00:00Z',
            description: 'Analyze product and customer data.',
          },
        ],
        cached: false,
        provider_status: {
          mode: 'direct_source',
          broad_search_used: false,
          degraded: false,
          degraded_reasons: [],
        },
        source_summary: {
          direct_sources: [{ provider_type: 'greenhouse', provider_key: 'acme', verification_status: 'verified' }],
          broad_provider_used: false,
          verified_source_count: 1,
          stale_source_count: 0,
          blocked_source_count: 0,
        },
      },
    });

    await page.goto('/');
    await page.getByRole('button', { name: 'Job Search' }).click();
    await page.getByPlaceholder('Search roles, companies, or keywords...').fill('data analyst Acme');
    await page.getByRole('button', { name: 'Search', exact: true }).click();

    await expect(page.getByText('Searching verified company career sources.')).toBeVisible();
    await expect(page.getByText('Company sources')).toBeVisible();
    await expect(page.getByText('Greenhouse')).toBeVisible();
    await expect(page.getByText('Fresh today')).toBeVisible();
    await page.getByRole('button', { name: /Open Data Analyst at Acme/ }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await page.getByRole('button', { name: 'Track this source' }).click();
    await expect(page.getByText('Tracking Acme source in Radar.')).toBeVisible();
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

  test('radar tracker form stays readable with the updates rail open', async ({ page }) => {
    await page.setViewportSize({ width: 2048, height: 1320 });
    await mockLoggedInApi(page, {
      emails: [
        {
          id: 'email-interview-1',
          sender: 'Global HR Interviews',
          sender_email: 'global.hr@example.com',
          subject: 'You are confirmed for an interview on 05/07/2026',
          snippet: 'Your interview is confirmed for 05/07/2026.',
          body: 'Your interview is confirmed.',
          received_at: '2026-05-01T12:00:00Z',
          classification: 'interview_request',
          email_type: 'job_update',
          category: 'interview_request',
          company_name: 'Bank of America',
          sender_domain: 'example.com',
          resolved: false,
        },
      ],
    });

    await page.goto('/');
    await page.getByRole('button', { name: 'Radar' }).click();

    await expect(page.getByRole('heading', { name: 'Opportunity Radar' })).toBeVisible();
    await expect(page.getByText('Watch sources')).toBeVisible();
    await expect(page.getByText('Activity + research')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Updates' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Not sure? Ask Scout' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Radar quality' })).toHaveCount(0);

    await page.getByRole('button', { name: 'New tracker' }).first().click();
    await expect(page.locator('#radar-tracker-form input').first()).toBeFocused();
    await expect(page.getByRole('status').filter({ hasText: 'New tracker draft is open below' })).toBeVisible();

    const modeOptionBoxes = await page.locator('label:has(input[name="tracker-mode"])').evaluateAll((nodes) =>
      nodes.map((node) => {
        const rect = node.getBoundingClientRect();
        return {
          width: rect.width,
          height: rect.height,
          left: rect.left,
          right: rect.right,
          top: rect.top,
        };
      }),
    );

    expect(modeOptionBoxes).toHaveLength(3);
    const viewportWidth = page.viewportSize()?.width || 0;
    for (const box of modeOptionBoxes) {
      expect(box.width).toBeGreaterThan(220);
      expect(box.height).toBeLessThan(128);
      expect(box.left).toBeGreaterThanOrEqual(0);
      expect(box.right).toBeLessThanOrEqual(viewportWidth);
    }

    await page.getByRole('button', { name: 'Not sure? Ask Scout' }).click();
    const scoutPanel = page.getByRole('dialog', { name: 'Ask Scout' });
    await expect(scoutPanel).toBeVisible();
    await expect(scoutPanel.getByText('Tracker name: AI/ML Data Science Radar')).toBeVisible();

    const fitsViewport = await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);
    expect(fitsViewport).toBeTruthy();
  });

  test('radar tracker cadence can be paused and resumed from the tracker card', async ({ page }) => {
    await mockLoggedInApi(page, {
      researchProfiles: [
        {
          id: 'profile-1',
          name: 'BOA AI roles',
          objective: 'Track AI and NLP roles at banks.',
          selected_domains: [],
          selected_roles: [],
          selected_companies: [],
          keywords: [],
          excluded_keywords: [],
          source_types: ['application'],
          mode: 'internal',
          frequency: 'weekly',
          depth: 'standard',
          notification_mode: 'in_app',
          minimum_score: 70,
          target_locations: [],
          remote_types: [],
          seniority_levels: [],
          research_source_scopes: [],
          use_profile_context: true,
          include_public_web_research: false,
          report_prompt_notes: null,
          max_search_queries: 8,
          max_sources_per_run: 20,
          active: true,
          last_run_at: null,
          next_run_at: '2026-05-10T12:00:00Z',
          last_successful_run_at: null,
          created_at: '2026-05-02T14:30:00Z',
          updated_at: '2026-05-02T14:30:00Z',
        },
      ],
    });

    await page.goto('/');
    await page.getByRole('button', { name: 'Radar' }).click();

    await expect(page.getByRole('button', { name: /BOA AI roles/ })).toBeVisible();
    await expect(page.locator('span').filter({ hasText: /^Active$/ })).toBeVisible();
    await page.getByRole('button', { name: 'Pause cadence' }).click();
    await expect(page.locator('span').filter({ hasText: /^Paused$/ })).toBeVisible();
    await expect(page.getByText('Cadence paused')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Resume cadence' })).toBeVisible();

    await page.getByRole('button', { name: 'Resume cadence' }).click();
    await expect(page.locator('span').filter({ hasText: /^Active$/ })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Pause cadence' })).toBeVisible();
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
