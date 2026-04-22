import { OpportunitySignal } from '../types';

interface SignalCardProps {
  signal: OpportunitySignal;
  selected?: boolean;
  onSelect?: (signal: OpportunitySignal) => void;
}

function formatLabel(value: string): string {
  return value.replaceAll('_', ' ');
}

export function SignalCard({ signal, selected = false, onSelect }: SignalCardProps) {
  const evidenceLinks = (signal.evidence || []).map((entry) => entry.url).filter(Boolean) as string[];

  return (
    <button
      type="button"
      onClick={() => onSelect?.(signal)}
      className={`w-full rounded-xl border p-3 text-left transition ${selected ? 'border-slate-400 bg-slate-50 shadow-sm' : 'border-slate-200 hover:bg-slate-50'}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-slate-500">{formatLabel(signal.event_type)}</div>
          <div className="mt-1 text-sm font-semibold text-slate-900">{signal.title}</div>
        </div>
        <div className="rounded-full bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
          {signal.score?.total_score ?? '—'}
        </div>
      </div>

      {signal.summary ? <div className="mt-2 text-sm leading-6 text-slate-600">{signal.summary}</div> : null}

      <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-slate-500">
        {signal.roles.slice(0, 3).map((role) => (
          <span key={role} className="rounded-full border border-slate-200 px-2 py-1">{role}</span>
        ))}
        {signal.domains.slice(0, 3).map((domain) => (
          <span key={domain} className="rounded-full border border-slate-200 px-2 py-1">{formatLabel(domain)}</span>
        ))}
        {signal.tech_stack.slice(0, 3).map((tech) => (
          <span key={tech} className="rounded-full border border-slate-200 px-2 py-1">{tech}</span>
        ))}
      </div>

      <div className="mt-3 flex items-center justify-between gap-3 text-[11px] text-slate-500">
        <span>Confidence {Math.round((signal.confidence || 0) * 100)}%</span>
        <span>{signal.occurred_at ? new Date(signal.occurred_at).toLocaleDateString() : 'No event date'}</span>
      </div>

      {evidenceLinks.length ? (
        <div className="mt-2 line-clamp-2 text-[11px] text-slate-500">
          Evidence: {evidenceLinks.join(', ')}
        </div>
      ) : null}
    </button>
  );
}
