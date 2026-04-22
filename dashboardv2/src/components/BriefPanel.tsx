import { OpportunityBrief } from '../types';

interface BriefPanelProps {
  brief?: OpportunityBrief;
}

export function BriefPanel({ brief }: BriefPanelProps) {
  return (
    <div className="text-sm text-slate-600 whitespace-pre-wrap">
      {brief?.markdown || 'No brief yet.'}
    </div>
  );
}
