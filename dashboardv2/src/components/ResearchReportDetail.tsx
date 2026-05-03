import { Download, Printer } from 'lucide-react';
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

function dateStamp(value?: string | null): string {
  const parsed = value ? new Date(value) : new Date();
  if (Number.isNaN(parsed.getTime())) return new Date().toISOString().slice(0, 10);
  return parsed.toISOString().slice(0, 10);
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 72) || 'radar-report';
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function reportToMarkdown(report: ResearchReportDetailType): string {
  const lines = [
    `# ${report.title}`,
    '',
    `Status: ${report.status}`,
    `Report date: ${formatDate(report.report_date || report.created_at)}`,
    `Confidence: ${Math.round((report.overall_confidence || 0) * 100)}%`,
    `Findings: ${report.finding_count}`,
    `Sources: ${report.source_count}`,
    `Actions: ${report.actions.length}`,
    '',
  ];

  if (report.summary_markdown) {
    lines.push('## Summary', '', report.summary_markdown, '');
  }

  if (report.sections.length) {
    lines.push('## Sections', '');
    report.sections
      .slice()
      .sort((left, right) => left.display_order - right.display_order)
      .forEach((section) => {
        lines.push(`### ${section.title}`, '', section.markdown || 'No narrative saved for this section.', '');
      });
  }

  if (report.evidence.length) {
    lines.push('## Evidence', '');
    report.evidence.forEach((item, index) => {
      lines.push(
        `### ${index + 1}. ${item.title || item.claim}`,
        '',
        `Type: ${item.evidence_type.replaceAll('_', ' ')}`,
        `Confidence: ${Math.round((item.confidence || 0) * 100)}%`,
        `Relevance: ${Math.round((item.relevance_score || 0) * 100)}%`,
        item.company_name ? `Company: ${item.company_name}` : '',
        item.role_title ? `Role: ${item.role_title}` : '',
        item.url ? `Source: ${item.url}` : '',
        '',
        item.claim,
        item.snippet ? `\nSnippet: ${item.snippet}` : '',
        ''
      );
    });
  }

  if (report.actions.length) {
    lines.push('## Recommended Actions', '');
    report.actions.forEach((action, index) => {
      lines.push(
        `### ${index + 1}. ${action.title}`,
        '',
        `Type: ${action.action_type}`,
        `Priority: ${action.priority}`,
        `Status: ${action.status}`,
        action.body || '',
        ''
      );
    });
  }

  return lines.filter((line, index, allLines) => line !== '' || allLines[index - 1] !== '').join('\n').trim() + '\n';
}

function downloadMarkdown(report: ResearchReportDetailType): void {
  const blob = new Blob([reportToMarkdown(report)], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `${dateStamp(report.report_date || report.created_at)}-${slugify(report.title)}.md`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function openPrintableReport(report: ResearchReportDetailType): void {
  const printable = window.open('', '_blank');
  if (!printable) return;
  printable.opener = null;

  const markdown = escapeHtml(reportToMarkdown(report));
  printable.document.write(`
    <!doctype html>
    <html>
      <head>
        <title>${escapeHtml(report.title)}</title>
        <style>
          body {
            color: #0f172a;
            font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            line-height: 1.55;
            margin: 48px auto;
            max-width: 820px;
            padding: 0 32px;
          }
          pre {
            font: inherit;
            white-space: pre-wrap;
            word-break: break-word;
          }
          @media print {
            body { margin: 24px auto; }
          }
        </style>
      </head>
      <body>
        <pre>${markdown}</pre>
        <script>
          window.addEventListener('load', () => window.print());
        </script>
      </body>
    </html>
  `);
  printable.document.close();
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
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => openPrintableReport(report)}
              className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-50"
            >
              <Printer className="h-3.5 w-3.5" />
              Print / save PDF
            </button>
            <button
              type="button"
              onClick={() => downloadMarkdown(report)}
              className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-50"
            >
              <Download className="h-3.5 w-3.5" />
              Markdown
            </button>
            <div className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-700">
              {formatDate(report.report_date || report.created_at)}
            </div>
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
