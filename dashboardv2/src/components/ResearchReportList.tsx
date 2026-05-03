import { ResearchReport } from '../types';

interface ResearchReportListProps {
  reports: ResearchReport[];
  selectedReportId?: string | null;
  loading?: boolean;
  onSelectReport: (report: ResearchReport) => void;
}

function formatDate(value?: string | null): string {
  if (!value) return 'Unknown date';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

export function ResearchReportList({
  reports,
  selectedReportId,
  loading = false,
  onSelectReport,
}: ResearchReportListProps) {
  if (loading && !reports.length) {
    return <div className="text-sm text-slate-500">Loading reports...</div>;
  }

  if (!reports.length) {
    return <div className="text-sm text-slate-500">No research reports yet. Run a research or hybrid tracker to save the first report.</div>;
  }

  return (
    <div className="space-y-3">
      {reports.map((report) => {
        const selected = report.id === selectedReportId;
        return (
          <button
            key={report.id}
            type="button"
            onClick={() => onSelectReport(report)}
            className={`w-full rounded-2xl border p-4 text-left ${
              selected ? 'border-slate-400 bg-slate-50' : 'border-slate-200 bg-white'
            }`}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-slate-900">{report.title}</div>
                <div className="mt-1 text-xs text-slate-500">
                  {formatDate(report.report_date || report.created_at)} · {report.status}
                </div>
              </div>
              <div className="rounded-full bg-slate-100 px-2 py-1 text-[11px] text-slate-700">
                {Math.round((report.overall_confidence || 0) * 100)}%
              </div>
            </div>

            {report.summary_markdown ? (
              <p className="mt-3 line-clamp-4 whitespace-pre-wrap text-sm leading-6 text-slate-600">
                {report.summary_markdown}
              </p>
            ) : null}

            <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] text-slate-500 sm:grid-cols-4">
              <div className="rounded-xl border border-slate-200 px-2 py-2">
                <div className="uppercase tracking-wide">Findings</div>
                <div className="mt-1 text-sm font-semibold text-slate-900">{report.finding_count}</div>
              </div>
              <div className="rounded-xl border border-slate-200 px-2 py-2">
                <div className="uppercase tracking-wide">Sources</div>
                <div className="mt-1 text-sm font-semibold text-slate-900">{report.source_count}</div>
              </div>
              <div className="rounded-xl border border-slate-200 px-2 py-2">
                <div className="uppercase tracking-wide">New</div>
                <div className="mt-1 text-sm font-semibold text-slate-900">{report.new_findings_count}</div>
              </div>
              <div className="rounded-xl border border-slate-200 px-2 py-2">
                <div className="uppercase tracking-wide">Changed</div>
                <div className="mt-1 text-sm font-semibold text-slate-900">{report.changed_findings_count}</div>
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}
