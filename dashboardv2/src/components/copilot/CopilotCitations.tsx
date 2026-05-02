import { BriefcaseBusiness, Mail, Radar, Search, Users, type LucideIcon } from 'lucide-react';
import { CopilotCitation } from '../../lib/copilotApi';
import { cn } from '../../lib/utils';

interface CopilotCitationsProps {
  citations: CopilotCitation[];
  onNavigate?: (actionUrl: string) => void;
}

const SOURCE_META: Record<string, { label: string; className: string; icon: LucideIcon }> = {
  application: {
    label: 'Application',
    className: 'border-blue-200 bg-blue-50 text-blue-700',
    icon: BriefcaseBusiness,
  },
  email: {
    label: 'Email',
    className: 'border-amber-200 bg-amber-50 text-amber-700',
    icon: Mail,
  },
  contact: {
    label: 'Contact',
    className: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    icon: Users,
  },
  radar_report: {
    label: 'Radar',
    className: 'border-indigo-200 bg-indigo-50 text-indigo-700',
    icon: Radar,
  },
};

function citationUrl(citation: CopilotCitation): string | null {
  const sourceId = encodeURIComponent(citation.source_id);
  if (citation.source_type === 'application') {
    return `/dashboard?job_id=${sourceId}`;
  }
  if (citation.source_type === 'email') {
    return `/emails?email_id=${sourceId}&tab=emails`;
  }
  if (citation.source_type === 'contact') {
    return '/network';
  }
  if (citation.source_type === 'radar_report') {
    return `/radar?report_id=${sourceId}`;
  }
  return null;
}

export function CopilotCitations({ citations, onNavigate }: CopilotCitationsProps) {
  if (citations.length === 0) return null;

  return (
    <div className="mt-3 space-y-2" aria-label="Copilot citations">
      <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">
        Sources
      </div>
      <div className="space-y-2">
        {citations.map((citation) => {
          const meta = SOURCE_META[citation.source_type] || {
            label: citation.source_type.replaceAll('_', ' '),
            className: 'border-slate-200 bg-slate-50 text-slate-600',
            icon: Search,
          };
          const Icon = meta.icon;
          const url = citationUrl(citation);
          const content = (
            <div className="flex min-w-0 items-start gap-3">
              <span className={cn('mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-xl border', meta.className)}>
                <Icon className="h-3.5 w-3.5" />
              </span>
              <span className="min-w-0 text-left">
                <span className="block text-xs font-semibold text-slate-800 [overflow-wrap:anywhere]">
                  {citation.title}
                </span>
                <span className="mt-1 inline-flex rounded-md border border-slate-200 bg-white px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                  {meta.label}
                </span>
                {citation.snippet ? (
                  <span className="mt-1 block text-xs leading-5 text-slate-500 line-clamp-2 [overflow-wrap:anywhere]">
                    {citation.snippet}
                  </span>
                ) : null}
              </span>
            </div>
          );

          if (!url || !onNavigate) {
            return (
              <div
                key={citation.document_id}
                className="rounded-2xl border border-slate-200 bg-white px-3 py-2"
              >
                {content}
              </div>
            );
          }

          return (
            <button
              key={citation.document_id}
              type="button"
              onClick={() => onNavigate(url)}
              className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 transition-colors hover:border-slate-300 hover:bg-slate-50"
              aria-label={`Open ${meta.label}: ${citation.title}`}
            >
              {content}
            </button>
          );
        })}
      </div>
    </div>
  );
}
