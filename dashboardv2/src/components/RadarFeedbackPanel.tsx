import { useState } from 'react';

interface RadarFeedbackPanelProps {
  busy?: boolean;
  message?: string | null;
  title?: string;
  description?: string;
  enabled?: boolean;
  onSubmit: (payload: { rating: string; notes?: string }) => Promise<void>;
}

export function RadarFeedbackPanel({
  busy = false,
  message,
  title = 'Was this useful?',
  description = 'Save feedback on the selected Radar output so future scoring and briefs can be tuned against real usage.',
  enabled = true,
  onSubmit,
}: RadarFeedbackPanelProps) {
  const [notes, setNotes] = useState('');

  const submit = async (rating: 'useful' | 'not_useful') => {
    await onSubmit({
      rating,
      notes: notes.trim() || undefined,
    });
    setNotes('');
  };

  return (
    <div className="space-y-3">
      <div>
        <div className="text-sm font-medium text-slate-900">{title}</div>
        <p className="mt-1 text-xs text-slate-500">{description}</p>
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
          disabled={busy || !enabled}
          onClick={() => submit('useful')}
          className="rounded-xl border border-slate-300 px-3 py-2 text-sm text-slate-700 disabled:opacity-40"
        >
          Helpful
        </button>
        <button
          type="button"
          disabled={busy || !enabled}
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
