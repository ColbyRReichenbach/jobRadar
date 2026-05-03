interface ResearchRunHistoryProps {
  runs: Array<{
    id: string;
    status: string;
    run_type?: string | null;
    mode?: string | null;
    current_step?: string | null;
    report_id?: string | null;
    created_at?: string | null;
    started_at?: string | null;
    completed_at?: string | null;
    source_counts?: Record<string, number>;
    signal_counts?: Record<string, number>;
    error_message?: string | null;
  }>;
  selectedRunId?: string | null;
  onSelectRun?: (runId: string) => void;
}

export function ResearchRunHistory({ runs, selectedRunId, onSelectRun }: ResearchRunHistoryProps) {
  if (!runs.length) return <div className="text-sm text-slate-500">No runs yet.</div>;

  return (
    <div className="space-y-2">
      {runs.slice(0, 5).map((run) => (
        <button
          key={run.id}
          type="button"
          onClick={() => onSelectRun?.(run.id)}
          className={`w-full rounded-lg border p-3 text-left text-xs text-slate-600 ${
            selectedRunId === run.id ? 'border-slate-400 bg-slate-50' : 'border-slate-200'
          }`}
        >
          <div className="flex items-center justify-between gap-3">
            <div className="font-medium text-slate-800">{run.status}</div>
            <div>{run.created_at ? new Date(run.created_at).toLocaleString() : 'Unknown date'}</div>
          </div>
          <div className="mt-2 text-[11px] text-slate-500">
            {(run.mode || 'internal').replaceAll('_', ' ')} · {(run.run_type || 'manual').replaceAll('_', ' ')}
            {run.current_step ? ` · ${run.current_step}` : ''}
          </div>
          <div className="mt-1 text-[11px] text-slate-500">
            Sources {run.source_counts?.total ?? 0} · {Object.entries(run.signal_counts || {}).map(([k, v]) => `${k}:${v}`).join(' · ') || 'No signals'}
            {run.report_id ? ' · report saved' : ''}
          </div>
          {run.error_message ? (
            <div className="mt-2 rounded-lg border border-rose-200 bg-rose-50 px-2 py-1.5 text-[11px] text-rose-700">
              {run.error_message}
            </div>
          ) : null}
        </button>
      ))}
    </div>
  );
}
