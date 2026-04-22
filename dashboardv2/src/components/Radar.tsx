import { useEffect, useMemo, useState } from 'react';
import {
  acceptRecommendedAction,
  createResearchProfile,
  fetchOpportunityBriefs,
  fetchOpportunitySignals,
  fetchRecommendedActions,
  fetchResearchRuns,
  fetchResearchProfiles,
  runResearchProfile,
  updateRecommendedAction,
} from '../lib/api';
import { OpportunityBrief, OpportunitySignal, RecommendedAction, ResearchProfile } from '../types';
import { RadarProfileForm } from './RadarProfileForm';
import { SignalFeed } from './SignalFeed';
import { OpportunityScoreBreakdown } from './OpportunityScoreBreakdown';
import { RecommendedActions } from './RecommendedActions';
import { BriefPanel } from './BriefPanel';
import { ResearchRunHistory } from './ResearchRunHistory';

interface ResearchRunSummary {
  id: string;
  status: string;
  created_at?: string | null;
  signal_counts?: Record<string, number>;
}

export function Radar() {
  const [profiles, setProfiles] = useState<ResearchProfile[]>([]);
  const [signals, setSignals] = useState<OpportunitySignal[]>([]);
  const [briefs, setBriefs] = useState<OpportunityBrief[]>([]);
  const [actions, setActions] = useState<RecommendedAction[]>([]);
  const [runs, setRuns] = useState<ResearchRunSummary[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(null);
  const [selectedSignalId, setSelectedSignalId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const load = async (profileId?: string | null) => {
    setLoading(true);
    try {
      const [p, s, b, a, r] = await Promise.all([
        fetchResearchProfiles(),
        fetchOpportunitySignals(profileId || undefined),
        fetchOpportunityBriefs(profileId || undefined),
        fetchRecommendedActions(profileId || undefined),
        fetchResearchRuns(profileId || undefined),
      ]);
      setProfiles(p);
      if (!selectedProfileId && p.length) setSelectedProfileId(p[0].id);
      setSignals(s);
      setBriefs(b);
      setActions(a);
      setRuns(r);
      if (s.length && !selectedSignalId) {
        setSelectedSignalId(s[0].id);
      }
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Radar request failed');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedSignal = useMemo(
    () => signals.find((signal) => signal.id === selectedSignalId) || signals[0],
    [selectedSignalId, signals]
  );
  const selectedBrief = useMemo(() => {
    if (!selectedSignal) return briefs[0];
    const signalTitle = selectedSignal.title.toLowerCase();
    return briefs.find((b) => (b.title || '').toLowerCase().includes(signalTitle)) || briefs[0];
  }, [briefs, selectedSignal]);

  const createProfile = async (payload: { name: string; objective: string }) => {
    setCreating(true);
    try {
      await createResearchProfile({
        ...payload,
        selected_domains: [],
        selected_roles: [],
        selected_companies: [],
        keywords: [],
        excluded_keywords: [],
        source_types: ['application', 'company_visit', 'company_tech'],
        frequency: 'daily',
        notification_mode: 'in_app',
        minimum_score: 70,
        active: true,
      } as any);
      await load();
    } finally {
      setCreating(false);
    }
  };

  const runNow = async () => {
    if (!selectedProfileId) return;
    try {
      await runResearchProfile(selectedProfileId);
      await load(selectedProfileId);
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to run tracker');
    }
  };

  return (
    <div className="flex-1 overflow-auto p-6 space-y-6">
      <div className="rounded-2xl border border-slate-200 bg-white p-5">
        <h1 className="text-2xl font-serif font-bold text-slate-900">Opportunity Radar</h1>
        <p className="mt-2 text-sm text-slate-600">
          Monitor companies, roles, and domains you care about. Radar turns job postings, company activity, and your own application history into scored signals, opportunity briefs, and next actions.
        </p>
        <div className="mt-4 flex gap-3">
          <button onClick={runNow} disabled={!selectedProfileId} className="px-4 py-2 rounded-xl bg-slate-900 text-white text-sm disabled:opacity-50">Run Now</button>
        </div>
        {errorMessage ? (
          <div className="mt-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
            {errorMessage}
          </div>
        ) : null}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
        <div className="xl:col-span-3 space-y-4">
          <div className="rounded-2xl border border-slate-200 bg-white p-4 space-y-2">
            <h2 className="font-semibold text-slate-800">Trackers</h2>
            {profiles.map((profile) => (
              <button key={profile.id} onClick={() => { setSelectedProfileId(profile.id); setSelectedSignalId(null); load(profile.id); }} className={`w-full text-left rounded-xl px-3 py-2 border ${selectedProfileId === profile.id ? 'bg-slate-100 border-slate-300' : 'border-slate-200'}`}>
                <div className="text-sm font-medium text-slate-900">{profile.name}</div>
                <div className="text-xs text-slate-500">{profile.frequency} · min {profile.minimum_score}</div>
              </button>
            ))}
          </div>

          <RadarProfileForm creating={creating} onCreate={createProfile} />

          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <h2 className="font-semibold text-slate-800 mb-2">Recent runs</h2>
            <ResearchRunHistory runs={runs} />
          </div>
        </div>

        <div className="xl:col-span-5 rounded-2xl border border-slate-200 bg-white p-4">
          <h2 className="font-semibold text-slate-800 mb-3">Signal feed</h2>
          <SignalFeed
            loading={loading}
            signals={signals}
            selectedSignalId={selectedSignal?.id}
            onSelectSignal={(signal) => setSelectedSignalId(signal.id)}
          />
        </div>

        <div className="xl:col-span-4 space-y-4">
          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <h2 className="font-semibold text-slate-800 mb-2">Score breakdown</h2>
            <OpportunityScoreBreakdown score={selectedSignal?.score} />
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <h2 className="font-semibold text-slate-800 mb-2">Recommended actions</h2>
            <RecommendedActions
              actions={actions}
              onAccept={async (actionId) => {
                try {
                  await acceptRecommendedAction(actionId);
                  await load(selectedProfileId);
                  setErrorMessage(null);
                } catch (error) {
                  setErrorMessage(error instanceof Error ? error.message : 'Failed to accept action');
                }
              }}
              onDismiss={async (actionId) => {
                try {
                  await updateRecommendedAction(actionId, { status: 'dismissed' });
                  await load(selectedProfileId);
                  setErrorMessage(null);
                } catch (error) {
                  setErrorMessage(error instanceof Error ? error.message : 'Failed to dismiss action');
                }
              }}
            />
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <h2 className="font-semibold text-slate-800 mb-2">Opportunity brief</h2>
            <BriefPanel brief={selectedBrief} />
          </div>
        </div>
      </div>
    </div>
  );
}
