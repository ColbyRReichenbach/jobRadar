import { useCallback, useEffect, useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer,
  LineChart, Line, Legend, Cell,
} from 'recharts';
import {
  ArrowLeft, Upload, Trash2, ChevronDown, ChevronUp, CheckCircle2,
  XCircle, MinusCircle, AlertTriangle, FlaskConical,
} from 'lucide-react';
import type {
  AuditRunSummary, AuditRunDetail, AuditEmailRow, AuditComparisonPoint,
  AuditMetrics,
} from '../lib/api';
import {
  fetchAuditRuns, fetchAuditRun, uploadAuditRun, fetchAuditComparison,
  deleteAuditRun, updateAuditEmailReview,
} from '../lib/api';

// ── Helpers ──────────────────────────────────────────────────────────

function pct(v: number) { return `${(v * 100).toFixed(1)}%`; }

function metricColor(v: number) {
  if (v >= 0.9) return 'text-emerald-600';
  if (v >= 0.7) return 'text-amber-600';
  return 'text-red-600';
}

function metricBg(v: number) {
  if (v >= 0.9) return 'bg-emerald-50 border-emerald-200';
  if (v >= 0.7) return 'bg-amber-50 border-amber-200';
  return 'bg-red-50 border-red-200';
}

const CLS_COLORS: Record<string, string> = {
  interview_request: '#6366f1',
  rejection: '#ef4444',
  offer: '#10b981',
  action_item: '#f59e0b',
  job_update: '#3b82f6',
  conversation: '#8b5cf6',
  not_relevant: '#94a3b8',
};

// ── Main Component ───────────────────────────────────────────────────

export function ClassifierAudit() {
  const [view, setView] = useState<'list' | 'detail' | 'compare'>('list');
  const [runs, setRuns] = useState<AuditRunSummary[]>([]);
  const [selectedRun, setSelectedRun] = useState<AuditRunDetail | null>(null);
  const [comparison, setComparison] = useState<AuditComparisonPoint[]>([]);
  const [compareIds, setCompareIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showUpload, setShowUpload] = useState(false);

  const loadRuns = useCallback(async () => {
    try {
      setLoading(true);
      const data = await fetchAuditRuns();
      setRuns(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load runs');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadRuns(); }, [loadRuns]);

  const openDetail = useCallback(async (runId: string) => {
    try {
      setLoading(true);
      const data = await fetchAuditRun(runId);
      setSelectedRun(data);
      setView('detail');
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load run');
    } finally {
      setLoading(false);
    }
  }, []);

  const openCompare = useCallback(async () => {
    try {
      setLoading(true);
      const ids = compareIds.size > 0 ? Array.from(compareIds) : undefined;
      const data = await fetchAuditComparison(ids);
      setComparison(data);
      setView('compare');
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to compare');
    } finally {
      setLoading(false);
    }
  }, [compareIds]);

  const handleDelete = useCallback(async (runId: string) => {
    if (!confirm('Delete this audit run?')) return;
    try {
      await deleteAuditRun(runId);
      setRuns(r => r.filter(x => x.id !== runId));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to delete');
    }
  }, []);

  const toggleCompare = useCallback((runId: string) => {
    setCompareIds(prev => {
      const next = new Set(prev);
      if (next.has(runId)) next.delete(runId);
      else next.add(runId);
      return next;
    });
  }, []);

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" />
          {error}
          <button onClick={() => setError('')} className="ml-auto text-red-400 hover:text-red-600">×</button>
        </div>
      )}

      <AnimatePresence mode="wait">
        {view === 'list' && (
          <motion.div key="list" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <RunList
              runs={runs}
              loading={loading}
              compareIds={compareIds}
              onOpenDetail={openDetail}
              onDelete={handleDelete}
              onToggleCompare={toggleCompare}
              onCompare={openCompare}
              onUpload={() => setShowUpload(true)}
            />
          </motion.div>
        )}
        {view === 'detail' && selectedRun && (
          <motion.div key="detail" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <RunDetail
              run={selectedRun}
              onBack={() => { setView('list'); setSelectedRun(null); }}
              onEmailUpdate={async (idx, review) => {
                await updateAuditEmailReview(selectedRun.meta.id, idx, review);
                const refreshed = await fetchAuditRun(selectedRun.meta.id);
                setSelectedRun(refreshed);
                loadRuns();
              }}
            />
          </motion.div>
        )}
        {view === 'compare' && (
          <motion.div key="compare" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <CompareView
              data={comparison}
              onBack={() => setView('list')}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {showUpload && (
        <UploadModal
          onClose={() => setShowUpload(false)}
          onUploaded={() => { setShowUpload(false); loadRuns(); }}
        />
      )}
    </div>
  );
}

// ── Run List ─────────────────────────────────────────────────────────

function RunList({
  runs, loading, compareIds, onOpenDetail, onDelete, onToggleCompare, onCompare, onUpload,
}: {
  runs: AuditRunSummary[];
  loading: boolean;
  compareIds: Set<string>;
  onOpenDetail: (id: string) => void;
  onDelete: (id: string) => void;
  onToggleCompare: (id: string) => void;
  onCompare: () => void;
  onUpload: () => void;
}) {
  return (
    <>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <FlaskConical className="w-6 h-6 text-indigo-600" />
            Classifier Audit
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Track classifier accuracy across runs. Recall-first — never miss a real job email.
          </p>
        </div>
        <div className="flex gap-2">
          {compareIds.size >= 2 && (
            <button onClick={onCompare} className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition">
              Compare ({compareIds.size})
            </button>
          )}
          <button onClick={onUpload} className="px-4 py-2 bg-slate-900 text-white rounded-lg text-sm font-medium hover:bg-slate-800 transition flex items-center gap-2">
            <Upload className="w-4 h-4" /> Upload Run
          </button>
        </div>
      </div>

      {loading && runs.length === 0 && (
        <p className="text-slate-500 text-center py-12">Loading runs…</p>
      )}

      {!loading && runs.length === 0 && (
        <div className="text-center py-16 text-slate-400">
          <FlaskConical className="w-12 h-12 mx-auto mb-4 opacity-40" />
          <p className="text-lg">No audit runs yet</p>
          <p className="text-sm mt-1">Run the classifier on your emails, review the CSV, then upload it here.</p>
        </div>
      )}

      <div className="grid gap-4">
        {runs.map((run) => {
          const m = run.metrics;
          const dr = m?.decision?.recall ?? 0;
          const dp = m?.decision?.precision ?? 0;
          const cr = m?.classification?.macro_recall ?? 0;
          const coverage = run.total_emails > 0 ? run.reviewed_emails / run.total_emails : 0;

          return (
            <motion.div
              key={run.id}
              layout
              className={`border rounded-xl p-5 bg-white shadow-sm hover:shadow-md transition ${compareIds.has(run.id) ? 'ring-2 ring-indigo-400' : ''}`}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <h3 className="font-semibold text-slate-900">{run.name}</h3>
                    <span className="px-2 py-0.5 rounded-full text-xs bg-slate-100 text-slate-600">
                      {run.classifier_engine} · {run.model}
                    </span>
                    <span className="px-2 py-0.5 rounded-full text-xs bg-indigo-50 text-indigo-600">
                      {run.prompt_version}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400">
                    {new Date(run.created_at).toLocaleDateString()} · {run.total_emails} emails · {run.reviewed_emails} reviewed
                    {run.notes && <> · {run.notes}</>}
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <label className="flex items-center gap-1 text-xs text-slate-500 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={compareIds.has(run.id)}
                      onChange={() => onToggleCompare(run.id)}
                      className="rounded border-slate-300"
                    />
                    Compare
                  </label>
                  <button onClick={() => onOpenDetail(run.id)} className="px-3 py-1.5 text-sm bg-slate-100 rounded-lg hover:bg-slate-200 transition">
                    Details
                  </button>
                  <button onClick={() => onDelete(run.id)} className="p-1.5 text-slate-400 hover:text-red-500 transition">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {/* Metrics row */}
              <div className="grid grid-cols-4 gap-3 mt-4">
                <MetricCard label="Decision Recall" value={dr} large />
                <MetricCard label="Decision Precision" value={dp} />
                <MetricCard label="Classification Recall" value={cr} />
                <MetricCard label="Review Coverage" value={coverage} />
              </div>
            </motion.div>
          );
        })}
      </div>
    </>
  );
}

function MetricCard({ label, value, large }: { label: string; value: number; large?: boolean }) {
  return (
    <div className={`border rounded-lg p-3 ${metricBg(value)}`}>
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className={`font-bold ${large ? 'text-2xl' : 'text-lg'} ${metricColor(value)}`}>
        {pct(value)}
      </p>
    </div>
  );
}

// ── Run Detail ───────────────────────────────────────────────────────

function RunDetail({
  run, onBack, onEmailUpdate,
}: {
  run: AuditRunDetail;
  onBack: () => void;
  onEmailUpdate: (idx: number, review: Record<string, string>) => Promise<void>;
}) {
  const { meta, emails } = run;
  const m = meta.metrics;
  const [filter, setFilter] = useState<'all' | 'reviewed' | 'unreviewed' | 'errors'>('all');
  const [sortCol, setSortCol] = useState('id');
  const [sortAsc, setSortAsc] = useState(true);
  const [editIdx, setEditIdx] = useState<number | null>(null);

  const dr = m?.decision?.recall ?? 0;
  const dp = m?.decision?.precision ?? 0;
  const ca = m?.classification?.accuracy ?? 0;
  const coverage = meta.total_emails > 0 ? meta.reviewed_emails / meta.total_emails : 0;

  // Filter + sort emails
  const filteredEmails = useMemo(() => {
    let list = emails.map((e, i) => ({ ...e, _idx: i }));

    if (filter === 'reviewed') list = list.filter(e => (e.review_correct || '').trim());
    if (filter === 'unreviewed') list = list.filter(e => !(e.review_correct || '').trim());
    if (filter === 'errors') list = list.filter(e => (e.review_correct || '').trim().toLowerCase() === 'no');

    list.sort((a, b) => {
      const av = a[sortCol] ?? '';
      const bv = b[sortCol] ?? '';
      const cmp = typeof av === 'string' ? av.localeCompare(bv) : Number(av) - Number(bv);
      return sortAsc ? cmp : -cmp;
    });

    return list;
  }, [emails, filter, sortCol, sortAsc]);

  const toggleSort = (col: string) => {
    if (sortCol === col) setSortAsc(!sortAsc);
    else { setSortCol(col); setSortAsc(true); }
  };

  // Classification distribution chart data
  const clsData = useMemo(() => {
    const counts: Record<string, number> = {};
    emails.forEach(e => {
      const c = e.predicted_classification || 'unknown';
      counts[c] = (counts[c] || 0) + 1;
    });
    return Object.entries(counts)
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count);
  }, [emails]);

  // Per-class recall table
  const perClass = m?.classification?.per_class ?? {};

  // Confusion matrix
  const cm = m?.confusion_matrix;

  return (
    <>
      <button onClick={onBack} className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900 mb-4 transition">
        <ArrowLeft className="w-4 h-4" /> Back to runs
      </button>

      <div className="flex items-center gap-3 mb-2">
        <h2 className="text-xl font-bold text-slate-900">{meta.name}</h2>
        <span className="px-2 py-0.5 rounded-full text-xs bg-slate-100 text-slate-600">
          {meta.classifier_engine} · {meta.model} · {meta.prompt_version}
        </span>
      </div>
      <p className="text-sm text-slate-400 mb-6">
        {new Date(meta.created_at).toLocaleDateString()} · {meta.total_emails} emails · {meta.reviewed_emails} reviewed
        {meta.notes && <> · {meta.notes}</>}
      </p>

      {/* Top metrics */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <MetricCard label="Decision Recall" value={dr} large />
        <MetricCard label="Decision Precision" value={dp} />
        <MetricCard label="Classification Accuracy" value={ca} />
        <MetricCard label="Review Coverage" value={coverage} />
      </div>

      {coverage < 0.5 && (
        <div className="mb-6 p-3 bg-amber-50 border border-amber-200 rounded-lg text-amber-700 text-sm flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" />
          Low review coverage ({pct(coverage)}). Review more emails for reliable metrics.
        </div>
      )}

      <div className="grid lg:grid-cols-3 gap-6 mb-8">
        {/* Classification distribution */}
        <div className="lg:col-span-2 bg-white border rounded-xl p-5">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Classification Distribution</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={clsData} layout="vertical" margin={{ left: 100 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" />
              <YAxis type="category" dataKey="name" width={100} tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                {clsData.map((entry) => (
                  <Cell key={entry.name} fill={CLS_COLORS[entry.name] || '#94a3b8'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Decision confusion matrix */}
        {cm && cm.matrix.length > 0 && (
          <div className="bg-white border rounded-xl p-5">
            <h3 className="text-sm font-semibold text-slate-700 mb-3">Decision Confusion Matrix</h3>
            <div className="text-xs text-slate-400 mb-2">Rows = Actual, Cols = Predicted</div>
            <table className="w-full text-center text-sm">
              <thead>
                <tr>
                  <th className="p-2"></th>
                  {cm.labels.map(l => <th key={l} className="p-2 font-medium text-slate-600">{l}</th>)}
                </tr>
              </thead>
              <tbody>
                {cm.labels.map((label, ri) => (
                  <tr key={label}>
                    <td className="p-2 font-medium text-slate-600 text-right">{label}</td>
                    {cm.matrix[ri].map((val, ci) => (
                      <td
                        key={ci}
                        className={`p-2 font-bold rounded ${ri === ci ? 'bg-emerald-100 text-emerald-700' : val > 0 ? 'bg-red-50 text-red-600' : 'text-slate-300'}`}
                      >
                        {val}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Per-class recall table */}
      {Object.keys(perClass).length > 0 && (
        <div className="bg-white border rounded-xl p-5 mb-8">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Per-Class Metrics</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b">
                <th className="pb-2">Category</th>
                <th className="pb-2 text-right">Precision</th>
                <th className="pb-2 text-right">Recall</th>
                <th className="pb-2 text-right">F1</th>
                <th className="pb-2 text-right">Support</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(perClass).map(([cls, m]) => (
                <tr key={cls} className={`border-b ${m.recall < 0.9 && m.support > 0 ? 'bg-amber-50' : ''}`}>
                  <td className="py-2 flex items-center gap-2">
                    <span className="w-3 h-3 rounded-full inline-block" style={{ background: CLS_COLORS[cls] || '#94a3b8' }} />
                    {cls}
                    {m.recall < 0.9 && m.support > 0 && <AlertTriangle className="w-3 h-3 text-amber-500" />}
                  </td>
                  <td className="py-2 text-right">{pct(m.precision)}</td>
                  <td className={`py-2 text-right font-medium ${metricColor(m.recall)}`}>{pct(m.recall)}</td>
                  <td className="py-2 text-right">{pct(m.f1)}</td>
                  <td className="py-2 text-right text-slate-400">{m.support}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Email review table */}
      <div className="bg-white border rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-slate-700">Email Reviews ({filteredEmails.length})</h3>
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value as typeof filter)}
            className="text-sm border rounded-lg px-3 py-1.5 text-slate-600"
          >
            <option value="all">All</option>
            <option value="reviewed">Reviewed</option>
            <option value="unreviewed">Unreviewed</option>
            <option value="errors">Errors Only</option>
          </select>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-slate-500 border-b">
                {['id', 'subject', 'sender_email', 'predicted_decision', 'predicted_classification', 'predicted_confidence', 'review_correct'].map(col => (
                  <th
                    key={col}
                    className="pb-2 pr-3 cursor-pointer hover:text-slate-900 whitespace-nowrap"
                    onClick={() => toggleSort(col)}
                  >
                    <span className="flex items-center gap-1">
                      {col.replace('predicted_', '').replace('review_', 'review ')}
                      {sortCol === col && (sortAsc ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />)}
                    </span>
                  </th>
                ))}
                <th className="pb-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredEmails.slice(0, 200).map((email) => {
                const rc = (email.review_correct || '').trim().toLowerCase();
                const rowBg = rc === 'yes' ? 'bg-emerald-50/50' : rc === 'no' ? 'bg-red-50/50' : '';

                return (
                  <tr key={email._idx} className={`border-b hover:bg-slate-50 ${rowBg}`}>
                    <td className="py-2 pr-3">{email.id}</td>
                    <td className="py-2 pr-3 max-w-[200px] truncate" title={email.subject}>{email.subject}</td>
                    <td className="py-2 pr-3 max-w-[150px] truncate" title={email.sender_email}>{email.sender_email}</td>
                    <td className="py-2 pr-3">
                      <span className={`px-1.5 py-0.5 rounded text-xs ${email.predicted_decision === 'inbox' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600'}`}>
                        {email.predicted_decision}
                      </span>
                    </td>
                    <td className="py-2 pr-3">
                      <span className="flex items-center gap-1">
                        <span className="w-2 h-2 rounded-full inline-block" style={{ background: CLS_COLORS[email.predicted_classification] || '#94a3b8' }} />
                        {email.predicted_classification}
                      </span>
                    </td>
                    <td className="py-2 pr-3">{Number(email.predicted_confidence || 0).toFixed(2)}</td>
                    <td className="py-2 pr-3">
                      {rc === 'yes' && <CheckCircle2 className="w-4 h-4 text-emerald-500" />}
                      {rc === 'no' && <XCircle className="w-4 h-4 text-red-500" />}
                      {!rc && <MinusCircle className="w-4 h-4 text-slate-300" />}
                    </td>
                    <td className="py-2">
                      <button
                        onClick={() => setEditIdx(editIdx === email._idx ? null : email._idx)}
                        className="text-indigo-600 hover:text-indigo-800 text-xs"
                      >
                        {editIdx === email._idx ? 'Close' : 'Review'}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Inline review editor */}
        <AnimatePresence>
          {editIdx !== null && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              <InlineReviewEditor
                email={emails[editIdx]}
                onSave={async (review) => {
                  await onEmailUpdate(editIdx, review);
                  setEditIdx(null);
                }}
                onCancel={() => setEditIdx(null)}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </>
  );
}

// ── Inline Review Editor ─────────────────────────────────────────────

function InlineReviewEditor({
  email, onSave, onCancel,
}: {
  email: AuditEmailRow;
  onSave: (review: Record<string, string>) => Promise<void>;
  onCancel: () => void;
}) {
  const [correct, setCorrect] = useState(email.review_correct || '');
  const [decision, setDecision] = useState(email.review_expected_decision || '');
  const [cls, setCls] = useState(email.review_expected_classification || '');
  const [net, setNet] = useState(email.review_expected_network_contact || '');
  const [status, setStatus] = useState(email.review_expected_status_change || '');
  const [reason, setReason] = useState(email.review_reason || '');
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    await onSave({
      review_correct: correct,
      review_expected_decision: decision,
      review_expected_classification: cls,
      review_expected_network_contact: net,
      review_expected_status_change: status,
      review_reason: reason,
    });
    setSaving(false);
  };

  return (
    <div className="mt-4 p-4 bg-slate-50 border rounded-lg">
      <div className="flex items-center gap-2 mb-3">
        <h4 className="text-sm font-semibold text-slate-700">Review: {email.subject}</h4>
        <span className="text-xs text-slate-400">from {email.sender_email}</span>
      </div>

      <div className="text-xs text-slate-500 mb-3 p-2 bg-white rounded border max-h-20 overflow-y-auto">
        {email.body_snippet || email.predicted_summary || 'No body text'}
      </div>

      <div className="grid grid-cols-3 gap-3 text-sm">
        <div>
          <label className="block text-xs text-slate-500 mb-1">Correct?</label>
          <select value={correct} onChange={e => setCorrect(e.target.value)} className="w-full border rounded px-2 py-1 text-sm">
            <option value="">—</option>
            <option value="yes">Yes</option>
            <option value="no">No</option>
          </select>
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Expected Decision</label>
          <select value={decision} onChange={e => setDecision(e.target.value)} className="w-full border rounded px-2 py-1 text-sm">
            <option value="">—</option>
            <option value="inbox">inbox</option>
            <option value="filter">filter</option>
          </select>
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Expected Classification</label>
          <select value={cls} onChange={e => setCls(e.target.value)} className="w-full border rounded px-2 py-1 text-sm">
            <option value="">—</option>
            {['interview_request', 'rejection', 'offer', 'action_item', 'job_update', 'conversation', 'not_relevant'].map(c => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Expected Network Contact</label>
          <select value={net} onChange={e => setNet(e.target.value)} className="w-full border rounded px-2 py-1 text-sm">
            <option value="">—</option>
            <option value="yes">yes</option>
            <option value="no">no</option>
          </select>
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Expected Status Change</label>
          <select value={status} onChange={e => setStatus(e.target.value)} className="w-full border rounded px-2 py-1 text-sm">
            <option value="">—</option>
            {['applied', 'interviewing', 'offer', 'rejected', ''].map(s => (
              <option key={s} value={s}>{s || '(none)'}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Reason</label>
          <input value={reason} onChange={e => setReason(e.target.value)} className="w-full border rounded px-2 py-1 text-sm" placeholder="Why wrong?" />
        </div>
      </div>

      <div className="flex gap-2 mt-3">
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-4 py-1.5 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700 disabled:opacity-50 transition"
        >
          {saving ? 'Saving…' : 'Save Review'}
        </button>
        <button onClick={onCancel} className="px-4 py-1.5 text-sm text-slate-500 hover:text-slate-700 transition">
          Cancel
        </button>
      </div>
    </div>
  );
}

// ── Compare View ─────────────────────────────────────────────────────

function CompareView({
  data, onBack,
}: {
  data: AuditComparisonPoint[];
  onBack: () => void;
}) {
  const METRIC_LINES = [
    { key: 'decision_recall', name: 'Decision Recall', color: '#10b981', strokeWidth: 3 },
    { key: 'decision_precision', name: 'Decision Precision', color: '#6366f1', strokeWidth: 1.5 },
    { key: 'decision_f1', name: 'Decision F1', color: '#8b5cf6', strokeWidth: 1.5 },
    { key: 'classification_macro_recall', name: 'Macro Recall', color: '#f59e0b', strokeWidth: 2 },
  ];

  return (
    <>
      <button onClick={onBack} className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900 mb-4 transition">
        <ArrowLeft className="w-4 h-4" /> Back to runs
      </button>

      <h2 className="text-xl font-bold text-slate-900 mb-6">Run Comparison</h2>

      {data.length === 0 ? (
        <p className="text-slate-500 text-center py-12">No runs to compare.</p>
      ) : (
        <>
          {/* Line chart */}
          <div className="bg-white border rounded-xl p-5 mb-8">
            <h3 className="text-sm font-semibold text-slate-700 mb-3">Metrics Over Time</h3>
            <ResponsiveContainer width="100%" height={350}>
              <LineChart data={data} margin={{ left: 10, right: 30, top: 10 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis domain={[0, 1]} tick={{ fontSize: 11 }} tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`} />
                <Tooltip formatter={(v: number) => `${(v * 100).toFixed(1)}%`} />
                <Legend />
                {METRIC_LINES.map(ml => (
                  <Line
                    key={ml.key}
                    type="monotone"
                    dataKey={ml.key}
                    name={ml.name}
                    stroke={ml.color}
                    strokeWidth={ml.strokeWidth}
                    dot={{ r: 4 }}
                    activeDot={{ r: 6 }}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Delta table */}
          <div className="bg-white border rounded-xl p-5">
            <h3 className="text-sm font-semibold text-slate-700 mb-3">Run Details</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-slate-500 border-b">
                    <th className="pb-2 pr-4">Run</th>
                    <th className="pb-2 pr-4">Engine</th>
                    <th className="pb-2 pr-4">Prompt</th>
                    <th className="pb-2 pr-4 text-right">Emails</th>
                    <th className="pb-2 pr-4 text-right">Reviewed</th>
                    <th className="pb-2 pr-4 text-right">Dec. Recall</th>
                    <th className="pb-2 pr-4 text-right">Dec. Precision</th>
                    <th className="pb-2 pr-4 text-right">Cls. Recall</th>
                    <th className="pb-2 text-right">Net. Recall</th>
                  </tr>
                </thead>
                <tbody>
                  {data.map((point, i) => {
                    const prev = i > 0 ? data[i - 1] : null;
                    return (
                      <tr key={point.id} className="border-b">
                        <td className="py-2 pr-4 font-medium">{point.name}</td>
                        <td className="py-2 pr-4 text-slate-500">{point.classifier_engine} · {point.model}</td>
                        <td className="py-2 pr-4 text-slate-500">{point.prompt_version}</td>
                        <td className="py-2 pr-4 text-right">{point.total_emails}</td>
                        <td className="py-2 pr-4 text-right">{point.reviewed_emails}</td>
                        <td className="py-2 pr-4 text-right">
                          <DeltaCell value={point.decision_recall} prev={prev?.decision_recall} />
                        </td>
                        <td className="py-2 pr-4 text-right">
                          <DeltaCell value={point.decision_precision} prev={prev?.decision_precision} />
                        </td>
                        <td className="py-2 pr-4 text-right">
                          <DeltaCell value={point.classification_macro_recall} prev={prev?.classification_macro_recall} />
                        </td>
                        <td className="py-2 text-right">
                          <DeltaCell value={point.network_recall} prev={prev?.network_recall} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </>
  );
}

function DeltaCell({ value, prev }: { value: number; prev?: number }) {
  const delta = prev != null ? value - prev : 0;
  return (
    <span className="flex items-center justify-end gap-1">
      <span className={`font-medium ${metricColor(value)}`}>{pct(value)}</span>
      {prev != null && delta !== 0 && (
        <span className={`text-xs ${delta > 0 ? 'text-emerald-500' : 'text-red-500'}`}>
          {delta > 0 ? '▲' : '▼'}{Math.abs(delta * 100).toFixed(1)}
        </span>
      )}
    </span>
  );
}

// ── Upload Modal ─────────────────────────────────────────────────────

function UploadModal({
  onClose, onUploaded,
}: {
  onClose: () => void;
  onUploaded: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState('');
  const [engine, setEngine] = useState('openai');
  const [model, setModel] = useState('gpt-4o-mini');
  const [promptVer, setPromptVer] = useState('v1');
  const [notes, setNotes] = useState('');
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async () => {
    if (!file || !name) { setError('File and name are required'); return; }
    setUploading(true);
    setError('');
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('name', name);
      fd.append('classifier_engine', engine);
      fd.append('model', model);
      fd.append('prompt_version', promptVer);
      fd.append('notes', notes);
      await uploadAuditRun(fd);
      onUploaded();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        className="bg-white rounded-xl shadow-xl p-6 w-full max-w-md"
        onClick={e => e.stopPropagation()}
      >
        <h3 className="text-lg font-bold text-slate-900 mb-4">Upload Audit Run</h3>

        {error && <p className="text-sm text-red-600 mb-3">{error}</p>}

        <div className="space-y-3">
          <div>
            <label className="block text-sm text-slate-600 mb-1">CSV File *</label>
            <input
              type="file"
              accept=".csv"
              onChange={e => setFile(e.target.files?.[0] || null)}
              className="w-full text-sm border rounded-lg p-2"
            />
          </div>
          <div>
            <label className="block text-sm text-slate-600 mb-1">Run Name *</label>
            <input value={name} onChange={e => setName(e.target.value)} className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="e.g. GPT-4o-mini prompt v2" />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-sm text-slate-600 mb-1">Engine</label>
              <select value={engine} onChange={e => setEngine(e.target.value)} className="w-full border rounded-lg px-2 py-2 text-sm">
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic</option>
                <option value="fallback">Fallback</option>
              </select>
            </div>
            <div>
              <label className="block text-sm text-slate-600 mb-1">Model</label>
              <input value={model} onChange={e => setModel(e.target.value)} className="w-full border rounded-lg px-2 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-sm text-slate-600 mb-1">Prompt Ver</label>
              <input value={promptVer} onChange={e => setPromptVer(e.target.value)} className="w-full border rounded-lg px-2 py-2 text-sm" />
            </div>
          </div>
          <div>
            <label className="block text-sm text-slate-600 mb-1">Notes</label>
            <textarea value={notes} onChange={e => setNotes(e.target.value)} className="w-full border rounded-lg px-3 py-2 text-sm" rows={2} placeholder="What changed in this run?" />
          </div>
        </div>

        <div className="flex gap-2 mt-5">
          <button
            onClick={handleSubmit}
            disabled={uploading}
            className="flex-1 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition"
          >
            {uploading ? 'Uploading…' : 'Upload & Compute Metrics'}
          </button>
          <button onClick={onClose} className="px-4 py-2 text-sm text-slate-500 hover:text-slate-700 transition">
            Cancel
          </button>
        </div>
      </motion.div>
    </div>
  );
}
