import { useEffect, useState } from 'react';
import { CheckCircle2, Loader2, RefreshCw, ShieldAlert, XCircle } from 'lucide-react';
import {
  approveAdminJobSource,
  blockAdminJobSource,
  fetchAdminJobSourceHealth,
  fetchAdminJobSourceUsage,
  fetchAdminJobSources,
  verifyAdminJobSource,
} from '../../lib/api';
import type { AdminJobSource, AdminSourceHealth } from '../../lib/api';

interface UsageRow {
  provider: string;
  month_bucket: string | null;
  request_count: number;
  result_count: number;
}

export function SourceIntelligenceAdmin() {
  const [sources, setSources] = useState<AdminJobSource[]>([]);
  const [health, setHealth] = useState<AdminSourceHealth | null>(null);
  const [usage, setUsage] = useState<UsageRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busySourceId, setBusySourceId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [sourceData, healthData, usageData] = await Promise.all([
        fetchAdminJobSources(),
        fetchAdminJobSourceHealth(),
        fetchAdminJobSourceUsage(),
      ]);
      setSources(sourceData.sources);
      setHealth(healthData);
      setUsage(usageData.usage);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load source intelligence.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const runAction = async (id: string, action: 'verify' | 'approve' | 'block') => {
    setBusySourceId(id);
    setError(null);
    try {
      if (action === 'verify') await verifyAdminJobSource(id);
      if (action === 'approve') await approveAdminJobSource(id);
      if (action === 'block') await blockAdminJobSource(id);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to ${action} source.`);
    } finally {
      setBusySourceId(null);
    }
  };

  const totals = health?.totals;

  return (
    <div className="flex-1 overflow-y-auto bg-[#F5F5F0] p-4 md:p-8">
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Admin</p>
          <h1 className="font-serif text-3xl font-bold tracking-tight text-slate-950">Source Intelligence</h1>
        </div>
        <button
          onClick={loadData}
          disabled={loading}
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          Refresh
        </button>
      </div>

      {error && <div className="mb-5 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>}

      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <MetricCard label="Verified" value={totals?.verified || 0} />
        <MetricCard label="Pending Review" value={totals?.pending_review || 0} />
        <MetricCard label="Failed/Stale" value={totals?.failed_stale || 0} />
        <MetricCard label="Blocked" value={totals?.blocked || 0} />
        <MetricCard label="Private Rejected" value={totals?.private_links_rejected_from_sharing || 0} />
      </div>

      <div className="mb-6 rounded-2xl border border-slate-200 bg-white">
        <div className="border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-900">Source Registry</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-100 text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3 text-left">Company</th>
                <th className="px-4 py-3 text-left">Provider</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3 text-left">Access</th>
                <th className="px-4 py-3 text-left">Risk</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {sources.map((source) => (
                <tr key={source.id} className="text-slate-700">
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-900">{source.company_name}</div>
                    <div className="text-xs text-slate-500">{source.company_domain || source.provider_key || 'unmapped'}</div>
                  </td>
                  <td className="px-4 py-3">{source.provider_type}</td>
                  <td className="px-4 py-3"><StatusBadge status={source.verification_status} /></td>
                  <td className="px-4 py-3">{source.access_mode}</td>
                  <td className="px-4 py-3">{source.terms_risk}</td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-2">
                      <ActionButton label="Verify" busy={busySourceId === source.id} onClick={() => runAction(source.id, 'verify')} />
                      <ActionButton label="Approve" busy={busySourceId === source.id} onClick={() => runAction(source.id, 'approve')} />
                      <ActionButton label="Block" danger busy={busySourceId === source.id} onClick={() => runAction(source.id, 'block')} />
                    </div>
                  </td>
                </tr>
              ))}
              {!sources.length && !loading && (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-slate-500">No source records yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white">
        <div className="border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-900">Broad Provider Usage</h2>
        </div>
        <div className="divide-y divide-slate-100">
          {usage.map((row) => (
            <div key={`${row.provider}-${row.month_bucket}`} className="grid gap-2 px-4 py-3 text-sm text-slate-700 sm:grid-cols-4">
              <span className="font-medium text-slate-900">{row.provider}</span>
              <span>{row.month_bucket || 'current'}</span>
              <span>{row.request_count} requests</span>
              <span>{row.result_count} results</span>
            </div>
          ))}
          {!usage.length && <div className="px-4 py-5 text-sm text-slate-500">No broad provider usage recorded.</div>}
        </div>
      </div>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4">
      <div className="text-2xl font-bold text-slate-950">{value}</div>
      <div className="mt-1 text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles = status === 'verified'
    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
    : status === 'blocked' || status === 'failed'
      ? 'border-red-200 bg-red-50 text-red-700'
      : 'border-amber-200 bg-amber-50 text-amber-700';
  const Icon = status === 'verified' ? CheckCircle2 : status === 'blocked' || status === 'failed' ? XCircle : ShieldAlert;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold ${styles}`}>
      <Icon className="h-3.5 w-3.5" />
      {status.replace(/_/g, ' ')}
    </span>
  );
}

function ActionButton({ label, busy, danger, onClick }: { label: string; busy: boolean; danger?: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      disabled={busy}
      className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold disabled:opacity-50 ${danger ? 'border-red-100 text-red-600 hover:bg-red-50' : 'border-slate-200 text-slate-700 hover:bg-slate-50'}`}
    >
      {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
      {label}
    </button>
  );
}
