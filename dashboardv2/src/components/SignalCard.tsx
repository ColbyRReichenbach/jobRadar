import { OpportunitySignal } from '../types';

interface SignalCardProps {
  signal: OpportunitySignal;
  selected?: boolean;
  onSelect?: (signal: OpportunitySignal) => void;
}

export function SignalCard({ signal, selected = false, onSelect }: SignalCardProps) {
  return (
    <button
      type="button"
      onClick={() => onSelect?.(signal)}
      className={`w-full text-left rounded-xl border p-3 transition ${selected ? 'border-slate-400 bg-slate-50' : 'border-slate-200 hover:bg-slate-50'}`}
    >
      <div className="text-xs text-slate-500">{signal.event_type} · Score {signal.score?.total_score ?? '—'}</div>
      <div className="text-sm font-semibold text-slate-900 mt-0.5">{signal.title}</div>
      <div className="text-sm text-slate-600 mt-1">{signal.summary}</div>
      <div className="text-xs text-slate-500 mt-2">
        Evidence: {(signal.evidence || []).map((e) => e.url).filter(Boolean).join(', ') || 'n/a'}
      </div>
    </button>
  );
}
