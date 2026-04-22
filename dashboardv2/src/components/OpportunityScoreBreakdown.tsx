import { OpportunityScore } from '../types';

interface OpportunityScoreBreakdownProps {
  score?: OpportunityScore;
}

const SCORE_KEYS: Array<keyof OpportunityScore> = [
  'total_score',
  'role_fit',
  'domain_fit',
  'company_interest',
  'recency',
  'public_data_buildability',
  'outreach_path_strength',
  'portfolio_gap_relevance',
  'source_confidence',
];

export function OpportunityScoreBreakdown({ score }: OpportunityScoreBreakdownProps) {
  if (!score) return <div className="text-sm text-slate-500">Select a signal after a run.</div>;

  return (
    <div className="space-y-1 text-sm text-slate-600">
      {SCORE_KEYS.map((key) => (
        <div key={key} className="flex justify-between gap-4">
          <span>{key}</span>
          <span>{typeof score[key] === 'number' ? Number(score[key]).toFixed(2) : String(score[key] ?? '')}</span>
        </div>
      ))}
      {score.explanation ? <p className="pt-2 text-xs text-slate-500">{score.explanation}</p> : null}
    </div>
  );
}
