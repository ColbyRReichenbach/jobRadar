import { useEffect, useMemo, useState } from 'react';
import { ResearchProfile } from '../types';

const SOURCE_OPTIONS = [
  { value: 'application', label: 'Applications' },
  { value: 'company_visit', label: 'Career-page visits' },
  { value: 'company_tech', label: 'Company tech signals' },
] as const;

interface RadarProfileFormValues {
  name: string;
  objective: string;
  selected_domains: string[];
  selected_roles: string[];
  selected_companies: string[];
  keywords: string[];
  excluded_keywords: string[];
  source_types: string[];
  frequency: ResearchProfile['frequency'];
  notification_mode: ResearchProfile['notification_mode'];
  minimum_score: number;
  active: boolean;
}

interface RadarProfileFormProps {
  mode: 'create' | 'edit';
  profile?: ResearchProfile | null;
  busy?: boolean;
  deleting?: boolean;
  onCreate: (payload: RadarProfileFormValues) => Promise<void>;
  onUpdate: (id: string, payload: RadarProfileFormValues) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onCancelCreate?: () => void;
}

function parseList(raw: string): string[] {
  return raw
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function joinList(values?: string[]): string {
  return (values || []).join(', ');
}

function buildFormState(profile?: ResearchProfile | null): RadarProfileFormValues {
  return {
    name: profile?.name || '',
    objective: profile?.objective || '',
    selected_domains: profile?.selected_domains || [],
    selected_roles: profile?.selected_roles || [],
    selected_companies: profile?.selected_companies || [],
    keywords: profile?.keywords || [],
    excluded_keywords: profile?.excluded_keywords || [],
    source_types: profile?.source_types?.length ? profile.source_types : ['application', 'company_visit', 'company_tech'],
    frequency: profile?.frequency || 'daily',
    notification_mode: profile?.notification_mode || 'in_app',
    minimum_score: profile?.minimum_score ?? 70,
    active: profile?.active ?? true,
  };
}

export function RadarProfileForm({
  mode,
  profile,
  busy = false,
  deleting = false,
  onCreate,
  onUpdate,
  onDelete,
  onCancelCreate,
}: RadarProfileFormProps) {
  const [form, setForm] = useState<RadarProfileFormValues>(() => buildFormState(profile));
  const [selectedDomainsText, setSelectedDomainsText] = useState(joinList(profile?.selected_domains));
  const [selectedRolesText, setSelectedRolesText] = useState(joinList(profile?.selected_roles));
  const [selectedCompaniesText, setSelectedCompaniesText] = useState(joinList(profile?.selected_companies));
  const [keywordsText, setKeywordsText] = useState(joinList(profile?.keywords));
  const [excludedKeywordsText, setExcludedKeywordsText] = useState(joinList(profile?.excluded_keywords));

  useEffect(() => {
    const next = buildFormState(profile);
    setForm(next);
    setSelectedDomainsText(joinList(next.selected_domains));
    setSelectedRolesText(joinList(next.selected_roles));
    setSelectedCompaniesText(joinList(next.selected_companies));
    setKeywordsText(joinList(next.keywords));
    setExcludedKeywordsText(joinList(next.excluded_keywords));
  }, [profile, mode]);

  const canSubmit = useMemo(() => form.name.trim().length > 0 && form.source_types.length > 0, [form.name, form.source_types.length]);

  const submit = async () => {
    if (!canSubmit) return;
    const payload: RadarProfileFormValues = {
      ...form,
      name: form.name.trim(),
      objective: form.objective.trim(),
      selected_domains: parseList(selectedDomainsText),
      selected_roles: parseList(selectedRolesText),
      selected_companies: parseList(selectedCompaniesText),
      keywords: parseList(keywordsText),
      excluded_keywords: parseList(excludedKeywordsText),
    };

    if (mode === 'create') {
      await onCreate(payload);
      setForm(buildFormState(null));
      setSelectedDomainsText('');
      setSelectedRolesText('');
      setSelectedCompaniesText('');
      setKeywordsText('');
      setExcludedKeywordsText('');
      return;
    }

    if (profile) {
      await onUpdate(profile.id, payload);
    }
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="font-semibold text-slate-800">
            {mode === 'create' ? 'New tracker' : 'Tracker settings'}
          </h2>
          <p className="mt-1 text-xs text-slate-500">
            {mode === 'create'
              ? 'Create a tracker with the sources and filters Radar should watch.'
              : 'Tune what this tracker should collect, score, and surface.'}
          </p>
        </div>
        {mode === 'edit' && profile?.last_run_at ? (
          <div className="text-right text-[11px] text-slate-500">
            <div>Last run</div>
            <div>{new Date(profile.last_run_at).toLocaleString()}</div>
          </div>
        ) : null}
      </div>

      <div className="space-y-2">
        <label className="block text-xs font-medium text-slate-600">
          Tracker name
          <input
            value={form.name}
            onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
            placeholder="Growth-stage infra roles"
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
        </label>

        <label className="block text-xs font-medium text-slate-600">
          Objective
          <textarea
            value={form.objective}
            onChange={(event) => setForm((current) => ({ ...current, objective: event.target.value }))}
            placeholder="Focus on signals that point to infra hiring at companies already on my shortlist."
            className="mt-1 min-h-[88px] w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
        </label>
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <label className="block text-xs font-medium text-slate-600">
          Minimum score
          <input
            type="number"
            min={0}
            max={100}
            value={form.minimum_score}
            onChange={(event) =>
              setForm((current) => ({
                ...current,
                minimum_score: Math.max(0, Math.min(100, Number(event.target.value || 0))),
              }))
            }
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
        </label>

        <label className="block text-xs font-medium text-slate-600">
          Frequency
          <select
            value={form.frequency}
            onChange={(event) => setForm((current) => ({ ...current, frequency: event.target.value as ResearchProfile['frequency'] }))}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="manual">Manual</option>
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
          </select>
        </label>

        <label className="block text-xs font-medium text-slate-600">
          Notification mode
          <select
            value={form.notification_mode}
            onChange={(event) => setForm((current) => ({ ...current, notification_mode: event.target.value as ResearchProfile['notification_mode'] }))}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="in_app">In app</option>
            <option value="email_digest">Email digest</option>
          </select>
        </label>

        <label className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium text-slate-600 sm:mt-6">
          <input
            type="checkbox"
            checked={form.active}
            onChange={(event) => setForm((current) => ({ ...current, active: event.target.checked }))}
          />
          Tracker active
        </label>
      </div>

      <div className="space-y-2">
        <div className="text-xs font-medium text-slate-600">Sources</div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          {SOURCE_OPTIONS.map((option) => {
            const checked = form.source_types.includes(option.value);
            return (
              <label key={option.value} className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-xs ${checked ? 'border-slate-400 bg-slate-50 text-slate-900' : 'border-slate-200 text-slate-600'}`}>
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(event) => {
                    setForm((current) => ({
                      ...current,
                      source_types: event.target.checked
                        ? [...current.source_types, option.value]
                        : current.source_types.filter((entry) => entry !== option.value),
                    }));
                  }}
                />
                {option.label}
              </label>
            );
          })}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-2">
        <label className="block text-xs font-medium text-slate-600">
          Domains
          <input
            value={selectedDomainsText}
            onChange={(event) => setSelectedDomainsText(event.target.value)}
            placeholder="healthcare_ai, devtools, fintech"
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
        </label>

        <label className="block text-xs font-medium text-slate-600">
          Roles
          <input
            value={selectedRolesText}
            onChange={(event) => setSelectedRolesText(event.target.value)}
            placeholder="Platform Engineer, Staff Backend Engineer"
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
        </label>

        <label className="block text-xs font-medium text-slate-600">
          Companies
          <input
            value={selectedCompaniesText}
            onChange={(event) => setSelectedCompaniesText(event.target.value)}
            placeholder="Stripe, Datadog, Vercel"
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
        </label>

        <label className="block text-xs font-medium text-slate-600">
          Keywords
          <input
            value={keywordsText}
            onChange={(event) => setKeywordsText(event.target.value)}
            placeholder="distributed systems, observability, platform"
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
        </label>

        <label className="block text-xs font-medium text-slate-600">
          Excluded keywords
          <input
            value={excludedKeywordsText}
            onChange={(event) => setExcludedKeywordsText(event.target.value)}
            placeholder="intern, contract, onsite only"
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
        </label>
      </div>

      <div className="flex flex-wrap gap-2 pt-1">
        {mode === 'create' && onCancelCreate ? (
          <button
            type="button"
            onClick={onCancelCreate}
            className="px-3 py-2 rounded-xl border border-slate-300 text-sm text-slate-700"
          >
            Cancel
          </button>
        ) : null}
        <button
          type="button"
          onClick={submit}
          disabled={busy || !canSubmit}
          className="px-3 py-2 rounded-xl bg-slate-800 text-white text-sm disabled:opacity-50"
        >
          {busy ? (mode === 'create' ? 'Creating...' : 'Saving...') : mode === 'create' ? 'Create tracker' : 'Save changes'}
        </button>
        {mode === 'edit' && profile ? (
          <button
            type="button"
            onClick={() => onDelete(profile.id)}
            disabled={deleting}
            className="px-3 py-2 rounded-xl border border-rose-300 text-sm text-rose-700 disabled:opacity-50"
          >
            {deleting ? 'Deleting...' : 'Delete tracker'}
          </button>
        ) : null}
      </div>
    </div>
  );
}
