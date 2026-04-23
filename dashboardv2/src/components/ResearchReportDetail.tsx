import { ResearchReportDetail as ResearchReportDetailType } from '../types';

interface ResearchReportDetailProps {
  report?: ResearchReportDetailType | null;
  loading?: boolean;
}

function formatDate(value?: string | null): string {
  if (!value) return 'Unknown date';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

export function ResearchReportDetail({ report, loading = false }: ResearchReportDetailProps) {
  if (loading) {
    return <div className="text-sm text-slate-500">Loading report...</div>;
  }

  if (!report) {
    return <div className="text-sm text-slate-500">Select a report to review its findings, sections, and evidence.</div>;
  }

  return (
    <div className="space-y-4">
      <div>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-xs uppercase tracking-wide text-slate-500">{report.status}</div>
            <div className="mt-1 text-lg font-semibold text-slate-900">{report.title}</div>
          </div>
          <div className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-700">
            {formatDate(report.report_date || report.created_at)}
          </div>
        </div>

        {report.summary_markdown ? (
          <div className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-600">{report.summary_markdown}</div>
        ) : null}
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          ['Confidence', `${Math.round((report.overall_confidence || 0) * 100)}%`],
          ['Findings', `${report.finding_count}`],
          ['Sources', `${report.source_count}`],
          ['Actions', `${report.actions.length}`],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl border border-slate-200 p-3">
            <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
            <div className="mt-1 text-base font-semibold text-slate-900">{value}</div>
          </div>
        ))}
      </div>

      {report.sections.length ? (
        <div>
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">Sections</div>
          <div className="space-y-3">
            {report.sections.map((section) => (
              <div key={section.id} className="rounded-2xl border border-slate-200 p-4">
                <div className="text-sm font-semibold text-slate-900">{section.title}</div>
                {section.markdown ? (
                  <div className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-600">{section.markdown}</div>
                ) : null}
                {section.structured_json && Object.keys(section.structured_json).length ? (
                  <details className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
                    <summary className="cursor-pointer text-xs font-medium text-slate-800">Structured detail</summary>
                    <pre className="mt-2 overflow-auto whitespace-pre-wrap text-[11px] leading-5 text-slate-500">
                      {JSON.stringify(section.structured_json, null, 2)}
                    </pre>
                  </details>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div>
        <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">Evidence</div>
        {report.evidence.length ? (
          <div className="space-y-3">
            {report.evidence.map((item) => (
              <div key={item.id} className="rounded-2xl border border-slate-200 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-slate-900">{item.title || item.claim}</div>
                    <div className="mt-1 text-xs text-slate-500">
                      {item.evidence_type.replaceAll('_', ' ')}
                      {item.company_name ? ` · ${item.company_name}` : ''}
                      {item.role_title ? ` · ${item.role_title}` : ''}
                    </div>
                  </div>
                  <div className="text-right text-[11px] text-slate-500">
                    <div>Confidence {Math.round((item.confidence || 0) * 100)}%</div>
                    <div>Relevance {Math.round((item.relevance_score || 0) * 100)}%</div>
                  </div>
                </div>

                <div className="mt-3 text-sm leading-6 text-slate-700">{item.claim}</div>
                {item.snippet ? <div className="mt-2 text-xs leading-5 text-slate-500">{item.snippet}</div> : null}
                {item.url ? (
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-3 block break-all text-xs text-sky-700 underline"
                  >
                    {item.url}
                  </a>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <div className="text-sm text-slate-500">No evidence was saved on this report.</div>
        )}
      </div>
    </div>
  );
}
