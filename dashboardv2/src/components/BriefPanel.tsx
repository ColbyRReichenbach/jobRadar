import { OpportunityBrief } from '../types';

interface BriefPanelProps {
  brief?: OpportunityBrief;
}

export function BriefPanel({ brief }: BriefPanelProps) {
  if (!brief) return <div className="text-sm text-slate-500">No brief for the selected signal yet.</div>;

  return (
    <div className="space-y-3">
      <div>
        <div className="text-sm font-semibold text-slate-900">{brief.title}</div>
        <div className="mt-1 text-xs text-slate-500">
          {brief.brief_type.replaceAll('_', ' ')} · confidence {Math.round((brief.confidence || 0) * 100)}%
        </div>
      </div>

      {brief.markdown ? (
        <div className="whitespace-pre-wrap text-sm leading-6 text-slate-600">{brief.markdown}</div>
      ) : null}

      {brief.structured_json ? (
        <details className="rounded-xl border border-slate-200 bg-slate-50 p-3">
          <summary className="cursor-pointer text-sm font-medium text-slate-800">Structured detail</summary>
          <pre className="mt-2 overflow-auto whitespace-pre-wrap text-[11px] leading-5 text-slate-500">
            {JSON.stringify(brief.structured_json, null, 2)}
          </pre>
        </details>
      ) : null}
    </div>
  );
}
