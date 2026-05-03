import { expect, test, type Page, type Route } from '@playwright/test';

const RUN_ID = '11111111-1111-4111-8111-111111111111';
const PROMOTION_ID = '22222222-2222-4222-8222-222222222222';
const ACCESS_LOG_ID = '33333333-3333-4333-8333-333333333333';

type MockOptions = {
  isAdmin?: boolean;
};

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

async function mockApp(page: Page, options: MockOptions = {}) {
  await page.addInitScript(() => {
    window.localStorage.setItem('apptrail-auth-session', 'true');
  });

  let promotionStatus = 'pending_review';
  let accessLogs: unknown[] = [];
  let safetyReviewStatus = 'unreviewed';

  await page.route('http://localhost:8000/api/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    if (path === '/api/auth/refresh' && method === 'POST') {
      await fulfillJson(route, { access_token: 'test-access-token', token_type: 'bearer' });
      return;
    }

    if (path === '/api/auth/me' && method === 'GET') {
      await fulfillJson(route, {
        id: '00000000-0000-0000-0000-000000000001',
        email: options.isAdmin ? 'admin@apptrail.test' : 'user@apptrail.test',
        name: options.isAdmin ? 'Admin User' : 'Standard User',
        picture: '',
        gmail_connected: true,
        calendar_connected: false,
        data_consent_accepted_at: '2026-05-02T12:00:00Z',
        is_admin: !!options.isAdmin,
      });
      return;
    }

    if (path === '/api/jobs' && method === 'GET') {
      await fulfillJson(route, []);
      return;
    }

    if (path === '/api/emails' && method === 'GET') {
      await fulfillJson(route, []);
      return;
    }

    if (path === '/api/alerts' && method === 'GET') {
      await fulfillJson(route, []);
      return;
    }

    if (path === '/api/alerts/count' && method === 'GET') {
      await fulfillJson(route, { unread: 0 });
      return;
    }

    if (path === '/api/audit/runs' && method === 'GET') {
      await fulfillJson(route, []);
      return;
    }

    if (path === '/api/audit/compare' && method === 'GET') {
      await fulfillJson(route, []);
      return;
    }

    if (path === '/api/emails/feedback/stats' && method === 'GET') {
      await fulfillJson(route, {
        total_feedback: 0,
        not_job_related: 0,
        job_related: 0,
        top_blocked_domains: [],
        original_classifications: {},
        daily_trend: [],
      });
      return;
    }

    if (path === '/api/extraction-reports/stats' && method === 'GET') {
      await fulfillJson(route, {
        total: 0,
        unresolved: 0,
        by_type: {},
        by_platform: {},
        by_field: {},
      });
      return;
    }

    if (path === '/api/extraction-reports' && method === 'GET') {
      await fulfillJson(route, []);
      return;
    }

    if (path === '/api/extraction-changelog' && method === 'GET') {
      await fulfillJson(route, []);
      return;
    }

    if (path === '/api/extraction-reports/version-stats' && method === 'GET') {
      await fulfillJson(route, { versions: [], changelog: [] });
      return;
    }

    if (path === '/api/admin/ai/telemetry' && method === 'GET') {
      await fulfillJson(route, {
        generated_at: '2026-05-02T14:30:00Z',
        overview: {
          total_calls: 12,
          failure_count: 1,
          failure_rate: 0.0833,
          fallback_rate: 0.1667,
          total_cost_cents: 94,
          total_tokens: 18450,
          p95_latency_ms: 1420,
        },
        by_task: [
          { surface: 'copilot', task_name: 'copilot_answer', calls: 8, cost_cents: 68, failures: 0 },
          { surface: 'search', task_name: 'rerank_jobs', calls: 4, cost_cents: 26, failures: 1 },
        ],
        search_freshness: { document_count: 24, stale_document_count: 2 },
        queue_health: { queued_shadow_runs: 3 },
        experiment_guardrails: {
          running_experiments: 1,
          paused_experiments: 1,
          pending_promotion_reports: promotionStatus === 'pending_review' ? 1 : 0,
        },
        safety_guardrails: {
          blocked_decisions: 1,
          redacted_decisions: 3,
          quarantined_decisions: 1,
          unreviewed_decisions: 1,
        },
      });
      return;
    }

    if (path === '/api/admin/ai/runs' && method === 'GET') {
      await fulfillJson(route, {
        runs: [
          {
            id: RUN_ID,
            user_id: '00000000-0000-0000-0000-000000000001',
            surface: 'copilot',
            task_name: 'copilot_answer',
            provider: 'openai',
            model: 'gpt-5.4',
            prompt_version: 'copilot_v1',
            variant: 'control',
            status: 'success',
            validation_result: 'valid',
            fallback_used: false,
            fallback_reason: null,
            latency_ms: 250,
            total_tokens: 150,
            prompt_tokens: 100,
            output_tokens: 50,
            cost_estimate_cents: 3,
            created_at: '2026-05-02T14:20:00Z',
          },
        ],
      });
      return;
    }

    if (path === `/api/admin/ai/runs/${RUN_ID}` && method === 'GET') {
      await fulfillJson(route, {
        run: {
          id: RUN_ID,
          user_id: '00000000-0000-0000-0000-000000000001',
          surface: 'copilot',
          task_name: 'copilot_answer',
          provider: 'openai',
          model: 'gpt-5.4',
          prompt_version: 'copilot_v1',
          variant: 'control',
          status: 'success',
          validation_result: 'valid',
          fallback_used: false,
          fallback_reason: null,
          latency_ms: 250,
          total_tokens: 150,
          prompt_tokens: 100,
          output_tokens: 50,
          cost_estimate_cents: 3,
          created_at: '2026-05-02T14:20:00Z',
        },
        request_metadata: { raw_prompt: '[redacted]', retrieval_scope: 'user_only' },
        response_metadata: { email_body: '[redacted]', answer_quality: 'grounded' },
        artifacts: [
          {
            id: '44444444-4444-4444-8444-444444444444',
            user_id: '00000000-0000-0000-0000-000000000001',
            model_call_id: RUN_ID,
            artifact_type: 'copilot_message',
            artifact_ref_id: '55555555-5555-4555-8555-555555555555',
            title: 'Copilot answer',
            path: 'app://copilot/message',
            metadata: { citation_count: 2 },
            created_at: '2026-05-02T14:21:00Z',
          },
        ],
        full_trace_available: true,
        full_trace_requires_reason: true,
      });
      return;
    }

    if (path === `/api/admin/ai/runs/${RUN_ID}/trace-access` && method === 'POST') {
      accessLogs = [
        {
          id: ACCESS_LOG_ID,
          admin_user_id: '00000000-0000-0000-0000-000000000001',
          action: 'view_full_ai_trace',
          target_type: 'ai_model_call',
          target_id: RUN_ID,
          reason: 'Debugging groundedness issue',
          metadata: { surface: 'copilot', task_name: 'copilot_answer' },
          created_at: '2026-05-02T14:32:00Z',
        },
      ];
      await fulfillJson(route, {
        run: { id: RUN_ID, surface: 'copilot', task_name: 'copilot_answer' },
        request_metadata: { raw_prompt: 'secret prompt' },
        response_metadata: { answer_quality: 'grounded' },
        access_log_id: ACCESS_LOG_ID,
      });
      return;
    }

    if (path === '/api/admin/ai/artifacts' && method === 'GET') {
      await fulfillJson(route, {
        artifacts: [
          {
            id: '44444444-4444-4444-8444-444444444444',
            user_id: '00000000-0000-0000-0000-000000000001',
            model_call_id: RUN_ID,
            artifact_type: 'copilot_message',
            artifact_ref_id: '55555555-5555-4555-8555-555555555555',
            title: 'Copilot answer',
            path: 'app://copilot/message',
            metadata: { raw_prompt: '[redacted]', citation_count: 2 },
            created_at: '2026-05-02T14:21:00Z',
          },
        ],
      });
      return;
    }

    if (path === '/api/admin/ai/experiments' && method === 'GET') {
      await fulfillJson(route, {
        experiments: [
          {
            id: '66666666-6666-4666-8666-666666666666',
            experiment_key: 'copilot_ops',
            surface: 'copilot',
            task_name: 'copilot_answer',
            status: 'running',
            control_variant: 'control',
            candidate_variants: ['candidate'],
            traffic_allocation: { control: 0.9, candidate: 0.1 },
            guardrail_thresholds: { max_cost_cents: 5 },
            created_at: '2026-05-01T14:20:00Z',
            updated_at: '2026-05-02T14:20:00Z',
          },
        ],
      });
      return;
    }

    if (path === '/api/admin/ai/model-cards' && method === 'GET') {
      await fulfillJson(route, {
        model_cards: [
          {
            id: '77777777-7777-4777-8777-777777777777',
            task_name: 'copilot_answer',
            model: 'gpt-5.4',
            prompt_version: 'copilot_v1',
            approval_status: 'draft',
            primary_metrics: { grounded_accuracy: 0.987 },
            guardrail_metrics: { pii_leak_rate: 0 },
            updated_at: '2026-05-02T14:20:00Z',
          },
        ],
      });
      return;
    }

    if (path === '/api/admin/ai/promotion-reports' && method === 'GET') {
      await fulfillJson(route, {
        promotion_reports: [
          {
            id: PROMOTION_ID,
            experiment_id: '66666666-6666-4666-8666-666666666666',
            status: promotionStatus,
            recommendation: promotionStatus === 'approved' ? 'promote_candidate' : 'keep_control_collect_more_data',
            generated_after_calls: 1000,
            generated_after_feedback: 140,
            report: { cost_delta_cents: -1200, accuracy_delta: -0.02 },
            created_at: '2026-05-02T14:20:00Z',
            reviewed_at: promotionStatus === 'approved' ? '2026-05-02T14:35:00Z' : null,
          },
        ],
      });
      return;
    }

    if (path === `/api/admin/ai/promotion-reports/${PROMOTION_ID}/approve` && method === 'POST') {
      promotionStatus = 'approved';
      await fulfillJson(route, { report_id: PROMOTION_ID, status: promotionStatus, recommendation: 'promote_candidate' });
      return;
    }

    if (path === `/api/admin/ai/promotion-reports/${PROMOTION_ID}/reject` && method === 'POST') {
      promotionStatus = 'rejected';
      await fulfillJson(route, { report_id: PROMOTION_ID, status: promotionStatus, recommendation: 'keep_control' });
      return;
    }

    if (path === '/api/admin/ai/trace-access-logs' && method === 'GET') {
      await fulfillJson(route, { access_logs: accessLogs });
      return;
    }

    if (path === '/api/admin/ai/safety-decisions' && method === 'GET') {
      if (url.searchParams.get('policy_decision') === 'quarantine') {
        await fulfillJson(route, {
          safety_decisions: [
            {
              id: '99999999-9999-4999-8999-999999999999',
              user_id: '00000000-0000-0000-0000-000000000001',
              model_call_id: null,
              surface: 'research_radar',
              task_name: 'research_evidence_extractor',
              stage: 'preflight',
              policy_decision: 'quarantine',
              risk_score: 0.91,
              prompt_injection_score: 0.91,
              input_data_classes: ['public_research'],
              consent_snapshot: { ai: true },
              redaction_counts: { prompt_injection_line: 1 },
              reasons: ['semantic_prompt_guard'],
              token_estimate: 300,
              metadata: {},
              review_status: safetyReviewStatus,
              reviewed_by_user_id: safetyReviewStatus === 'unreviewed' ? null : '00000000-0000-0000-0000-000000000001',
              reviewed_at: safetyReviewStatus === 'unreviewed' ? null : '2026-05-02T14:40:00Z',
              review_notes: safetyReviewStatus === 'unreviewed' ? null : 'Reviewed in AI Ops.',
              created_at: '2026-05-02T14:34:00Z',
            },
          ],
        });
        return;
      }
      await fulfillJson(route, {
        safety_decisions: [
          {
            id: '88888888-8888-4888-8888-888888888888',
            user_id: '00000000-0000-0000-0000-000000000001',
            model_call_id: RUN_ID,
            surface: 'copilot',
            task_name: 'copilot_answer',
            stage: 'preflight',
            policy_decision: 'allow_redacted',
            risk_score: 0.72,
            prompt_injection_score: 0.36,
            input_data_classes: ['career_private', 'untrusted_inbound'],
            consent_snapshot: { ai: true },
            redaction_counts: { email: 1 },
            reasons: ['reveal_prompt', 'redacted_email'],
            token_estimate: 431,
            metadata: { raw_prompt: '[redacted]' },
            review_status: 'unreviewed',
            reviewed_by_user_id: null,
            reviewed_at: null,
            review_notes: null,
            created_at: '2026-05-02T14:33:00Z',
          },
        ],
      });
      return;
    }

    if (path === '/api/admin/ai/safety-decisions/99999999-9999-4999-8999-999999999999/review' && method === 'PATCH') {
      const body = JSON.parse(request.postData() || '{}');
      safetyReviewStatus = body.review_status || 'confirmed_unsafe';
      await fulfillJson(route, {
        id: '99999999-9999-4999-8999-999999999999',
        user_id: '00000000-0000-0000-0000-000000000001',
        model_call_id: null,
        surface: 'research_radar',
        task_name: 'research_evidence_extractor',
        stage: 'preflight',
        policy_decision: 'quarantine',
        risk_score: 0.91,
        prompt_injection_score: 0.91,
        input_data_classes: ['public_research'],
        consent_snapshot: { ai: true },
        redaction_counts: { prompt_injection_line: 1 },
        reasons: ['semantic_prompt_guard'],
        token_estimate: 300,
        metadata: {},
        review_status: safetyReviewStatus,
        reviewed_by_user_id: '00000000-0000-0000-0000-000000000001',
        reviewed_at: '2026-05-02T14:40:00Z',
        review_notes: 'Reviewed in AI Ops.',
        created_at: '2026-05-02T14:34:00Z',
      });
      return;
    }

    await fulfillJson(route, {});
  });
}

test('non-admin users do not see AI Ops navigation', async ({ page }) => {
  await mockApp(page, { isAdmin: false });
  await page.goto('/');

  await expect(page.getByRole('heading', { name: 'Pipeline' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'AI Ops' })).toHaveCount(0);
});

test('admin can review AI Ops telemetry, traces, and promotion reports', async ({ page }) => {
  await mockApp(page, { isAdmin: true });
  await page.goto('/');

  await page.getByRole('button', { name: 'AI Ops' }).click();

  await expect(page.getByRole('heading', { name: 'AI Ops' })).toBeVisible();
  await expect(page.getByText('12')).toBeVisible();
  await expect(page.getByText('$0.94')).toBeVisible();
  await expect(page.getByText('copilot_answer')).toBeVisible();

  await page.getByRole('button', { name: 'Runs' }).click();
  await page.getByRole('row', { name: /copilot copilot_answer/ }).click();
  await expect(page.getByText('"raw_prompt": "[redacted]"')).toBeVisible();
  await expect(page.getByText('"email_body": "[redacted]"')).toBeVisible();

  await page.getByLabel('Access Reason').fill('Debugging groundedness issue');
  await page.getByRole('button', { name: 'Request Full Trace' }).click();
  await expect(page.getByText(`Full trace access logged: ${ACCESS_LOG_ID}`)).toBeVisible();

  await page.getByRole('button', { name: 'Access Logs' }).click();
  await expect(page.getByText('Debugging groundedness issue')).toBeVisible();
  await expect(page.getByText('view full ai trace')).toBeVisible();

  await page.getByRole('button', { name: 'Safety' }).click();
  await expect(page.getByText('Safety Decisions')).toBeVisible();
  await expect(page.locator('tbody').getByText('allow redacted', { exact: true })).toBeVisible();
  await expect(page.getByText('redacted email')).toBeVisible();
  await page.getByLabel('Decision').selectOption('quarantine');
  await expect(page.locator('tbody').getByText('quarantine', { exact: true })).toBeVisible();
  await expect(page.getByText('semantic prompt guard')).toBeVisible();
  await expect(page.locator('tbody').getByText('unreviewed', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Confirm unsafe' }).click();
  await expect(page.locator('tbody').getByText('confirmed unsafe', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Promotions' }).click();
  await expect(page.getByText('keep control collect more data')).toBeVisible();
  await page.getByRole('button', { name: 'Approve' }).click();
  await expect(page.getByText('approved')).toBeVisible();
  await expect(page.getByText('promote candidate')).toBeVisible();
});

test('admin-only pages use the full desktop workspace and survive sidebar collapse', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockApp(page, { isAdmin: true });
  await page.goto('/');

  for (const pageName of ['Classifier Audit', 'Extraction Reports', 'AI Ops']) {
    await page.getByRole('button', { name: pageName }).click();
    await expect(page.getByRole('heading', { name: pageName })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Updates' })).toHaveCount(0);
    const fitsViewport = await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);
    expect(fitsViewport).toBeTruthy();
  }

  await page.getByLabel('Collapse navigation sidebar').click();
  await page.waitForTimeout(400);
  await expect(page.getByLabel('Expand navigation sidebar')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Access Logs' })).toBeVisible();
  await page.getByRole('button', { name: 'Runs' }).click();
  await expect(page.getByPlaceholder('Filter surface')).toBeVisible();
  await expect(page.getByText('Run Detail')).toBeVisible();

  const collapsedLayout = await page.evaluate(() => {
    const main = document.querySelector('main')?.getBoundingClientRect();
    const runFilter = Array.from(document.querySelectorAll('input'))
      .find((input) => input.getAttribute('placeholder') === 'Filter surface')
      ?.getBoundingClientRect();
    return {
      documentFits: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
      mainWidth: main?.width ?? 0,
      filterInsideViewport: runFilter ? runFilter.left >= 0 && runFilter.right <= window.innerWidth : false,
    };
  });

  expect(collapsedLayout.documentFits).toBeTruthy();
  expect(collapsedLayout.mainWidth).toBeGreaterThan(1280);
  expect(collapsedLayout.filterInsideViewport).toBeTruthy();
});
