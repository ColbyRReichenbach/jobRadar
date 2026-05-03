import { useCallback, useEffect, useMemo, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import {
  Activity,
  AlertTriangle,
  BrainCircuit,
  CheckCircle2,
  Clock3,
  Coins,
  Eye,
  FileText,
  FlaskConical,
  Gauge,
  Layers3,
  Loader2,
  LockKeyhole,
  RefreshCw,
  ShieldCheck,
  XCircle,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import type {
  AiArtifact,
  AiExperiment,
  AiModelCard,
  AiPromotionReport,
  AiRun,
  AiRunDetail,
  AiSafetyDecision,
  AiTelemetry,
  AiTraceAccessLog,
} from '../../lib/adminAiApi';
import {
  approvePromotionReport,
  fetchAiArtifacts,
  fetchAiExperiments,
  fetchAiModelCards,
  fetchAiPromotionReports,
  fetchAiRunDetail,
  fetchAiRuns,
  fetchAiSafetyDecisions,
  fetchAiTelemetry,
  fetchAiTraceAccessLogs,
  rejectPromotionReport,
  requestFullTrace,
} from '../../lib/adminAiApi';

type SectionId = 'overview' | 'runs' | 'artifacts' | 'experiments' | 'models' | 'promotions' | 'safety' | 'access';

const SECTIONS: Array<{ id: SectionId; label: string; icon: typeof Activity }> = [
  { id: 'overview', label: 'Overview', icon: Activity },
  { id: 'runs', label: 'Runs', icon: Gauge },
  { id: 'artifacts', label: 'Artifacts', icon: Layers3 },
  { id: 'experiments', label: 'Experiments', icon: FlaskConical },
  { id: 'models', label: 'Models', icon: BrainCircuit },
  { id: 'promotions', label: 'Promotions', icon: CheckCircle2 },
  { id: 'safety', label: 'Safety', icon: ShieldCheck },
  { id: 'access', label: 'Access Logs', icon: LockKeyhole },
];

function formatDate(value: string | null): string {
  if (!value) return 'Not recorded';
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value));
}

function formatNumber(value: number | null | undefined): string {
  return new Intl.NumberFormat().format(value ?? 0);
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function formatCost(cents: number | null | undefined): string {
  return new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD' }).format((cents ?? 0) / 100);
}

function jsonPreview(value: Record<string, unknown>): string {
  const text = JSON.stringify(value, null, 2);
  return text === '{}' ? 'No metadata recorded.' : text;
}

function statusTone(status: string): string {
  const normalized = status.toLowerCase();
  if (['success', 'valid', 'approved', 'running', 'active'].includes(normalized)) {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  }
  if (['pending_review', 'queued', 'draft', 'paused'].includes(normalized)) {
    return 'border-amber-200 bg-amber-50 text-amber-700';
  }
  if (['failed', 'rejected', 'invalid', 'error'].includes(normalized)) {
    return 'border-red-200 bg-red-50 text-red-700';
  }
  return 'border-slate-200 bg-slate-50 text-slate-600';
}

function StatusPill({ status }: { status: string }) {
  return (
    <span className={cn('inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold capitalize', statusTone(status))}>
      {status.replaceAll('_', ' ')}
    </span>
  );
}

function SectionShell({ title, icon: Icon, children }: { title: string; icon: typeof Activity; children: ReactNode }) {
  return (
    <section className="min-w-0 rounded-2xl border border-slate-200/70 bg-white p-4 shadow-sm md:p-5">
      <div className="mb-4 flex items-center gap-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-slate-100 text-slate-700">
          <Icon className="h-4 w-4" />
        </div>
        <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
      </div>
      {children}
    </section>
  );
}

function StatCard({ label, value, icon: Icon, detail }: { label: string; value: string; icon: typeof Activity; detail?: string }) {
  return (
    <div className="rounded-2xl border border-slate-200/70 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
        <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-slate-100 text-slate-700">
          <Icon className="h-4 w-4" />
        </div>
      </div>
      <p className="text-2xl font-semibold tracking-tight text-slate-900">{value}</p>
      {detail && <p className="mt-1 text-xs text-slate-500">{detail}</p>}
    </div>
  );
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50/70 px-4 py-10 text-center text-sm text-slate-500">
      {label}
    </div>
  );
}

export function AiOps() {
  const [activeSection, setActiveSection] = useState<SectionId>('overview');
  const [telemetry, setTelemetry] = useState<AiTelemetry | null>(null);
  const [runs, setRuns] = useState<AiRun[]>([]);
  const [artifacts, setArtifacts] = useState<AiArtifact[]>([]);
  const [experiments, setExperiments] = useState<AiExperiment[]>([]);
  const [modelCards, setModelCards] = useState<AiModelCard[]>([]);
  const [promotionReports, setPromotionReports] = useState<AiPromotionReport[]>([]);
  const [safetyDecisions, setSafetyDecisions] = useState<AiSafetyDecision[]>([]);
  const [accessLogs, setAccessLogs] = useState<AiTraceAccessLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedRunDetail, setSelectedRunDetail] = useState<AiRunDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const [traceReason, setTraceReason] = useState('');
  const [traceLoading, setTraceLoading] = useState(false);
  const [traceError, setTraceError] = useState('');
  const [fullTrace, setFullTrace] = useState<Record<string, unknown> | null>(null);
  const [promotionBusyId, setPromotionBusyId] = useState<string | null>(null);
  const [surfaceFilter, setSurfaceFilter] = useState('');
  const [taskFilter, setTaskFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [safetySurfaceFilter, setSafetySurfaceFilter] = useState('');
  const [safetyTaskFilter, setSafetyTaskFilter] = useState('');
  const [safetyPolicyFilter, setSafetyPolicyFilter] = useState('');
  const [safetyStageFilter, setSafetyStageFilter] = useState('');
  const [safetyMinRiskFilter, setSafetyMinRiskFilter] = useState('');

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [telemetryData, runsData, artifactData, experimentData, modelCardData, promotionData, safetyData, accessLogData] = await Promise.all([
        fetchAiTelemetry(),
        fetchAiRuns(),
        fetchAiArtifacts(),
        fetchAiExperiments(),
        fetchAiModelCards(),
        fetchAiPromotionReports(),
        fetchAiSafetyDecisions({
          surface: safetySurfaceFilter,
          task_name: safetyTaskFilter,
          policy_decision: safetyPolicyFilter,
          stage: safetyStageFilter,
          min_risk: safetyMinRiskFilter,
        }),
        fetchAiTraceAccessLogs(),
      ]);
      setTelemetry(telemetryData);
      setRuns(runsData);
      setArtifacts(artifactData);
      setExperiments(experimentData);
      setModelCards(modelCardData);
      setPromotionReports(promotionData);
      setSafetyDecisions(safetyData);
      setAccessLogs(accessLogData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load AI Ops data.');
    } finally {
      setLoading(false);
    }
  }, [safetyMinRiskFilter, safetyPolicyFilter, safetyStageFilter, safetySurfaceFilter, safetyTaskFilter]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const openRun = useCallback(async (runId: string) => {
    setSelectedRunId(runId);
    setSelectedRunDetail(null);
    setDetailError('');
    setTraceError('');
    setTraceReason('');
    setFullTrace(null);
    setDetailLoading(true);
    try {
      setSelectedRunDetail(await fetchAiRunDetail(runId));
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : 'Failed to load AI run detail.');
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const handleTraceAccess = useCallback(async (event: FormEvent) => {
    event.preventDefault();
    if (!selectedRunId) return;
    setTraceLoading(true);
    setTraceError('');
    setFullTrace(null);
    try {
      const trace = await requestFullTrace(selectedRunId, traceReason);
      setFullTrace(trace);
      setTraceReason('');
      setAccessLogs(await fetchAiTraceAccessLogs());
    } catch (err) {
      setTraceError(err instanceof Error ? err.message : 'Failed to request full trace.');
    } finally {
      setTraceLoading(false);
    }
  }, [selectedRunId, traceReason]);

  const filteredRuns = useMemo(() => {
    return runs.filter((run) => {
      const surfaceMatch = !surfaceFilter || run.surface.toLowerCase().includes(surfaceFilter.toLowerCase());
      const taskMatch = !taskFilter || run.task_name.toLowerCase().includes(taskFilter.toLowerCase());
      const statusMatch = statusFilter === 'all' || run.status === statusFilter;
      return surfaceMatch && taskMatch && statusMatch;
    });
  }, [runs, surfaceFilter, taskFilter, statusFilter]);

  const runStatuses = useMemo(() => Array.from(new Set(runs.map((run) => run.status))).sort(), [runs]);
  const selectedRun = selectedRunId ? runs.find((run) => run.id === selectedRunId) ?? null : null;

  const handlePromotionAction = useCallback(async (reportId: string, action: 'approve' | 'reject') => {
    setPromotionBusyId(reportId);
    setError('');
    try {
      if (action === 'approve') {
        await approvePromotionReport(reportId);
      } else {
        await rejectPromotionReport(reportId);
      }
      setPromotionReports(await fetchAiPromotionReports());
      setTelemetry(await fetchAiTelemetry());
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to ${action} promotion report.`);
    } finally {
      setPromotionBusyId(null);
    }
  }, []);

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center bg-[#F5F5F0]">
        <div className="text-center">
          <Loader2 className="mx-auto mb-3 h-8 w-8 animate-spin text-slate-500" />
          <p className="font-serif italic text-slate-500">Loading AI Ops...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-w-0 flex-1 overflow-y-auto overflow-x-hidden bg-[#F5F5F0] p-4 md:p-6">
      <div className="mx-auto flex w-full max-w-7xl min-w-0 flex-col gap-5">
        <header className="flex min-w-0 flex-col gap-4 lg:flex-row lg:items-end lg:justify-between lg:pr-14 xl:pr-0">
          <div className="min-w-0">
            <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-600 shadow-sm">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
              Admin-only governance
            </div>
            <h1 className="font-serif text-3xl font-bold tracking-tight text-slate-950">AI Ops</h1>
            <p className="mt-1 max-w-2xl text-sm text-slate-600">
              Review model calls, cost, lineage, experiments, promotion reports, and reason-gated trace access.
            </p>
          </div>
          <button
            onClick={() => void loadAll()}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:bg-slate-50"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
        </header>

        {error && (
          <div className="flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <div className="flex-1">{error}</div>
            <button
              onClick={() => setError('')}
              aria-label="Dismiss AI Ops error"
              className="text-red-500 transition-colors hover:text-red-700"
            >
              <XCircle className="h-4 w-4" />
            </button>
          </div>
        )}

        <div className="max-w-full overflow-x-auto rounded-2xl border border-slate-200/70 bg-white p-1 shadow-sm">
          <div className="flex w-max min-w-full gap-2">
            {SECTIONS.map((section) => {
              const Icon = section.icon;
              const isActive = activeSection === section.id;
              return (
                <button
                  key={section.id}
                  onClick={() => setActiveSection(section.id)}
                  className={cn(
                    'flex shrink-0 items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium transition-colors',
                    isActive ? 'bg-slate-900 text-white shadow-sm' : 'text-slate-500 hover:bg-slate-100 hover:text-slate-900'
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {section.label}
                </button>
              );
            })}
          </div>
        </div>

        {activeSection === 'overview' && telemetry && (
          <div className="space-y-5">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard label="Model Calls" value={formatNumber(telemetry.overview.total_calls)} icon={BrainCircuit} detail={`Generated ${formatDate(telemetry.generated_at)}`} />
              <StatCard label="Estimated Cost" value={formatCost(telemetry.overview.total_cost_cents)} icon={Coins} detail={`${formatNumber(telemetry.overview.total_tokens)} total tokens`} />
              <StatCard label="p95 Latency" value={`${formatNumber(telemetry.overview.p95_latency_ms)} ms`} icon={Clock3} detail={`${formatPercent(telemetry.overview.fallback_rate)} fallback rate`} />
              <StatCard label="Failure Rate" value={formatPercent(telemetry.overview.failure_rate)} icon={AlertTriangle} detail={`${formatNumber(telemetry.overview.failure_count)} failed calls`} />
            </div>
            <div className="grid gap-5 2xl:grid-cols-[minmax(0,1.4fr)_minmax(320px,0.6fr)]">
              <SectionShell title="Cost And Reliability By Task" icon={Gauge}>
                {telemetry.by_task.length === 0 ? (
                  <EmptyState label="No model calls have been recorded yet." />
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[620px] text-sm">
                      <thead>
                        <tr className="border-b border-slate-100 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                          <th className="py-2 pr-4">Surface</th>
                          <th className="py-2 pr-4">Task</th>
                          <th className="py-2 pr-4 text-right">Calls</th>
                          <th className="py-2 pr-4 text-right">Cost</th>
                          <th className="py-2 text-right">Failures</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {telemetry.by_task.map((row) => (
                          <tr key={`${row.surface}:${row.task_name}`} className="text-slate-700">
                            <td className="py-3 pr-4 font-medium text-slate-900">{row.surface}</td>
                            <td className="py-3 pr-4">{row.task_name}</td>
                            <td className="py-3 pr-4 text-right">{formatNumber(row.calls)}</td>
                            <td className="py-3 pr-4 text-right">{formatCost(row.cost_cents)}</td>
                            <td className="py-3 text-right">{formatNumber(row.failures)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </SectionShell>
              <SectionShell title="Operational Guardrails" icon={ShieldCheck}>
                <div className="grid gap-3">
                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                    <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Search Freshness</p>
                    <p className="mt-1 text-lg font-semibold text-slate-900">
                      {formatNumber(telemetry.search_freshness.stale_document_count)} stale / {formatNumber(telemetry.search_freshness.document_count)} indexed
                    </p>
                  </div>
                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                    <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Shadow Queue</p>
                    <p className="mt-1 text-lg font-semibold text-slate-900">{formatNumber(telemetry.queue_health.queued_shadow_runs)} queued runs</p>
                  </div>
                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                    <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Experiments</p>
                    <p className="mt-1 text-lg font-semibold text-slate-900">
                      {formatNumber(telemetry.experiment_guardrails.running_experiments)} running, {formatNumber(telemetry.experiment_guardrails.paused_experiments)} paused
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      {formatNumber(telemetry.experiment_guardrails.pending_promotion_reports)} promotion reports pending review
                    </p>
                  </div>
                  {telemetry.safety_guardrails && (
                    <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Safety Gateway</p>
                      <p className="mt-1 text-lg font-semibold text-slate-900">
                        {formatNumber(telemetry.safety_guardrails.redacted_decisions)} redacted
                      </p>
                      <p className="mt-1 text-xs text-slate-500">
                        {formatNumber(telemetry.safety_guardrails.blocked_decisions)} blocked before model access
                      </p>
                    </div>
                  )}
                </div>
              </SectionShell>
            </div>
          </div>
        )}

        {activeSection === 'runs' && (
          <div className="grid min-w-0 gap-5 2xl:grid-cols-[minmax(0,1fr)_minmax(360px,420px)]">
            <SectionShell title="Runs" icon={Gauge}>
              <div className="mb-4 grid min-w-0 gap-2 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(150px,180px)]">
                <input
                  value={surfaceFilter}
                  onChange={(event) => setSurfaceFilter(event.target.value)}
                  placeholder="Filter surface"
                  className="min-w-0 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm outline-none transition-colors focus:border-slate-400"
                />
                <input
                  value={taskFilter}
                  onChange={(event) => setTaskFilter(event.target.value)}
                  placeholder="Filter task"
                  className="min-w-0 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm outline-none transition-colors focus:border-slate-400"
                />
                <select
                  value={statusFilter}
                  onChange={(event) => setStatusFilter(event.target.value)}
                  className="min-w-0 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm outline-none transition-colors focus:border-slate-400"
                >
                  <option value="all">All statuses</option>
                  {runStatuses.map((status) => <option key={status} value={status}>{status}</option>)}
                </select>
              </div>
              {filteredRuns.length === 0 ? (
                <EmptyState label="No AI runs match the current filters." />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[760px] text-sm">
                    <thead>
                      <tr className="border-b border-slate-100 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                        <th className="py-2 pr-4">Run</th>
                        <th className="py-2 pr-4">Model</th>
                        <th className="py-2 pr-4">Prompt</th>
                        <th className="py-2 pr-4">Status</th>
                        <th className="py-2 pr-4 text-right">Latency</th>
                        <th className="py-2 pr-4 text-right">Tokens</th>
                        <th className="py-2 text-right">Cost</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {filteredRuns.map((run) => (
                        <tr
                          key={run.id}
                          onClick={() => void openRun(run.id)}
                          className={cn(
                            'cursor-pointer text-slate-700 transition-colors hover:bg-slate-50',
                            selectedRunId === run.id && 'bg-slate-50'
                          )}
                        >
                          <td className="py-3 pr-4">
                            <p className="font-medium text-slate-900">{run.surface}</p>
                            <p className="text-xs text-slate-500">{run.task_name}</p>
                          </td>
                          <td className="py-3 pr-4">{run.model}</td>
                          <td className="py-3 pr-4">
                            <p>{run.prompt_version}</p>
                            <p className="text-xs text-slate-500">{run.variant || 'no variant'}</p>
                          </td>
                          <td className="py-3 pr-4"><StatusPill status={run.status} /></td>
                          <td className="py-3 pr-4 text-right">{formatNumber(run.latency_ms)} ms</td>
                          <td className="py-3 pr-4 text-right">{formatNumber(run.total_tokens)}</td>
                          <td className="py-3 text-right">{formatCost(run.cost_estimate_cents)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </SectionShell>
            <RunDetailPanel
              run={selectedRun}
              detail={selectedRunDetail}
              loading={detailLoading}
              error={detailError}
              traceReason={traceReason}
              traceLoading={traceLoading}
              traceError={traceError}
              fullTrace={fullTrace}
              onTraceReasonChange={setTraceReason}
              onTraceAccess={handleTraceAccess}
            />
          </div>
        )}

        {activeSection === 'artifacts' && (
          <SectionShell title="Artifact Lineage" icon={Layers3}>
            {artifacts.length === 0 ? (
              <EmptyState label="No generated artifacts have been recorded yet." />
            ) : (
              <div className="grid gap-3">
                {artifacts.map((artifact) => (
                  <article key={artifact.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                      <div>
                        <p className="text-sm font-semibold text-slate-900">{artifact.title || artifact.artifact_type}</p>
                        <p className="mt-1 text-xs text-slate-500">
                          {artifact.artifact_type} · {formatDate(artifact.created_at)}
                        </p>
                      </div>
                      <button
                        onClick={() => artifact.model_call_id && void openRun(artifact.model_call_id)}
                        disabled={!artifact.model_call_id}
                        className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <Eye className="h-3.5 w-3.5" />
                        Open Run
                      </button>
                    </div>
                    <dl className="mt-3 grid gap-2 text-xs text-slate-600 md:grid-cols-3">
                      <div>
                        <dt className="font-medium text-slate-500">Model call</dt>
                        <dd className="mt-1 break-all text-slate-800">{artifact.model_call_id || 'Not linked'}</dd>
                      </div>
                      <div>
                        <dt className="font-medium text-slate-500">Reference</dt>
                        <dd className="mt-1 break-all text-slate-800">{artifact.artifact_ref_id || 'Not recorded'}</dd>
                      </div>
                      <div>
                        <dt className="font-medium text-slate-500">Path</dt>
                        <dd className="mt-1 break-all text-slate-800">{artifact.path || 'Not recorded'}</dd>
                      </div>
                    </dl>
                    <pre className="mt-3 max-h-48 overflow-auto rounded-xl bg-white p-3 text-xs text-slate-700">{jsonPreview(artifact.metadata)}</pre>
                  </article>
                ))}
              </div>
            )}
          </SectionShell>
        )}

        {activeSection === 'experiments' && (
          <SectionShell title="Experiment Guardrails" icon={FlaskConical}>
            {experiments.length === 0 ? (
              <EmptyState label="No governed experiments have been configured yet." />
            ) : (
              <div className="grid gap-3">
                {experiments.map((experiment) => (
                  <article key={experiment.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                      <div>
                        <p className="text-sm font-semibold text-slate-900">{experiment.experiment_key}</p>
                        <p className="mt-1 text-xs text-slate-500">{experiment.surface} · {experiment.task_name}</p>
                      </div>
                      <StatusPill status={experiment.status} />
                    </div>
                    <div className="mt-4 grid gap-3 md:grid-cols-3">
                      <MetricBlock label="Control" value={experiment.control_variant} />
                      <MetricBlock label="Candidates" value={experiment.candidate_variants.join(', ') || 'None'} />
                      <MetricBlock label="Updated" value={formatDate(experiment.updated_at)} />
                    </div>
                    <div className="mt-3 grid gap-3 lg:grid-cols-2">
                      <pre className="max-h-48 overflow-auto rounded-xl bg-white p-3 text-xs text-slate-700">{jsonPreview(experiment.traffic_allocation)}</pre>
                      <pre className="max-h-48 overflow-auto rounded-xl bg-white p-3 text-xs text-slate-700">{jsonPreview(experiment.guardrail_thresholds)}</pre>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </SectionShell>
        )}

        {activeSection === 'models' && (
          <SectionShell title="Model Cards" icon={BrainCircuit}>
            {modelCards.length === 0 ? (
              <EmptyState label="No model cards have been published yet." />
            ) : (
              <div className="grid gap-3 lg:grid-cols-2">
                {modelCards.map((card) => (
                  <article key={card.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                      <div>
                        <p className="text-sm font-semibold text-slate-900">{card.task_name}</p>
                        <p className="mt-1 text-xs text-slate-500">{card.model} · {card.prompt_version}</p>
                      </div>
                      <StatusPill status={card.approval_status} />
                    </div>
                    <div className="mt-3 grid gap-3">
                      <div>
                        <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Primary Metrics</p>
                        <pre className="max-h-48 overflow-auto rounded-xl bg-white p-3 text-xs text-slate-700">{jsonPreview(card.primary_metrics)}</pre>
                      </div>
                      <div>
                        <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Guardrails</p>
                        <pre className="max-h-48 overflow-auto rounded-xl bg-white p-3 text-xs text-slate-700">{jsonPreview(card.guardrail_metrics)}</pre>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </SectionShell>
        )}

        {activeSection === 'promotions' && (
          <SectionShell title="Promotion Reports" icon={CheckCircle2}>
            {promotionReports.length === 0 ? (
              <EmptyState label="No promotion reports are waiting for review." />
            ) : (
              <div className="grid gap-3">
                {promotionReports.map((report) => (
                  <article key={report.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-semibold text-slate-900">{report.recommendation.replaceAll('_', ' ')}</p>
                          <StatusPill status={report.status} />
                        </div>
                        <p className="mt-1 text-xs text-slate-500">
                          {formatNumber(report.generated_after_calls)} calls · {formatNumber(report.generated_after_feedback)} feedback events · {formatDate(report.created_at)}
                        </p>
                      </div>
                      {report.status === 'pending_review' && (
                        <div className="flex gap-2">
                          <button
                            onClick={() => void handlePromotionAction(report.id, 'reject')}
                            disabled={promotionBusyId === report.id}
                            className="inline-flex items-center gap-2 rounded-xl border border-red-200 bg-white px-3 py-2 text-xs font-medium text-red-700 transition-colors hover:bg-red-50 disabled:opacity-50"
                          >
                            <XCircle className="h-3.5 w-3.5" />
                            Reject
                          </button>
                          <button
                            onClick={() => void handlePromotionAction(report.id, 'approve')}
                            disabled={promotionBusyId === report.id}
                            className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-slate-700 disabled:opacity-50"
                          >
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            Approve
                          </button>
                        </div>
                      )}
                    </div>
                    <pre className="mt-3 max-h-80 overflow-auto rounded-xl bg-white p-3 text-xs text-slate-700">{jsonPreview(report.report)}</pre>
                  </article>
                ))}
              </div>
            )}
          </SectionShell>
        )}

        {activeSection === 'safety' && (
          <SectionShell title="Safety Decisions" icon={ShieldCheck}>
            <div className="mb-4 grid gap-2 rounded-2xl border border-slate-200 bg-slate-50/70 p-3 md:grid-cols-2 xl:grid-cols-5">
              <label className="grid gap-1 text-xs font-medium text-slate-600">
                Surface
                <input
                  value={safetySurfaceFilter}
                  onChange={(event) => setSafetySurfaceFilter(event.target.value)}
                  placeholder="copilot"
                  className="min-w-0 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm outline-none transition focus:border-slate-400"
                />
              </label>
              <label className="grid gap-1 text-xs font-medium text-slate-600">
                Task
                <input
                  value={safetyTaskFilter}
                  onChange={(event) => setSafetyTaskFilter(event.target.value)}
                  placeholder="copilot_answer"
                  className="min-w-0 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm outline-none transition focus:border-slate-400"
                />
              </label>
              <label className="grid gap-1 text-xs font-medium text-slate-600">
                Decision
                <select
                  value={safetyPolicyFilter}
                  onChange={(event) => setSafetyPolicyFilter(event.target.value)}
                  className="min-w-0 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm outline-none transition focus:border-slate-400"
                >
                  <option value="">All decisions</option>
                  <option value="allow">Allow</option>
                  <option value="allow_redacted">Allow redacted</option>
                  <option value="quarantine">Quarantine</option>
                  <option value="block">Block</option>
                </select>
              </label>
              <label className="grid gap-1 text-xs font-medium text-slate-600">
                Stage
                <select
                  value={safetyStageFilter}
                  onChange={(event) => setSafetyStageFilter(event.target.value)}
                  className="min-w-0 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm outline-none transition focus:border-slate-400"
                >
                  <option value="">All stages</option>
                  <option value="preflight">Preflight</option>
                  <option value="postflight">Postflight</option>
                </select>
              </label>
              <label className="grid gap-1 text-xs font-medium text-slate-600">
                Minimum risk
                <input
                  type="number"
                  min="0"
                  max="1"
                  step="0.05"
                  value={safetyMinRiskFilter}
                  onChange={(event) => setSafetyMinRiskFilter(event.target.value)}
                  placeholder="0.70"
                  className="min-w-0 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm outline-none transition focus:border-slate-400"
                />
              </label>
            </div>
            {safetyDecisions.length === 0 ? (
              <EmptyState label="No safety gateway decisions have been recorded yet." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[900px] text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                      <th className="py-2 pr-4">Time</th>
                      <th className="py-2 pr-4">Surface</th>
                      <th className="py-2 pr-4">Stage</th>
                      <th className="py-2 pr-4">Decision</th>
                      <th className="py-2 pr-4 text-right">Risk</th>
                      <th className="py-2 pr-4">Redactions</th>
                      <th className="py-2">Reasons</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {safetyDecisions.map((decision) => (
                      <tr key={decision.id} className="text-slate-700">
                        <td className="py-3 pr-4 whitespace-nowrap">{formatDate(decision.created_at)}</td>
                        <td className="py-3 pr-4">
                          <p className="font-medium text-slate-900">{decision.surface}</p>
                          <p className="text-xs text-slate-500">{decision.task_name}</p>
                        </td>
                        <td className="py-3 pr-4 capitalize">{decision.stage}</td>
                        <td className="py-3 pr-4"><StatusPill status={decision.policy_decision} /></td>
                        <td className="py-3 pr-4 text-right">
                          <p className="font-medium text-slate-900">{decision.risk_score.toFixed(2)}</p>
                          <p className="text-xs text-slate-500">PI {formatNumber(Math.round((decision.prompt_injection_score ?? 0) * 100))}%</p>
                        </td>
                        <td className="py-3 pr-4">
                          <pre className="max-h-28 max-w-xs overflow-auto rounded-xl bg-slate-50 p-2 text-xs">{jsonPreview(decision.redaction_counts)}</pre>
                        </td>
                        <td className="py-3">
                          <div className="flex max-w-sm flex-wrap gap-1">
                            {decision.reasons.length === 0 ? (
                              <span className="text-xs text-slate-500">No issues detected</span>
                            ) : (
                              decision.reasons.map((reason) => (
                                <span key={reason} className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-medium text-slate-600">
                                  {reason.replaceAll('_', ' ')}
                                </span>
                              ))
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </SectionShell>
        )}

        {activeSection === 'access' && (
          <SectionShell title="Trace Access Audit Log" icon={LockKeyhole}>
            {accessLogs.length === 0 ? (
              <EmptyState label="No full-trace access has been requested yet." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px] text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                      <th className="py-2 pr-4">Time</th>
                      <th className="py-2 pr-4">Action</th>
                      <th className="py-2 pr-4">Target</th>
                      <th className="py-2 pr-4">Reason</th>
                      <th className="py-2">Metadata</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {accessLogs.map((log) => (
                      <tr key={log.id} className="text-slate-700">
                        <td className="py-3 pr-4 whitespace-nowrap">{formatDate(log.created_at)}</td>
                        <td className="py-3 pr-4">{log.action.replaceAll('_', ' ')}</td>
                        <td className="py-3 pr-4">
                          <p>{log.target_type}</p>
                          <p className="max-w-[220px] truncate text-xs text-slate-500">{log.target_id || 'not recorded'}</p>
                        </td>
                        <td className="py-3 pr-4 max-w-sm">{log.reason}</td>
                        <td className="py-3">
                          <pre className="max-h-32 max-w-xs overflow-auto rounded-xl bg-slate-50 p-2 text-xs">{jsonPreview(log.metadata)}</pre>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </SectionShell>
        )}
      </div>
    </div>
  );
}

function MetricBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 break-words text-sm font-semibold text-slate-900">{value}</p>
    </div>
  );
}

function RunDetailPanel({
  run,
  detail,
  loading,
  error,
  traceReason,
  traceLoading,
  traceError,
  fullTrace,
  onTraceReasonChange,
  onTraceAccess,
}: {
  run: AiRun | null;
  detail: AiRunDetail | null;
  loading: boolean;
  error: string;
  traceReason: string;
  traceLoading: boolean;
  traceError: string;
  fullTrace: Record<string, unknown> | null;
  onTraceReasonChange: (value: string) => void;
  onTraceAccess: (event: FormEvent) => void;
}) {
  const accessLogId = typeof fullTrace?.access_log_id === 'string' ? fullTrace.access_log_id : null;

  return (
    <SectionShell title="Run Detail" icon={FileText}>
      {!run && !loading && <EmptyState label="Select a run to inspect redacted lineage and trace controls." />}
      {loading && (
        <div className="flex items-center justify-center py-12 text-sm text-slate-500">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          Loading run detail...
        </div>
      )}
      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </div>
      )}
      {detail && (
        <div className="space-y-4">
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
              <div>
                <p className="text-sm font-semibold text-slate-900">{detail.run.surface} · {detail.run.task_name}</p>
                <p className="mt-1 text-xs text-slate-500">{detail.run.model} · {detail.run.prompt_version}</p>
              </div>
              <StatusPill status={detail.run.status} />
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
              <MetricBlock label="Latency" value={`${formatNumber(detail.run.latency_ms)} ms`} />
              <MetricBlock label="Tokens" value={formatNumber(detail.run.total_tokens)} />
              <MetricBlock label="Cost" value={formatCost(detail.run.cost_estimate_cents)} />
              <MetricBlock label="Created" value={formatDate(detail.run.created_at)} />
            </div>
          </div>

          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Redacted Request Metadata</p>
            <pre className="max-h-56 overflow-auto rounded-xl bg-slate-950 p-3 text-xs text-slate-100">{jsonPreview(detail.request_metadata)}</pre>
          </div>
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Redacted Response Metadata</p>
            <pre className="max-h-56 overflow-auto rounded-xl bg-slate-950 p-3 text-xs text-slate-100">{jsonPreview(detail.response_metadata)}</pre>
          </div>

          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Linked Artifacts</p>
            {detail.artifacts.length === 0 ? (
              <EmptyState label="No artifacts are linked to this run." />
            ) : (
              <div className="space-y-2">
                {detail.artifacts.map((artifact) => (
                  <div key={artifact.id} className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs">
                    <p className="font-semibold text-slate-900">{artifact.title || artifact.artifact_type}</p>
                    <p className="mt-1 break-all text-slate-500">{artifact.path || artifact.id}</p>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
            <div className="mb-3 flex items-start gap-2 text-sm text-amber-900">
              <LockKeyhole className="mt-0.5 h-4 w-4 shrink-0" />
              <p>Full trace access can expose raw prompts and sensitive metadata. A reason is required and every access is written to the admin audit log.</p>
            </div>
            <form onSubmit={onTraceAccess} className="space-y-2">
              <label className="block text-xs font-semibold uppercase tracking-wide text-amber-800" htmlFor="ai-trace-reason">
                Access Reason
              </label>
              <textarea
                id="ai-trace-reason"
                value={traceReason}
                onChange={(event) => onTraceReasonChange(event.target.value)}
                minLength={8}
                rows={3}
                placeholder="Example: Debugging groundedness issue in copilot run"
                className="w-full resize-none rounded-xl border border-amber-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none transition-colors focus:border-amber-400"
              />
              <button
                type="submit"
                disabled={traceLoading || traceReason.trim().length < 8}
                className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {traceLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Eye className="h-3.5 w-3.5" />}
                Request Full Trace
              </button>
            </form>
            {traceError && <p className="mt-2 text-sm text-red-700">{traceError}</p>}
            {fullTrace && (
              <div className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 p-3">
                <p className="flex items-center gap-2 text-sm font-medium text-emerald-800">
                  <CheckCircle2 className="h-4 w-4" />
                  Full trace access logged{accessLogId ? `: ${accessLogId}` : '.'}
                </p>
                <details className="mt-2">
                  <summary className="cursor-pointer text-xs font-medium text-emerald-700">View raw trace payload</summary>
                  <pre className="mt-2 max-h-72 overflow-auto rounded-xl bg-white p-3 text-xs text-slate-700">
                    {JSON.stringify(fullTrace, null, 2)}
                  </pre>
                </details>
              </div>
            )}
          </div>
        </div>
      )}
    </SectionShell>
  );
}
