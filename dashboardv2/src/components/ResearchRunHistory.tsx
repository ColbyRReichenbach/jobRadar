interface ResearchRunHistoryProps {
  runs: Array<{ id: string; status: string; created_at?: string | null; signal_counts?: Record<string, number> }>;
}

export function ResearchRunHistory({ runs }: ResearchRunHistoryProps) {
  if (!runs.length) return <div className="text-sm text-slate-500">No runs yet.</div>;

  return (
    <div className="space-y-2">
      {runs.slice(0, 5).map((run) => (
        <div key={run.id} className="rounded-lg border border-slate-200 p-2 text-xs text-slate-600">
          <div className="font-medium text-slate-800">{run.status}</div>
          <div>{run.created_at ? new Date(run.created_at).toLocaleString() : 'Unknown date'}</div>
          <div>{Object.entries(run.signal_counts || {}).map(([k, v]) => `${k}:${v}`).join(' · ') || 'No signals'}</div>
        </div>
      ))}
    </div>
  );
}
