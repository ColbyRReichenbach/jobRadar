import { ResearchReportDiff as ResearchReportDiffType } from '../types';

interface ResearchReportDiffProps {
  diff?: ResearchReportDiffType | null;
  loading?: boolean;
}

function DiffBucket({
  title,
  items,
  tone,
}: {
  title: string;
  items: string[];
  tone: 'emerald' | 'amber' | 'rose' | 'slate';
}) {
  const toneClasses = {
    emerald: 'border-emerald-200 bg-emerald-50 text-emerald-800',
    amber: 'border-amber-200 bg-amber-50 text-amber-800',
    rose: 'border-rose-200 bg-rose-50 text-rose-800',
    slate: 'border-slate-200 bg-slate-50 text-slate-800',
  }[tone];

  return (
    <div className={`rounded-2xl border p-3 ${toneClasses}`}>
      <div className="text-sm font-semibold">{title}</div>
      {items.length ? (
        <ul className="mt-2 space-y-2 text-xs leading-5">
          {items.map((item, index) => (
            <li key={`${title}-${index}`} className="rounded-xl bg-white/70 px-3 py-2">
              {item}
            </li>
          ))}
        </ul>
      ) : (
        <div className="mt-2 text-xs opacity-75">No items in this bucket.</div>
      )}
    </div>
  );
}

export function ResearchReportDiff({ diff, loading = false }: ResearchReportDiffProps) {
  if (loading) {
    return <div className="text-sm text-slate-500">Loading diff...</div>;
  }

  if (!diff) {
    return <div className="text-sm text-slate-500">No report diff is available for this report yet.</div>;
  }

  return (
    <div className="space-y-3">
      {diff.diff_summary ? (
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3 text-sm leading-6 text-slate-700">
          {diff.diff_summary}
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ['New', diff.new_findings.length],
          ['Changed', diff.changed_findings.length],
          ['Dropped', diff.dropped_findings.length],
          ['Unchanged', diff.unchanged_findings.length],
        ].map(([label, count]) => (
          <div key={label} className="rounded-xl border border-slate-200 p-3 text-center">
            <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
            <div className="mt-1 text-lg font-semibold text-slate-900">{count}</div>
          </div>
        ))}
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <DiffBucket title="New findings" items={diff.new_findings} tone="emerald" />
        <DiffBucket title="Changed findings" items={diff.changed_findings} tone="amber" />
        <DiffBucket title="Dropped findings" items={diff.dropped_findings} tone="rose" />
        <DiffBucket title="Unchanged findings" items={diff.unchanged_findings} tone="slate" />
      </div>
    </div>
  );
}
