import { useCallback, useEffect, useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer, Cell,
  LineChart, Line, Legend,
} from 'recharts';
import {
  AlertTriangle, CheckCircle2, XCircle, Bug, Globe, Crosshair,
  ChevronDown, ChevronUp, ExternalLink, Eye, GitCommitHorizontal, TrendingUp, Plus,
} from 'lucide-react';
import type { ExtractionReportItem, ExtractionReportStats, ChangelogEntry, VersionStatsResponse, FeedbackStats } from '../lib/api';
import {
  fetchExtractionReports, fetchExtractionReportStats, resolveExtractionReport,
  fetchVersionStats, fetchChangelog, createChangelogEntry, fetchFeedbackStats,
} from '../lib/api';

const TYPE_LABELS: Record<string, string> = {
  missing_data: 'Missing Data',
  wrong_data: 'Wrong Data',
  undetected_site: 'Undetected Site',
  false_positive: 'False Positive',
};

const TYPE_COLORS: Record<string, string> = {
  missing_data: '#f59e0b',
  wrong_data: '#ef4444',
  undetected_site: '#3b82f6',
  false_positive: '#8b5cf6',
};

const TYPE_ICONS: Record<string, typeof Bug> = {
  missing_data: AlertTriangle,
  wrong_data: XCircle,
  undetected_site: Globe,
  false_positive: Crosshair,
};

const PLATFORM_COLORS: Record<string, string> = {
  linkedin: '#0077B5',
  greenhouse: '#3AB549',
  lever: '#555',
  workday: '#005CB9',
  indeed: '#2164F3',
  glassdoor: '#0CAA41',
  ashby: '#6366f1',
  ziprecruiter: '#00A53E',
  generic: '#94a3b8',
};

// ── Version Timeline Sub-component ──────────────────────────────────

function VersionTimeline() {
  const [data, setData] = useState<VersionStatsResponse | null>(null);
  const [changelog, setChangelog] = useState<ChangelogEntry[]>([]);
  const [feedback, setFeedback] = useState<FeedbackStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showAddForm, setShowAddForm] = useState(false);
  const [form, setForm] = useState({ version: '', description: '', change_type: 'extraction', platforms: '', fields: '' });

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [vs, cl, fb] = await Promise.all([
        fetchVersionStats(),
        fetchChangelog(),
        fetchFeedbackStats().catch(() => null),
      ]);
      setData(vs);
      setChangelog(cl);
      setFeedback(fb);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleAddEntry = useCallback(async () => {
    if (!form.version || !form.description) return;
    try {
      await createChangelogEntry({
        version: form.version,
        description: form.description,
        change_type: form.change_type,
        platforms_affected: form.platforms ? form.platforms.split(',').map(s => s.trim()) : undefined,
        fields_affected: form.fields ? form.fields.split(',').map(s => s.trim()) : undefined,
      });
      setForm({ version: '', description: '', change_type: 'extraction', platforms: '', fields: '' });
      setShowAddForm(false);
      loadData();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to create entry');
    }
  }, [form, loadData]);

  // Build chart data from version stats
  const chartData = useMemo(() => {
    if (!data) return [];
    return data.versions.map(v => ({
      version: v.version.replace('ext-', ''),
      accuracy: v.accuracy_rate != null ? +(v.accuracy_rate * 100).toFixed(1) : null,
      reports: v.total_reports,
      wrong: v.wrong_data_reports,
      false_pos: v.false_positive_reports,
    }));
  }, [data]);

  // Build per-field accuracy table across versions
  const allFields = useMemo(() => {
    if (!data) return [];
    const fields = new Set<string>();
    data.versions.forEach(v => Object.keys(v.field_accuracy).forEach(f => fields.add(f)));
    return Array.from(fields).sort();
  }, [data]);

  if (loading) return <p className="text-slate-500 text-center py-12">Loading version data...</p>;

  return (
    <div>
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" />
          {error}
          <button onClick={() => setError('')} className="ml-auto text-red-400 hover:text-red-600">&times;</button>
        </div>
      )}

      {/* Classifier false-positive signal */}
      {feedback && feedback.not_job_related > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-6">
          <h3 className="text-sm font-semibold text-red-700 mb-2 flex items-center gap-2">
            <XCircle className="w-4 h-4" />
            Classifier False Positives — {feedback.not_job_related} emails marked "Not Job Related" by user
          </h3>
          <div className="flex flex-col gap-1 text-xs text-red-600 sm:flex-row sm:flex-wrap sm:gap-x-4">
            <span>Top domains: {feedback.top_blocked_domains.slice(0, 5).map(d => d.domain).join(', ') || 'none'}</span>
            {feedback.daily_trend.length > 0 && (
              <span>Latest: {feedback.daily_trend[feedback.daily_trend.length - 1].date}</span>
            )}
          </div>
          <p className="text-[10px] text-red-500 mt-1">
            These are emails the classifier let through that the user manually flagged. See Classifier Audit for full breakdown.
          </p>
        </div>
      )}

      {/* Accuracy over versions chart */}
      {chartData.length > 0 && (
        <div className="min-w-0 overflow-hidden bg-white border rounded-xl p-4 mb-6 sm:p-5">
          <h3 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-indigo-500" />
            Accuracy Trend Across Versions
          </h3>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={chartData} margin={{ left: 0, right: 8 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="version" tick={{ fontSize: 10 }} angle={-30} textAnchor="end" height={60} />
              <YAxis domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(val) => `${val}%`} />
              <Legend />
              <Line type="monotone" dataKey="accuracy" name="Accuracy %" stroke="#10b981" strokeWidth={3} dot={{ r: 5 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Report volume per version */}
      {chartData.length > 0 && (
        <div className="min-w-0 overflow-hidden bg-white border rounded-xl p-4 mb-6 sm:p-5">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Report Volume by Version</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={chartData} margin={{ left: 0, right: 8 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="version" tick={{ fontSize: 10 }} angle={-30} textAnchor="end" height={60} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Bar dataKey="wrong" name="Wrong Data" fill="#ef4444" stackId="a" radius={[0, 0, 0, 0]} />
              <Bar dataKey="false_pos" name="False Positive" fill="#8b5cf6" stackId="a" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Per-field accuracy table */}
      {allFields.length > 0 && data && (
        <div className="bg-white border rounded-xl p-5 mb-6 overflow-x-auto">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Per-Field Accuracy by Version</h3>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b">
                <th className="text-left py-2 pr-4 text-slate-500 font-medium">Field</th>
                {data.versions.map(v => (
                  <th key={v.version} className="text-center py-2 px-2 text-slate-500 font-medium">
                    {v.version.replace('ext-', '')}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {allFields.map(field => (
                <tr key={field} className="border-b border-slate-50">
                  <td className="py-2 pr-4 font-medium text-slate-700">{field}</td>
                  {data.versions.map(v => {
                    const acc = v.field_accuracy[field];
                    const pct = acc != null ? (acc * 100).toFixed(0) : '—';
                    const color = acc == null ? 'text-slate-300'
                      : acc >= 0.9 ? 'text-emerald-600'
                      : acc >= 0.7 ? 'text-amber-600'
                      : 'text-red-600';
                    return (
                      <td key={v.version} className={`text-center py-2 px-2 font-medium ${color}`}>
                        {acc != null ? `${pct}%` : pct}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {chartData.length === 0 && (
        <div className="text-center py-16 text-slate-400">
          <GitCommitHorizontal className="w-12 h-12 mx-auto mb-4 opacity-40" />
          <p className="text-lg">No version data yet</p>
          <p className="text-sm mt-1">Version stats appear when extraction reports include an extractor_version.</p>
        </div>
      )}

      {/* Changelog entries */}
      <div className="bg-white border rounded-xl p-4 sm:p-5">
        <div className="flex flex-col gap-3 mb-4 sm:flex-row sm:items-center sm:justify-between">
          <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
            <GitCommitHorizontal className="w-4 h-4 text-slate-500" />
            Changelog
          </h3>
          <button
            onClick={() => setShowAddForm(!showAddForm)}
            className="text-xs text-indigo-600 hover:text-indigo-800 flex items-center gap-1"
          >
            <Plus className="w-3 h-3" /> Add Entry
          </button>
        </div>

        {/* Add form */}
        {showAddForm && (
          <div className="mb-4 p-4 bg-slate-50 rounded-lg border border-slate-200 space-y-3">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <input
                placeholder="Version (e.g. ext-2026.03.18a)"
                value={form.version}
                onChange={e => setForm(f => ({ ...f, version: e.target.value }))}
                className="text-sm border rounded-lg px-3 py-1.5"
              />
              <select
                value={form.change_type}
                onChange={e => setForm(f => ({ ...f, change_type: e.target.value }))}
                className="text-sm border rounded-lg px-3 py-1.5"
              >
                <option value="extraction">Extraction</option>
                <option value="classifier">Classifier</option>
                <option value="both">Both</option>
              </select>
            </div>
            <input
              placeholder="Description of changes"
              value={form.description}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              className="w-full text-sm border rounded-lg px-3 py-1.5"
            />
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <input
                placeholder="Platforms affected (comma-separated)"
                value={form.platforms}
                onChange={e => setForm(f => ({ ...f, platforms: e.target.value }))}
                className="text-sm border rounded-lg px-3 py-1.5"
              />
              <input
                placeholder="Fields affected (comma-separated)"
                value={form.fields}
                onChange={e => setForm(f => ({ ...f, fields: e.target.value }))}
                className="text-sm border rounded-lg px-3 py-1.5"
              />
            </div>
            <div className="flex flex-col justify-end gap-2 sm:flex-row">
              <button
                onClick={() => setShowAddForm(false)}
                className="text-xs px-3 py-1.5 text-slate-500 hover:text-slate-700"
              >
                Cancel
              </button>
              <button
                onClick={handleAddEntry}
                disabled={!form.version || !form.description}
                className="text-xs px-4 py-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-40"
              >
                Save Entry
              </button>
            </div>
          </div>
        )}

        {/* Changelog list */}
        {changelog.length === 0 && !showAddForm && (
          <p className="text-slate-400 text-sm text-center py-6">No changelog entries yet. Add one to start tracking changes.</p>
        )}
        <div className="space-y-3">
          {changelog.map(entry => (
            <div key={entry.id} className="flex gap-3 items-start">
              <div className="w-2 h-2 rounded-full bg-indigo-500 mt-1.5 flex-shrink-0" />
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-mono font-medium text-slate-800">{entry.version}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                    entry.change_type === 'extraction' ? 'bg-blue-100 text-blue-700'
                    : entry.change_type === 'classifier' ? 'bg-purple-100 text-purple-700'
                    : 'bg-amber-100 text-amber-700'
                  }`}>
                    {entry.change_type}
                  </span>
                  <span className="text-[10px] text-slate-400">
                    {new Date(entry.created_at).toLocaleDateString()}
                  </span>
                </div>
                <p className="text-xs text-slate-600 mt-0.5">{entry.description}</p>
                {entry.platforms_affected && entry.platforms_affected.length > 0 && (
                  <p className="text-[10px] text-slate-400 mt-0.5">
                    Platforms: {entry.platforms_affected.join(', ')}
                  </p>
                )}
                {entry.fields_affected && entry.fields_affected.length > 0 && (
                  <p className="text-[10px] text-slate-400">
                    Fields: {entry.fields_affected.join(', ')}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Main Component ──────────────────────────────────────────────────

export function ExtractionReports() {
  const [activeSubTab, setActiveSubTab] = useState<'reports' | 'versions'>('reports');
  const [stats, setStats] = useState<ExtractionReportStats | null>(null);
  const [reports, setReports] = useState<ExtractionReportItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [typeFilter, setTypeFilter] = useState<string>('');
  const [platformFilter, setPlatformFilter] = useState<string>('');
  const [resolvedFilter, setResolvedFilter] = useState<string>('unresolved');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [s, r] = await Promise.all([
        fetchExtractionReportStats(),
        fetchExtractionReports({
          report_type: typeFilter || undefined,
          platform: platformFilter || undefined,
          resolved: resolvedFilter === 'all' ? undefined : resolvedFilter === 'resolved',
          limit: 200,
        }),
      ]);
      setStats(s);
      setReports(r);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, [typeFilter, platformFilter, resolvedFilter]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleResolve = useCallback(async (id: string, resolved: boolean) => {
    try {
      await resolveExtractionReport(id, resolved);
      setReports(prev => prev.map(r => r.id === id ? { ...r, resolved } : r));
      setStats(prev => prev ? {
        ...prev,
        unresolved: prev.unresolved + (resolved ? -1 : 1),
      } : prev);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to update');
    }
  }, []);

  // Chart data
  const typeChartData = useMemo(() => {
    if (!stats) return [];
    return Object.entries(stats.by_type).map(([name, count]) => ({
      name: TYPE_LABELS[name] || name,
      count,
      fill: TYPE_COLORS[name] || '#94a3b8',
    }));
  }, [stats]);

  const platformChartData = useMemo(() => {
    if (!stats) return [];
    return Object.entries(stats.by_platform)
      .sort((a, b) => b[1] - a[1])
      .map(([name, count]) => ({
        name,
        count,
        fill: PLATFORM_COLORS[name] || '#94a3b8',
      }));
  }, [stats]);

  const fieldChartData = useMemo(() => {
    if (!stats) return [];
    return Object.entries(stats.by_field)
      .sort((a, b) => b[1] - a[1])
      .map(([name, count]) => ({ name, count }));
  }, [stats]);

  // Unique platforms for filter dropdown
  const platforms = useMemo(() => {
    const set = new Set(reports.map(r => r.platform_detected).filter(Boolean));
    return Array.from(set).sort();
  }, [reports]);

  return (
    <div className="max-w-7xl mx-auto overflow-x-hidden p-4 sm:p-6">
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" />
          {error}
          <button onClick={() => setError('')} className="ml-auto text-red-400 hover:text-red-600">&times;</button>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col items-start gap-4 mb-6 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Bug className="w-6 h-6 text-amber-500" />
            Extraction Reports
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Track extraction issues reported by users from the extension.
          </p>
        </div>
        {stats && activeSubTab === 'reports' && (
          <div className="grid w-full grid-cols-2 gap-3 lg:w-auto">
            <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-2 text-center">
              <p className="text-2xl font-bold text-amber-600">{stats.unresolved}</p>
              <p className="text-xs text-amber-500">Unresolved</p>
            </div>
            <div className="bg-slate-50 border border-slate-200 rounded-lg px-4 py-2 text-center">
              <p className="text-2xl font-bold text-slate-600">{stats.total}</p>
              <p className="text-xs text-slate-400">Total</p>
            </div>
          </div>
        )}
      </div>

      {/* Tab switcher */}
      <div className="mb-6 max-w-full overflow-x-auto">
        <div className="flex w-max gap-1 bg-slate-100 rounded-lg p-1">
        <button
          onClick={() => setActiveSubTab('reports')}
          className={`text-sm px-4 py-1.5 rounded-md transition font-medium ${
            activeSubTab === 'reports'
              ? 'bg-white text-slate-800 shadow-sm'
              : 'text-slate-500 hover:text-slate-700'
          }`}
        >
          Reports
        </button>
        <button
          onClick={() => setActiveSubTab('versions')}
          className={`text-sm px-4 py-1.5 rounded-md transition font-medium flex items-center gap-1.5 ${
            activeSubTab === 'versions'
              ? 'bg-white text-slate-800 shadow-sm'
              : 'text-slate-500 hover:text-slate-700'
          }`}
        >
          <GitCommitHorizontal className="w-3.5 h-3.5" />
          Version Timeline
        </button>
        </div>
      </div>

      {/* Version Timeline tab */}
      {activeSubTab === 'versions' && <VersionTimeline />}

      {/* Reports tab */}
      {activeSubTab === 'reports' && <>
      {/* Stats row */}
      {stats && (
        <div className="grid grid-cols-1 gap-4 mb-6 lg:grid-cols-3">
          {/* By type */}
          <div className="min-w-0 overflow-hidden bg-white border rounded-xl p-4 sm:p-5">
            <h3 className="text-sm font-semibold text-slate-700 mb-3">By Report Type</h3>
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={typeChartData} layout="vertical" margin={{ left: 4, right: 8 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" />
                <YAxis type="category" dataKey="name" width={88} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                  {typeChartData.map(e => <Cell key={e.name} fill={e.fill} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* By platform */}
          <div className="min-w-0 overflow-hidden bg-white border rounded-xl p-4 sm:p-5">
            <h3 className="text-sm font-semibold text-slate-700 mb-3">By Platform</h3>
            {platformChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={160}>
                <BarChart data={platformChartData} layout="vertical" margin={{ left: 4, right: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" />
                  <YAxis type="category" dataKey="name" width={88} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                    {platformChartData.map(e => <Cell key={e.name} fill={e.fill} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-slate-400 text-sm text-center py-8">No platform data yet</p>
            )}
          </div>

          {/* By field */}
          <div className="min-w-0 overflow-hidden bg-white border rounded-xl p-4 sm:p-5">
            <h3 className="text-sm font-semibold text-slate-700 mb-3">Most Reported Fields</h3>
            {fieldChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={160}>
                <BarChart data={fieldChartData} layout="vertical" margin={{ left: 4, right: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" />
                  <YAxis type="category" dataKey="name" width={88} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#f59e0b" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-slate-400 text-sm text-center py-8">No field data yet</p>
            )}
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-col gap-2 mb-4 sm:flex-row sm:items-center sm:gap-3">
        <select
          value={typeFilter}
          onChange={e => setTypeFilter(e.target.value)}
          className="w-full text-sm border rounded-lg px-3 py-1.5 text-slate-600 sm:w-auto"
        >
          <option value="">All Types</option>
          {Object.entries(TYPE_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
        <select
          value={platformFilter}
          onChange={e => setPlatformFilter(e.target.value)}
          className="w-full text-sm border rounded-lg px-3 py-1.5 text-slate-600 sm:w-auto"
        >
          <option value="">All Platforms</option>
          {platforms.map(p => <option key={p} value={p!}>{p}</option>)}
        </select>
        <select
          value={resolvedFilter}
          onChange={e => setResolvedFilter(e.target.value)}
          className="w-full text-sm border rounded-lg px-3 py-1.5 text-slate-600 sm:w-auto"
        >
          <option value="unresolved">Unresolved</option>
          <option value="resolved">Resolved</option>
          <option value="all">All</option>
        </select>
        <span className="text-sm text-slate-400 sm:ml-auto">{reports.length} reports</span>
      </div>

      {/* Reports list */}
      {loading && reports.length === 0 && (
        <p className="text-slate-500 text-center py-12">Loading reports...</p>
      )}

      {!loading && reports.length === 0 && (
        <div className="text-center py-16 text-slate-400">
          <Bug className="w-12 h-12 mx-auto mb-4 opacity-40" />
          <p className="text-lg">No extraction reports yet</p>
          <p className="text-sm mt-1">Reports will appear here when users report issues from the extension.</p>
        </div>
      )}

      <div className="space-y-3 mb-6">
        <AnimatePresence>
          {reports.map(report => {
            const Icon = TYPE_ICONS[report.report_type] || Bug;
            const isExpanded = expandedId === report.id;

            return (
              <motion.div
                key={report.id}
                layout
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className={`border rounded-xl p-4 bg-white shadow-sm transition ${
                  report.resolved ? 'opacity-60' : ''
                }`}
              >
                {/* Header row */}
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                    style={{ backgroundColor: `${TYPE_COLORS[report.report_type] || '#94a3b8'}15` }}
                  >
                    <Icon className="w-4 h-4" style={{ color: TYPE_COLORS[report.report_type] || '#94a3b8' }} />
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2 mb-1">
                      <span
                        className="text-xs font-medium px-2 py-0.5 rounded-full"
                        style={{
                          backgroundColor: `${TYPE_COLORS[report.report_type] || '#94a3b8'}15`,
                          color: TYPE_COLORS[report.report_type] || '#94a3b8',
                        }}
                      >
                        {TYPE_LABELS[report.report_type] || report.report_type}
                      </span>
                      {report.platform_detected && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
                          {report.platform_detected}
                        </span>
                      )}
                      {report.fields_flagged && report.fields_flagged.length > 0 && (
                        <span className="text-xs text-amber-600">
                          {report.fields_flagged.join(', ')}
                        </span>
                      )}
                      {report.resolved && (
                        <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                      )}
                    </div>

                    <p className="text-xs text-slate-500 truncate" title={report.url}>
                      {report.domain || new URL(report.url).hostname} &mdash; {report.url}
                    </p>

                    <p className="text-xs text-slate-400 mt-1">
                      {new Date(report.created_at).toLocaleString()}
                      {report.extension_version && <> &middot; v{report.extension_version}</>}
                    </p>
                  </div>

                  <div className="flex items-center gap-1 flex-shrink-0">
                    <button
                      onClick={() => setExpandedId(isExpanded ? null : report.id)}
                      className="p-1.5 text-slate-400 hover:text-slate-600 transition"
                      title="View details"
                    >
                      {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    </button>
                    <a
                      href={report.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="p-1.5 text-slate-400 hover:text-indigo-500 transition"
                      title="Open URL"
                    >
                      <ExternalLink className="w-4 h-4" />
                    </a>
                    <button
                      onClick={() => handleResolve(report.id, !report.resolved)}
                      className={`p-1.5 transition ${
                        report.resolved
                          ? 'text-emerald-500 hover:text-amber-500'
                          : 'text-slate-400 hover:text-emerald-500'
                      }`}
                      title={report.resolved ? 'Unresolve' : 'Mark resolved'}
                    >
                      <CheckCircle2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {/* Expanded detail */}
                <AnimatePresence>
                  {isExpanded && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="overflow-hidden"
                    >
                      <div className="mt-4 pt-4 border-t border-slate-100">
                        {/* Extracted vs Corrected diff */}
                        {report.extracted_data && report.corrected_data && (
                          <div className="grid grid-cols-1 gap-4 mb-4 md:grid-cols-2">
                            <div>
                              <h4 className="text-xs font-semibold text-slate-500 mb-2 flex items-center gap-1">
                                <Eye className="w-3 h-3" /> Extracted (what we got)
                              </h4>
                              <div className="bg-red-50/50 border border-red-100 rounded-lg p-3 text-xs space-y-1">
                                {Object.entries(report.extracted_data).map(([k, v]) => (
                                  <div key={k}>
                                    <span className="font-medium text-slate-500">{k}:</span>{' '}
                                    <span className={
                                      report.fields_flagged?.includes(k) ? 'text-red-600 font-medium' : 'text-slate-700'
                                    }>
                                      {v != null ? String(v) : <em className="text-slate-400">null</em>}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            </div>
                            <div>
                              <h4 className="text-xs font-semibold text-slate-500 mb-2 flex items-center gap-1">
                                <CheckCircle2 className="w-3 h-3" /> Corrected (user input)
                              </h4>
                              <div className="bg-emerald-50/50 border border-emerald-100 rounded-lg p-3 text-xs space-y-1">
                                {Object.entries(report.corrected_data).map(([k, v]) => (
                                  <div key={k}>
                                    <span className="font-medium text-slate-500">{k}:</span>{' '}
                                    <span className={
                                      report.fields_flagged?.includes(k) ? 'text-emerald-600 font-medium' : 'text-slate-700'
                                    }>
                                      {v != null ? String(v) : <em className="text-slate-400">null</em>}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          </div>
                        )}

                        {/* Notes */}
                        {report.notes && (
                          <div className="text-xs text-slate-600 bg-slate-50 rounded-lg p-3 mb-2">
                            <span className="font-medium text-slate-500">Notes:</span> {report.notes}
                          </div>
                        )}

                        {/* Metadata */}
                        <div className="text-xs text-slate-400 flex flex-wrap gap-4">
                          {report.extraction_method && <span>Method: {report.extraction_method}</span>}
                          <span>URL: <a href={report.url} target="_blank" rel="noopener noreferrer" className="text-indigo-500 hover:underline">{report.url}</a></span>
                        </div>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
      </>}
    </div>
  );
}
