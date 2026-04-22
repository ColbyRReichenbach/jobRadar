import { OpportunityScore } from '../types';

interface OpportunityScoreBreakdownProps {
  score?: OpportunityScore;
}

const SCORE_ROWS: Array<{ key: keyof OpportunityScore; label: string }> = [
  { key: 'total_score', label: 'Total score' },
  { key: 'role_fit', label: 'Role fit' },
  { key: 'domain_fit', label: 'Domain fit' },
  { key: 'company_interest', label: 'Company interest' },
  { key: 'recency', label: 'Recency' },
  { key: 'public_data_buildability', label: 'Public data buildability' },
  { key: 'outreach_path_strength', label: 'Outreach path strength' },
  { key: 'portfolio_gap_relevance', label: 'Portfolio gap relevance' },
  { key: 'source_confidence', label: 'Source confidence' },
];

export function OpportunityScoreBreakdown({ score }: OpportunityScoreBreakdownProps) {
  if (!score) return <div className="text-sm text-slate-500">Select a signal to inspect how Radar scored it.</div>;

  return (
    <div className="space-y-2 text-sm text-slate-600">
      {SCORE_ROWS.map(({ key, label }) => (
        <div key={key} className="space-y-1">
          <div className="flex justify-between gap-4">
            <span>{label}</span>
            <span className="font-medium text-slate-800">
              {typeof score[key] === 'number' ? Number(score[key]).toFixed(key === 'total_score' ? 0 : 2) : String(score[key] ?? '')}
            </span>
          </div>
          {typeof score[key] === 'number' ? (
            <div className="h-2 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-slate-700"
                style={{ width: `${Math.max(0, Math.min(100, Number(score[key]))) }%` }}
              />
            </div>
          ) : null}
        </div>
      ))}
      {score.explanation ? <p className="pt-2 text-xs leading-5 text-slate-500">{score.explanation}</p> : null}
    </div>
  );
}
