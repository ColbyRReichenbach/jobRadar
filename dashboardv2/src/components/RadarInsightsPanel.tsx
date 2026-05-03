import { RadarFeedbackStats } from '../types';

interface RadarInsightsPanelProps {
  stats?: RadarFeedbackStats | null;
}

export function RadarInsightsPanel({ stats }: RadarInsightsPanelProps) {
  if (!stats) {
    return <div className="text-sm text-slate-500">No Radar feedback yet.</div>;
  }

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-xl border border-slate-200 p-3">
          <div className="text-[11px] uppercase tracking-wide text-slate-500">Feedback count</div>
          <div className="mt-1 text-lg font-semibold text-slate-900">{stats.total_feedback}</div>
        </div>
        <div className="rounded-xl border border-slate-200 p-3">
          <div className="text-[11px] uppercase tracking-wide text-slate-500">Useful rate</div>
          <div className="mt-1 text-lg font-semibold text-slate-900">{stats.usefulness_rate}%</div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 text-center">
        <div className="rounded-xl border border-slate-200 p-3">
          <div className="text-[11px] uppercase tracking-wide text-slate-500">Helpful</div>
          <div className="mt-1 text-base font-semibold text-slate-900">{stats.useful}</div>
        </div>
        <div className="rounded-xl border border-slate-200 p-3">
          <div className="text-[11px] uppercase tracking-wide text-slate-500">Not helpful</div>
          <div className="mt-1 text-base font-semibold text-slate-900">{stats.not_useful}</div>
        </div>
        <div className="rounded-xl border border-slate-200 p-3">
          <div className="text-[11px] uppercase tracking-wide text-slate-500">Notes</div>
          <div className="mt-1 text-base font-semibold text-slate-900">{stats.notes_count}</div>
        </div>
      </div>

      {stats.recent_feedback.length ? (
        <div>
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">Recent feedback</div>
          <div className="space-y-2">
            {stats.recent_feedback.map((item) => (
              <div key={item.id} className="rounded-xl border border-slate-200 p-3 text-xs text-slate-600">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-medium text-slate-800">{item.rating.replaceAll('_', ' ')}</div>
                  <div>{item.created_at ? new Date(item.created_at).toLocaleString() : 'Unknown date'}</div>
                </div>
                {item.notes ? <div className="mt-1 leading-5 text-slate-500">{item.notes}</div> : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
