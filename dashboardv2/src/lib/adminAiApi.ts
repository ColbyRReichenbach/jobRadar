import { apiFetch, authHeaders } from './api';

export interface AiTelemetry {
  generated_at: string;
  overview: {
    total_calls: number;
    failure_count: number;
    failure_rate: number;
    fallback_rate: number;
    total_cost_cents: number;
    total_tokens: number;
    p95_latency_ms: number;
  };
  by_task: Array<{
    surface: string;
    task_name: string;
    calls: number;
    cost_cents: number;
    failures: number;
  }>;
  search_freshness: {
    document_count: number;
    stale_document_count: number;
  };
  queue_health: {
    queued_shadow_runs: number;
  };
  experiment_guardrails: {
    running_experiments: number;
    paused_experiments: number;
    pending_promotion_reports: number;
  };
}

export interface AiRun {
  id: string;
  user_id: string | null;
  surface: string;
  task_name: string;
  provider: string;
  model: string;
  prompt_version: string;
  variant: string | null;
  status: string;
  validation_result: string | null;
  fallback_used: boolean;
  fallback_reason: string | null;
  latency_ms: number | null;
  total_tokens: number | null;
  prompt_tokens: number | null;
  output_tokens: number | null;
  cost_estimate_cents: number | null;
  created_at: string | null;
}

export interface AiArtifact {
  id: string;
  user_id: string | null;
  model_call_id: string | null;
  artifact_type: string;
  artifact_ref_id: string | null;
  title: string | null;
  path: string | null;
  metadata: Record<string, unknown>;
  created_at: string | null;
}

export interface AiRunDetail {
  run: AiRun;
  request_metadata: Record<string, unknown>;
  response_metadata: Record<string, unknown>;
  artifacts: AiArtifact[];
  full_trace_available: boolean;
  full_trace_requires_reason: boolean;
}

export interface AiExperiment {
  id: string;
  experiment_key: string;
  surface: string;
  task_name: string;
  status: string;
  control_variant: string;
  candidate_variants: string[];
  traffic_allocation: Record<string, number>;
  guardrail_thresholds: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
}

export interface AiModelCard {
  id: string;
  task_name: string;
  model: string;
  prompt_version: string;
  approval_status: string;
  primary_metrics: Record<string, unknown>;
  guardrail_metrics: Record<string, unknown>;
  updated_at: string | null;
}

export interface AiPromotionReport {
  id: string;
  experiment_id: string;
  status: string;
  recommendation: string;
  generated_after_calls: number;
  generated_after_feedback: number;
  report: Record<string, unknown>;
  created_at: string | null;
  reviewed_at: string | null;
}

export interface AiTraceAccessLog {
  id: string;
  admin_user_id: string | null;
  action: string;
  target_type: string;
  target_id: string | null;
  reason: string;
  metadata: Record<string, unknown>;
  created_at: string | null;
}

async function readErrorDetail(res: Response, fallback: string): Promise<string> {
  const payload = await res.json().catch(() => null);
  if (typeof payload?.detail === 'string') return payload.detail;
  if (typeof payload?.message === 'string') return payload.message;
  return fallback;
}

async function requestJson<T>(path: string, options: RequestInit = {}, fallback = 'AI Ops request failed.'): Promise<T> {
  const res = await apiFetch(path, {
    ...options,
    headers: {
      ...authHeaders(),
      ...(options.headers as Record<string, string> | undefined),
    },
  });
  if (!res.ok) {
    throw new Error(await readErrorDetail(res, fallback));
  }
  return res.json() as Promise<T>;
}

export function fetchAiTelemetry(): Promise<AiTelemetry> {
  return requestJson('/api/admin/ai/telemetry', {}, 'Failed to load AI telemetry.');
}

export async function fetchAiRuns(): Promise<AiRun[]> {
  const payload = await requestJson<{ runs: AiRun[] }>('/api/admin/ai/runs', {}, 'Failed to load AI runs.');
  return payload.runs;
}

export function fetchAiRunDetail(runId: string): Promise<AiRunDetail> {
  return requestJson(`/api/admin/ai/runs/${encodeURIComponent(runId)}`, {}, 'Failed to load AI run detail.');
}

export function requestFullTrace(runId: string, reason: string): Promise<Record<string, unknown>> {
  return requestJson(
    `/api/admin/ai/runs/${encodeURIComponent(runId)}/trace-access`,
    {
      method: 'POST',
      body: JSON.stringify({ reason }),
    },
    'Failed to request full trace.'
  );
}

export async function fetchAiArtifacts(): Promise<AiArtifact[]> {
  const payload = await requestJson<{ artifacts: AiArtifact[] }>('/api/admin/ai/artifacts', {}, 'Failed to load AI artifacts.');
  return payload.artifacts;
}

export async function fetchAiExperiments(): Promise<AiExperiment[]> {
  const payload = await requestJson<{ experiments: AiExperiment[] }>('/api/admin/ai/experiments', {}, 'Failed to load AI experiments.');
  return payload.experiments;
}

export async function fetchAiModelCards(): Promise<AiModelCard[]> {
  const payload = await requestJson<{ model_cards: AiModelCard[] }>('/api/admin/ai/model-cards', {}, 'Failed to load AI model cards.');
  return payload.model_cards;
}

export async function fetchAiPromotionReports(): Promise<AiPromotionReport[]> {
  const payload = await requestJson<{ promotion_reports: AiPromotionReport[] }>('/api/admin/ai/promotion-reports', {}, 'Failed to load AI promotion reports.');
  return payload.promotion_reports;
}

export async function fetchAiTraceAccessLogs(): Promise<AiTraceAccessLog[]> {
  const payload = await requestJson<{ access_logs: AiTraceAccessLog[] }>('/api/admin/ai/trace-access-logs', {}, 'Failed to load AI trace access logs.');
  return payload.access_logs;
}

export function approvePromotionReport(reportId: string): Promise<{ status: string; recommendation: string }> {
  return requestJson(`/api/admin/ai/promotion-reports/${encodeURIComponent(reportId)}/approve`, { method: 'POST' });
}

export function rejectPromotionReport(reportId: string): Promise<{ status: string; recommendation: string }> {
  return requestJson(`/api/admin/ai/promotion-reports/${encodeURIComponent(reportId)}/reject`, { method: 'POST' });
}
