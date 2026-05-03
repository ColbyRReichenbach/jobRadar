import { OpportunitySignal } from '../types';

interface SignalDetailPanelProps {
  signal?: OpportunitySignal;
}

function formatLabel(value: string): string {
  return value.replaceAll('_', ' ');
}

export function SignalDetailPanel({ signal }: SignalDetailPanelProps) {
  if (!signal) {
    return <div className="text-sm text-slate-500">Select a signal to inspect its evidence and context.</div>;
  }

  return (
    <div className="space-y-4">
      <div>
        <div className="text-xs uppercase tracking-wide text-slate-500">{formatLabel(signal.event_type)}</div>
        <div className="mt-1 text-lg font-semibold text-slate-900">{signal.title}</div>
        {signal.summary ? <p className="mt-2 text-sm leading-6 text-slate-600">{signal.summary}</p> : null}
      </div>

      <div className="grid grid-cols-2 gap-3 text-xs text-slate-500">
        <div className="rounded-xl border border-slate-200 p-3">
          <div className="uppercase tracking-wide">Confidence</div>
          <div className="mt-1 text-base font-semibold text-slate-900">{Math.round((signal.confidence || 0) * 100)}%</div>
        </div>
        <div className="rounded-xl border border-slate-200 p-3">
          <div className="uppercase tracking-wide">Occurred</div>
          <div className="mt-1 text-base font-semibold text-slate-900">
            {signal.occurred_at ? new Date(signal.occurred_at).toLocaleDateString() : 'Unknown'}
          </div>
        </div>
      </div>

      {signal.roles.length ? (
        <div>
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">Roles</div>
          <div className="flex flex-wrap gap-2">
            {signal.roles.map((role) => (
              <span key={role} className="rounded-full border border-slate-200 px-2 py-1 text-xs text-slate-700">
                {role}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {signal.domains.length ? (
        <div>
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">Domains</div>
          <div className="flex flex-wrap gap-2">
            {signal.domains.map((domain) => (
              <span key={domain} className="rounded-full border border-slate-200 px-2 py-1 text-xs text-slate-700">
                {formatLabel(domain)}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {signal.tech_stack.length ? (
        <div>
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">Tech stack</div>
          <div className="flex flex-wrap gap-2">
            {signal.tech_stack.map((tech) => (
              <span key={tech} className="rounded-full border border-slate-200 px-2 py-1 text-xs text-slate-700">
                {tech}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      <div>
        <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">Evidence</div>
        {signal.evidence.length ? (
          <div className="space-y-2">
            {signal.evidence.map((item, index) => (
              <div key={`${item.url || 'evidence'}-${index}`} className="rounded-xl border border-slate-200 p-3 text-xs text-slate-600">
                <div className="flex flex-wrap items-center gap-2">
                  {item.source_name ? (
                    <span className="rounded-full bg-slate-100 px-2 py-1 text-[11px] text-slate-700">
                      {item.source_name.replaceAll('_', ' ')}
                    </span>
                  ) : null}
                  {item.field ? (
                    <span className="rounded-full bg-slate-100 px-2 py-1 text-[11px] text-slate-700">
                      {formatLabel(item.field)}
                    </span>
                  ) : null}
                  {typeof item.confidence === 'number' ? (
                    <span className="rounded-full bg-slate-100 px-2 py-1 text-[11px] text-slate-700">
                      {Math.round(item.confidence * 100)}%
                    </span>
                  ) : null}
                </div>
                {item.title ? <div className="mt-2 text-sm font-medium text-slate-800">{item.title}</div> : null}
                {item.excerpt ? <div className="mt-1 text-xs leading-5 text-slate-500">{item.excerpt}</div> : null}
                {item.url ? (
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-2 block break-all text-sky-700 underline"
                  >
                    {item.url}
                  </a>
                ) : (
                  <div className="mt-2 text-slate-500">No source URL on this evidence item.</div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="text-sm text-slate-500">No evidence attached to this signal.</div>
        )}
      </div>
    </div>
  );
}
