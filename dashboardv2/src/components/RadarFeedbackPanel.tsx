import { useState } from 'react';

interface RadarFeedbackPanelProps {
  busy?: boolean;
  message?: string | null;
  signalId?: string;
  briefId?: string;
  actionId?: string;
  onSubmit: (payload: { signal_id?: string; brief_id?: string; action_id?: string; rating: string; notes?: string }) => Promise<void>;
}

export function RadarFeedbackPanel({
  busy = false,
  message,
  signalId,
  briefId,
  actionId,
  onSubmit,
}: RadarFeedbackPanelProps) {
  const [notes, setNotes] = useState('');

  const submit = async (rating: 'useful' | 'not_useful') => {
    await onSubmit({
      signal_id: signalId,
      brief_id: briefId,
      action_id: actionId,
      rating,
      notes: notes.trim() || undefined,
    });
    setNotes('');
  };

  return (
    <div className="space-y-3">
      <div>
        <div className="text-sm font-medium text-slate-900">Was this useful?</div>
        <p className="mt-1 text-xs text-slate-500">
          Save feedback on the selected Radar output so future scoring and briefs can be tuned against real usage.
        </p>
      </div>

      <textarea
        value={notes}
        onChange={(event) => setNotes(event.target.value)}
        placeholder="Optional note about what was right, wrong, or missing"
        className="min-h-[88px] w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
      />

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy || !signalId}
          onClick={() => submit('useful')}
          className="rounded-xl border border-slate-300 px-3 py-2 text-sm text-slate-700 disabled:opacity-40"
        >
          Helpful
        </button>
        <button
          type="button"
          disabled={busy || !signalId}
          onClick={() => submit('not_useful')}
          className="rounded-xl border border-slate-300 px-3 py-2 text-sm text-slate-700 disabled:opacity-40"
        >
          Not helpful
        </button>
      </div>

      {message ? (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700">
          {message}
        </div>
      ) : null}
    </div>
  );
}
