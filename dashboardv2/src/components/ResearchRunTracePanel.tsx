import { ResearchRunTrace } from '../types';

interface ResearchRunTracePanelProps {
  trace?: ResearchRunTrace | null;
  loading?: boolean;
}

function formatDate(value?: string | null): string {
  if (!value) return 'Unknown';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function JsonBlock({ value }: { value?: Record<string, unknown> | null }) {
  if (!value || !Object.keys(value).length) return null;
  return (
    <pre className="mt-2 overflow-auto rounded-xl bg-slate-950 p-3 text-[11px] leading-5 text-slate-100">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

export function ResearchRunTracePanel({ trace, loading = false }: ResearchRunTracePanelProps) {
  if (loading) {
    return <div className="text-sm text-slate-500">Loading trace...</div>;
  }

  if (!trace) {
    return <div className="text-sm text-slate-500">Pick a run to inspect the execution trace.</div>;
  }

  return (
    <div className="space-y-3">
      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
        <div className="grid grid-cols-2 gap-3 text-xs text-slate-500 md:grid-cols-4">
          <div>
            <div className="uppercase tracking-wide">Status</div>
            <div className="mt-1 text-sm font-semibold text-slate-900">{trace.run.status}</div>
          </div>
          <div>
            <div className="uppercase tracking-wide">Mode</div>
            <div className="mt-1 text-sm font-semibold text-slate-900">{trace.run.mode || 'internal'}</div>
          </div>
          <div>
            <div className="uppercase tracking-wide">Started</div>
            <div className="mt-1 text-sm font-semibold text-slate-900">{formatDate(trace.run.started_at)}</div>
          </div>
          <div>
            <div className="uppercase tracking-wide">Completed</div>
            <div className="mt-1 text-sm font-semibold text-slate-900">{formatDate(trace.run.completed_at)}</div>
          </div>
        </div>
        {trace.run.error_message ? (
          <div className="mt-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs leading-5 text-rose-700">
            {trace.run.error_message}
          </div>
        ) : null}
      </div>

      <div className="space-y-3">
        {trace.steps.map((step) => (
          <details key={step.id} className="rounded-2xl border border-slate-200 bg-white p-4">
            <summary className="cursor-pointer list-none">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-slate-900">
                    {step.step_order}. {step.step_name}
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    {step.status}
                    {step.model_name ? ` · ${step.model_name}` : ''}
                    {step.prompt_version ? ` · ${step.prompt_version}` : ''}
                    {step.tool_name ? ` · ${step.tool_name}` : ''}
                  </div>
                </div>
                <div className="text-right text-[11px] text-slate-500">
                  <div>{formatDate(step.started_at)}</div>
                  <div>{step.tokens_in || 0} in · {step.tokens_out || 0} out</div>
                </div>
              </div>
            </summary>

            {step.error_message ? (
              <div className="mt-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs leading-5 text-rose-700">
                {step.error_message}
              </div>
            ) : null}

            <JsonBlock value={step.input_json} />
            <JsonBlock value={step.output_json} />
          </details>
        ))}
      </div>
    </div>
  );
}
