import { CheckCircle2, ShieldCheck } from 'lucide-react';
import { CopilotSuggestedAction } from '../../lib/copilotApi';

interface CopilotSuggestedActionsProps {
  actions: CopilotSuggestedAction[];
}

export function CopilotSuggestedActions({ actions }: CopilotSuggestedActionsProps) {
  if (actions.length === 0) return null;

  return (
    <div className="mt-3 space-y-2" aria-label="Copilot suggested actions">
      <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">
        Suggestions
      </div>
      <div className="space-y-2">
        {actions.map((action, index) => (
          <div
            key={`${action.title}-${index}`}
            className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2"
          >
            <div className="flex items-start gap-3">
              <span className="mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-500">
                <CheckCircle2 className="h-3.5 w-3.5" />
              </span>
              <div className="min-w-0">
                <div className="text-xs font-semibold text-slate-800 [overflow-wrap:anywhere]">
                  {action.title}
                </div>
                {action.description ? (
                  <p className="mt-1 text-xs leading-5 text-slate-500 [overflow-wrap:anywhere]">
                    {action.description}
                  </p>
                ) : null}
                <div className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                  <ShieldCheck className="h-3 w-3" />
                  Review only
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
