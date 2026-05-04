import { useEffect, useMemo, useState } from 'react';
import { ResearchProfile } from '../types';
import { ScoutLogo } from './copilot/ScoutLogo';

const INTERNAL_SOURCE_OPTIONS = [
  { value: 'application', label: 'Applications' },
  { value: 'company_visit', label: 'Career-page visits' },
  { value: 'company_tech', label: 'Company tech signals' },
] as const;

const RESEARCH_SCOPE_OPTIONS = [
  { value: 'company_news', label: 'Company news' },
  { value: 'job_boards', label: 'Job boards' },
  { value: 'company_pages', label: 'Company pages' },
  { value: 'team_pages', label: 'Team pages' },
] as const;

const REMOTE_TYPE_OPTIONS = ['remote', 'hybrid', 'onsite'] as const;
const SENIORITY_OPTIONS = ['entry', 'mid', 'senior', 'staff', 'principal', 'manager'] as const;

export interface ResearchTrackerFormValues {
  name: string;
  objective: string;
  selected_domains: string[];
  selected_roles: string[];
  selected_companies: string[];
  keywords: string[];
  excluded_keywords: string[];
  source_types: string[];
  mode: ResearchProfile['mode'];
  frequency: ResearchProfile['frequency'];
  depth: ResearchProfile['depth'];
  notification_mode: ResearchProfile['notification_mode'];
  minimum_score: number;
  target_locations: string[];
  remote_types: string[];
  seniority_levels: string[];
  research_source_scopes: string[];
  use_profile_context: boolean;
  include_public_web_research: boolean;
  report_prompt_notes: string;
  max_search_queries: number;
  max_sources_per_run: number;
  active: boolean;
}

interface ResearchTrackerFormProps {
  mode: 'create' | 'edit';
  profile?: ResearchProfile | null;
  busy?: boolean;
  deleting?: boolean;
  researchConsentEnabled?: boolean;
  onCreate: (payload: ResearchTrackerFormValues) => Promise<void>;
  onUpdate: (id: string, payload: ResearchTrackerFormValues) => Promise<void>;
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

function toggleListEntry(values: string[], entry: string, checked: boolean): string[] {
  if (checked) {
    return values.includes(entry) ? values : [...values, entry];
  }
  return values.filter((value) => value !== entry);
}

function buildFormState(profile?: ResearchProfile | null): ResearchTrackerFormValues {
  const supportsReports = profile?.mode === 'research' || profile?.mode === 'hybrid';
  return {
    name: profile?.name || '',
    objective: profile?.objective || '',
    selected_domains: profile?.selected_domains || [],
    selected_roles: profile?.selected_roles || [],
    selected_companies: profile?.selected_companies || [],
    keywords: profile?.keywords || [],
    excluded_keywords: profile?.excluded_keywords || [],
    source_types: profile?.source_types?.length ? profile.source_types : ['application', 'company_visit', 'company_tech'],
    mode: profile?.mode || 'internal',
    frequency: profile?.frequency || 'weekly',
    depth: profile?.depth || 'standard',
    notification_mode: profile?.notification_mode || 'in_app',
    minimum_score: profile?.minimum_score ?? 70,
    target_locations: profile?.target_locations || [],
    remote_types: profile?.remote_types || [],
    seniority_levels: profile?.seniority_levels || [],
    research_source_scopes: profile?.research_source_scopes?.length ? profile.research_source_scopes : ['company_news', 'job_boards'],
    use_profile_context: profile?.use_profile_context ?? true,
    include_public_web_research: profile?.include_public_web_research ?? supportsReports,
    report_prompt_notes: profile?.report_prompt_notes || '',
    max_search_queries: profile?.max_search_queries ?? 8,
    max_sources_per_run: profile?.max_sources_per_run ?? 20,
    active: profile?.active ?? true,
  };
}

function SectionLabel({ title, body }: { title: string; body: string }) {
  return (
    <div>
      <div className="text-sm font-semibold text-slate-900">{title}</div>
      <p className="mt-1 text-xs leading-5 text-slate-500">{body}</p>
    </div>
  );
}

function buildScoutTrackerPrompt({
  name,
  objective,
  domains,
  roles,
  companies,
  locations,
  avoid,
}: {
  name: string;
  objective: string;
  domains: string;
  roles: string;
  companies: string;
  locations: string;
  avoid: string;
}) {
  const knownContext = [
    name.trim() ? `Tracker name idea: ${name.trim()}` : null,
    objective.trim() ? `What I care about: ${objective.trim()}` : null,
    roles.trim() ? `Roles I mentioned: ${roles.trim()}` : null,
    companies.trim() ? `Companies I mentioned: ${companies.trim()}` : null,
    domains.trim() ? `Domains I mentioned: ${domains.trim()}` : null,
    locations.trim() ? `Locations I mentioned: ${locations.trim()}` : null,
    avoid.trim() ? `Things to avoid: ${avoid.trim()}` : null,
  ].filter(Boolean);

  return [
    'Help me set up an Opportunity Radar tracker.',
    'Use my AppTrail profile, applications, inbox, and saved context when available.',
    'Return concise values I can paste into the tracker form using this format:',
    'Tracker name:',
    'What Radar should watch:',
    'Watch sources: Activity, Research, or Activity + research',
    'Cadence:',
    'Roles:',
    'Companies:',
    'Domains:',
    'Locations:',
    'Avoid:',
    knownContext.length ? `Known context:\n${knownContext.join('\n')}` : 'Known context: I am not sure yet, so ask only the few questions needed and then propose a strong starter tracker.',
  ].join('\n');
}

export function ResearchTrackerForm({
  mode,
  profile,
  busy = false,
  deleting = false,
  researchConsentEnabled = false,
  onCreate,
  onUpdate,
  onDelete,
  onCancelCreate,
}: ResearchTrackerFormProps) {
  const [form, setForm] = useState<ResearchTrackerFormValues>(() => buildFormState(profile));
  const [domainsText, setDomainsText] = useState(joinList(profile?.selected_domains));
  const [rolesText, setRolesText] = useState(joinList(profile?.selected_roles));
  const [companiesText, setCompaniesText] = useState(joinList(profile?.selected_companies));
  const [keywordsText, setKeywordsText] = useState(joinList(profile?.keywords));
  const [excludedKeywordsText, setExcludedKeywordsText] = useState(joinList(profile?.excluded_keywords));
  const [locationsText, setLocationsText] = useState(joinList(profile?.target_locations));

  useEffect(() => {
    const next = buildFormState(profile);
    setForm(next);
    setDomainsText(joinList(next.selected_domains));
    setRolesText(joinList(next.selected_roles));
    setCompaniesText(joinList(next.selected_companies));
    setKeywordsText(joinList(next.keywords));
    setExcludedKeywordsText(joinList(next.excluded_keywords));
    setLocationsText(joinList(next.target_locations));
  }, [profile, mode]);

  const supportsReports = form.mode === 'research' || form.mode === 'hybrid';
  const supportsSignals = form.mode === 'internal' || form.mode === 'hybrid';
  const canUseResearchMode = researchConsentEnabled;

  const canSubmit = useMemo(() => {
    if (!form.name.trim()) return false;
    if (!form.objective.trim()) return false;
    if (supportsReports && !researchConsentEnabled) return false;
    if (!supportsReports) return form.source_types.length > 0;
    return true;
  }, [form.name, form.objective, form.source_types.length, researchConsentEnabled, supportsReports]);

  useEffect(() => {
    setForm((current) => {
      if (supportsReports && !current.include_public_web_research) {
        return { ...current, include_public_web_research: true };
      }
      if (!supportsReports && current.include_public_web_research) {
        return { ...current, include_public_web_research: false };
      }
      return current;
    });
  }, [supportsReports]);

  const resetCreateState = () => {
    const empty = buildFormState(null);
    setForm(empty);
    setDomainsText('');
    setRolesText('');
    setCompaniesText('');
    setKeywordsText('');
    setExcludedKeywordsText('');
    setLocationsText('');
  };

  const submit = async () => {
    if (!canSubmit) return;

    const payload: ResearchTrackerFormValues = {
      ...form,
      name: form.name.trim(),
      objective: form.objective.trim(),
      selected_domains: parseList(domainsText),
      selected_roles: parseList(rolesText),
      selected_companies: parseList(companiesText),
      keywords: parseList(keywordsText),
      excluded_keywords: parseList(excludedKeywordsText),
      target_locations: parseList(locationsText),
      report_prompt_notes: form.report_prompt_notes.trim(),
      include_public_web_research: canUseResearchMode && supportsReports,
      research_source_scopes: supportsReports ? form.research_source_scopes : [],
    };

    if (mode === 'create') {
      await onCreate(payload);
      resetCreateState();
      return;
    }

    if (profile) {
      await onUpdate(profile.id, payload);
    }
  };

  const askScoutForTracker = () => {
    window.dispatchEvent(new CustomEvent('apptrail:open-scout', {
      detail: {
        autoSubmit: true,
        prompt: buildScoutTrackerPrompt({
          name: form.name,
          objective: form.objective,
          domains: domainsText,
          roles: rolesText,
          companies: companiesText,
          locations: locationsText,
          avoid: excludedKeywordsText,
        }),
      },
    }));
  };

  return (
    <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4 sm:p-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h2 className="font-semibold text-slate-800">{mode === 'create' ? 'Create Radar' : 'Tracker settings'}</h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-slate-500">
            Describe what you want Radar to watch. Optional details and production-style controls stay tucked away until you need them.
          </p>
        </div>
        {mode === 'edit' && profile?.last_run_at ? (
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-left text-[11px] text-slate-500 lg:text-right">
            <div>Last run</div>
            <div>{new Date(profile.last_run_at).toLocaleString()}</div>
          </div>
        ) : null}
      </div>

      {!researchConsentEnabled ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">
          Research reports need core, AI processing, and web research consent. You can still use Radar with your AppTrail activity until those settings are enabled.
        </div>
      ) : null}

      <div className="rounded-2xl border border-slate-200 bg-[#F8F8F4] p-4">
        <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="text-sm font-semibold text-slate-900">Start with plain language</div>
            <p className="mt-1 text-xs leading-5 text-slate-500">
              Radar can infer roles, companies, domains, and keywords from this description.
            </p>
          </div>
          <button
            type="button"
            onClick={askScoutForTracker}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 shadow-sm transition-colors hover:bg-slate-50"
          >
            <ScoutLogo className="h-5 w-5 text-slate-800" />
            Not sure? Ask Scout
          </button>
        </div>

        <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(220px,0.45fr)_minmax(0,1fr)]">
          <label className="block text-xs font-medium text-slate-600">
            Tracker name
            <input
              value={form.name}
              onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
              placeholder="AI/ML data science roles"
              className="mt-1 w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm"
            />
          </label>

          <label className="block text-xs font-medium text-slate-600">
            What should Radar watch?
            <textarea
              value={form.objective}
              onChange={(event) => setForm((current) => ({ ...current, objective: event.target.value }))}
              placeholder="I am targeting AI/ML data scientist roles at banks, fintech companies, and teams building virtual assistants. Prioritize NLP, search, LLM evaluation, Python analytics, and production ML systems. Avoid internships and unpaid roles."
              className="mt-1 min-h-[132px] w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm leading-6"
            />
          </label>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 2xl:grid-cols-[minmax(0,1fr)_minmax(260px,0.42fr)]">
        <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-3">
          <SectionLabel
            title="Watch sources"
            body="Choose the signal lane. You can start with AppTrail activity and turn on research once consent is enabled."
          />
          <div className="grid gap-2 lg:grid-cols-3">
            {[
              ['internal', 'Activity'],
              ['research', 'Research'],
              ['hybrid', 'Activity + research'],
            ].map(([value, label]) => {
              const needsConsent = value !== 'internal';
              const disabled = needsConsent && !researchConsentEnabled;
              const checked = form.mode === value;
              return (
                <label
                  key={value}
                  className={`block rounded-xl border px-3 py-3 text-sm transition-colors ${
                    checked ? 'border-slate-900 bg-slate-50 text-slate-900 shadow-sm' : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                  } ${disabled ? 'opacity-50' : 'cursor-pointer'}`}
                >
                  <div className="flex items-start gap-2">
                    <input
                      type="radio"
                      name="tracker-mode"
                      checked={checked}
                      disabled={disabled}
                      onChange={() => setForm((current) => ({ ...current, mode: value as ResearchProfile['mode'] }))}
                      className="mt-0.5"
                    />
                    <div className="min-w-0">
                      <div className="font-medium">{label}</div>
                      <div className="mt-1 text-xs leading-5 text-slate-500">
                        {value === 'internal'
                          ? 'Signals and next steps from your pipeline and messages.'
                          : value === 'research'
                            ? 'Saved reports with sourced findings and dated updates.'
                            : 'Pipeline-aware signals plus saved research reports.'}
                      </div>
                    </div>
                  </div>
                </label>
              );
            })}
          </div>
        </div>

        <label className="block rounded-xl border border-slate-200 bg-white p-3 text-xs font-medium text-slate-600">
          Update cadence
          <select
            value={form.frequency}
            onChange={(event) => setForm((current) => ({ ...current, frequency: event.target.value as ResearchProfile['frequency'] }))}
            className="mt-2 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="manual">Manual</option>
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="biweekly">Biweekly</option>
            <option value="monthly">Monthly</option>
          </select>
          <span className="mt-2 block text-xs font-normal leading-5 text-slate-500">
            Weekly is a good default for market and company movement.
          </span>
        </label>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <label className="block text-xs font-medium text-slate-600">
          Target locations
          <input
            value={locationsText}
            onChange={(event) => setLocationsText(event.target.value)}
            placeholder="Charlotte, Plano, New York, Remote"
            className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
          />
        </label>

        <label className="block text-xs font-medium text-slate-600">
          Avoid
          <input
            value={excludedKeywordsText}
            onChange={(event) => setExcludedKeywordsText(event.target.value)}
            placeholder="internships, unpaid roles, front-end-only roles"
            className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
          />
        </label>
      </div>

      <details className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <summary className="cursor-pointer list-none px-4 py-3 text-sm font-semibold text-slate-800 transition-colors hover:bg-slate-50">
          Optional focus details
        </summary>
        <div className="grid grid-cols-1 gap-3 border-t border-slate-200 p-4 lg:grid-cols-2">
          <label className="block text-xs font-medium text-slate-600">
            Roles
            <input
              value={rolesText}
              onChange={(event) => setRolesText(event.target.value)}
              placeholder="Data Scientist, ML Engineer, NLP Data Scientist"
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </label>

          <label className="block text-xs font-medium text-slate-600">
            Companies
            <input
              value={companiesText}
              onChange={(event) => setCompaniesText(event.target.value)}
              placeholder="Bank of America, JPMorgan Chase, Capital One"
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </label>

          <label className="block text-xs font-medium text-slate-600">
            Domains
            <input
              value={domainsText}
              onChange={(event) => setDomainsText(event.target.value)}
              placeholder="banking, fintech, virtual assistants, search"
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </label>

          <label className="block text-xs font-medium text-slate-600">
            Positive keywords
            <input
              value={keywordsText}
              onChange={(event) => setKeywordsText(event.target.value)}
              placeholder="NLP, LLM evaluation, Python, SQL, production ML"
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </label>
        </div>
      </details>

      <details className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <summary className="cursor-pointer list-none px-4 py-3 text-sm font-semibold text-slate-800 transition-colors hover:bg-slate-50">
          Advanced settings
        </summary>
        <div className="space-y-4 border-t border-slate-200 p-4">
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
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
              Depth
              <select
                value={form.depth}
                onChange={(event) => setForm((current) => ({ ...current, depth: event.target.value as ResearchProfile['depth'] }))}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                disabled={!supportsReports}
              >
                <option value="quick">Quick scan</option>
                <option value="standard">Standard</option>
                <option value="deep">Deep dive</option>
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
          </div>

          <div className="space-y-3 rounded-xl border border-slate-200 p-3">
            <SectionLabel
              title="Internal signal inputs"
              body="Used by activity and hybrid trackers when Radar ranks opportunities from existing AppTrail activity."
            />
            <div className="grid gap-2 sm:grid-cols-3">
              {INTERNAL_SOURCE_OPTIONS.map((option) => {
                const checked = form.source_types.includes(option.value);
                return (
                  <label
                    key={option.value}
                    className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-xs ${
                      checked ? 'border-slate-400 bg-slate-50 text-slate-900' : 'border-slate-200 text-slate-600'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          source_types: toggleListEntry(current.source_types, option.value, event.target.checked),
                        }))
                      }
                      disabled={!supportsSignals}
                    />
                    {option.label}
                  </label>
                );
              })}
            </div>
          </div>

          <div className={`space-y-3 rounded-xl border p-3 ${supportsReports ? 'border-slate-200' : 'border-slate-100 bg-slate-50/80'}`}>
            <SectionLabel
              title="Research run settings"
              body="Controls saved reports, public web coverage, and run size."
            />

            <div className="grid gap-2 sm:grid-cols-2">
              <label className="block text-xs font-medium text-slate-600">
                Max search queries
                <input
                  type="number"
                  min={1}
                  max={25}
                  value={form.max_search_queries}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      max_search_queries: Math.max(1, Math.min(25, Number(event.target.value || 1))),
                    }))
                  }
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  disabled={!supportsReports}
                />
              </label>

              <label className="block text-xs font-medium text-slate-600">
                Max sources per run
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={form.max_sources_per_run}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      max_sources_per_run: Math.max(1, Math.min(100, Number(event.target.value || 1))),
                    }))
                  }
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  disabled={!supportsReports}
                />
              </label>
            </div>

            <div className="grid gap-2 sm:grid-cols-2">
              <div>
                <div className="mb-2 text-xs font-medium text-slate-600">Remote preference</div>
                <div className="flex flex-wrap gap-2">
                  {REMOTE_TYPE_OPTIONS.map((option) => (
                    <label key={option} className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-xs text-slate-700">
                      <input
                        type="checkbox"
                        checked={form.remote_types.includes(option)}
                        onChange={(event) =>
                          setForm((current) => ({
                            ...current,
                            remote_types: toggleListEntry(current.remote_types, option, event.target.checked),
                          }))
                        }
                        disabled={!supportsReports}
                      />
                      {option}
                    </label>
                  ))}
                </div>
              </div>

              <div>
                <div className="mb-2 text-xs font-medium text-slate-600">Seniority</div>
                <div className="flex flex-wrap gap-2">
                  {SENIORITY_OPTIONS.map((option) => (
                    <label key={option} className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-xs text-slate-700">
                      <input
                        type="checkbox"
                        checked={form.seniority_levels.includes(option)}
                        onChange={(event) =>
                          setForm((current) => ({
                            ...current,
                            seniority_levels: toggleListEntry(current.seniority_levels, option, event.target.checked),
                          }))
                        }
                        disabled={!supportsReports}
                      />
                      {option}
                    </label>
                  ))}
                </div>
              </div>
            </div>

            <div>
              <div className="mb-2 text-xs font-medium text-slate-600">Research source scopes</div>
              <div className="grid gap-2 sm:grid-cols-2">
                {RESEARCH_SCOPE_OPTIONS.map((option) => (
                  <label key={option.value} className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-xs text-slate-700">
                    <input
                      type="checkbox"
                      checked={form.research_source_scopes.includes(option.value)}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          research_source_scopes: toggleListEntry(current.research_source_scopes, option.value, event.target.checked),
                        }))
                      }
                      disabled={!supportsReports}
                    />
                    {option.label}
                  </label>
                ))}
              </div>
            </div>

            <label className="block text-xs font-medium text-slate-600">
              Research notes
              <textarea
                value={form.report_prompt_notes}
                onChange={(event) => setForm((current) => ({ ...current, report_prompt_notes: event.target.value }))}
                placeholder="Bias toward teams with recent hiring, clear product momentum, and strong engineering blog coverage."
                className="mt-1 min-h-[88px] w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                disabled={!supportsReports}
              />
            </label>

            <div className="grid gap-2 sm:grid-cols-2">
              <label className="flex items-start gap-2 rounded-lg border border-slate-200 px-3 py-3 text-xs text-slate-700">
                <input
                  type="checkbox"
                  checked={form.use_profile_context}
                  onChange={(event) => setForm((current) => ({ ...current, use_profile_context: event.target.checked }))}
                  disabled={!supportsReports}
                />
                <span>
                  <span className="block font-medium text-slate-900">Use account context</span>
                  Pull in profile, application history, and company interactions to tailor the report.
                </span>
              </label>

              <label className="flex items-start gap-2 rounded-lg border border-slate-200 px-3 py-3 text-xs text-slate-700">
                <input
                  type="checkbox"
                  checked={supportsReports ? true : form.include_public_web_research}
                  onChange={(event) => setForm((current) => ({ ...current, include_public_web_research: event.target.checked }))}
                  disabled
                />
                <span>
                  <span className="block font-medium text-slate-900">Include public web research</span>
                  {supportsReports
                    ? 'Required for report-capable trackers so Radar can gather external evidence and save dated reports.'
                    : 'Available automatically when you switch this tracker into research or hybrid mode.'}
                </span>
              </label>
            </div>
          </div>
        </div>
      </details>

      <div className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 sm:flex-row sm:items-center sm:justify-between">
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={form.active}
            onChange={(event) => setForm((current) => ({ ...current, active: event.target.checked }))}
          />
          Tracker active
        </label>

        <div className="flex flex-wrap justify-end gap-2">
          {mode === 'create' && onCancelCreate ? (
            <button
              type="button"
              onClick={onCancelCreate}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-700"
            >
              Cancel
            </button>
          ) : null}
          {mode === 'edit' && profile ? (
            <button
              type="button"
              disabled={deleting}
              onClick={() => onDelete(profile.id)}
              className="rounded-lg border border-rose-200 px-3 py-2 text-sm text-rose-700 disabled:opacity-50"
            >
              {deleting ? 'Deleting...' : 'Delete'}
            </button>
          ) : null}
          <button
            type="button"
            disabled={busy || !canSubmit}
            onClick={submit}
            className="rounded-lg bg-slate-900 px-3 py-2 text-sm text-white disabled:opacity-50"
          >
            {busy ? 'Saving...' : mode === 'create' ? 'Create tracker' : 'Save changes'}
          </button>
        </div>
      </div>
    </div>
  );
}
