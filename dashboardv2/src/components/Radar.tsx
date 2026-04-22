import { useEffect, useMemo, useState } from 'react';
import {
  acceptRecommendedAction,
  createResearchProfile,
  deleteResearchProfile,
  fetchOpportunityBriefs,
  fetchResearchFeedbackStats,
  fetchOpportunitySignals,
  fetchRecommendedActions,
  fetchResearchRuns,
  fetchResearchProfiles,
  runResearchProfile,
  sendResearchFeedback,
  updateRecommendedAction,
  updateResearchProfile,
} from '../lib/api';
import { OpportunityBrief, OpportunitySignal, RadarFeedbackStats, RecommendedAction, ResearchProfile } from '../types';
import { RadarProfileForm } from './RadarProfileForm';
import { SignalFeed } from './SignalFeed';
import { OpportunityScoreBreakdown } from './OpportunityScoreBreakdown';
import { RecommendedActions } from './RecommendedActions';
import { BriefPanel } from './BriefPanel';
import { ResearchRunHistory } from './ResearchRunHistory';
import { SignalDetailPanel } from './SignalDetailPanel';
import { RadarFeedbackPanel } from './RadarFeedbackPanel';
import { RadarInsightsPanel } from './RadarInsightsPanel';

interface ResearchRunSummary {
  id: string;
  profile_id: string;
  status: string;
  created_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  source_counts?: Record<string, number>;
  signal_counts?: Record<string, number>;
  error_message?: string | null;
}

type RadarProfileFormValues = {
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
};

interface RadarFocusRequest {
  profileId?: string;
  signalId?: string;
  token: number;
}

interface RadarProps {
  focusRequest?: RadarFocusRequest | null;
}

export function Radar({ focusRequest }: RadarProps) {
  const [profiles, setProfiles] = useState<ResearchProfile[]>([]);
  const [signals, setSignals] = useState<OpportunitySignal[]>([]);
  const [briefs, setBriefs] = useState<OpportunityBrief[]>([]);
  const [actions, setActions] = useState<RecommendedAction[]>([]);
  const [runs, setRuns] = useState<ResearchRunSummary[]>([]);
  const [feedbackStats, setFeedbackStats] = useState<RadarFeedbackStats | null>(null);
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(null);
  const [selectedSignalId, setSelectedSignalId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);
  const [deletingProfile, setDeletingProfile] = useState(false);
  const [running, setRunning] = useState(false);
  const [busyActionId, setBusyActionId] = useState<string | null>(null);
  const [savingFeedback, setSavingFeedback] = useState(false);
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);
  const [editingMode, setEditingMode] = useState<'create' | 'edit'>('edit');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const selectedProfile = useMemo(
    () => profiles.find((profile) => profile.id === selectedProfileId) || null,
    [profiles, selectedProfileId]
  );

  const load = async (requestedProfileId?: string | null, preferredSignalId?: string | null) => {
    setLoading(true);
    try {
      const profileRows = await fetchResearchProfiles();
      const requestedProfileExists =
        requestedProfileId !== undefined &&
        requestedProfileId !== null &&
        profileRows.some((profile) => profile.id === requestedProfileId);
      const activeProfileId =
        requestedProfileExists
          ? requestedProfileId
          : (selectedProfileId && profileRows.some((profile) => profile.id === selectedProfileId) ? selectedProfileId : profileRows[0]?.id || null);

      const [signalRows, briefRows, actionRows, runRows, feedbackStatsRow] = await Promise.all([
        fetchOpportunitySignals(activeProfileId || undefined),
        fetchOpportunityBriefs(activeProfileId || undefined),
        fetchRecommendedActions(activeProfileId || undefined),
        fetchResearchRuns(activeProfileId || undefined),
        fetchResearchFeedbackStats(),
      ]);

      setProfiles(profileRows);
      setSelectedProfileId(activeProfileId);
      setSignals(signalRows);
      setBriefs(briefRows);
      setActions(actionRows);
      setRuns(runRows);
      setFeedbackStats(feedbackStatsRow);
      setSelectedSignalId((current) => {
        if (!signalRows.length) return null;
        if (preferredSignalId && signalRows.some((signal) => signal.id === preferredSignalId)) return preferredSignalId;
        if (current && signalRows.some((signal) => signal.id === current)) return current;
        return signalRows[0].id;
      });
      if (activeProfileId) setEditingMode('edit');
      setErrorMessage(null);
      setFeedbackMessage(null);
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

  useEffect(() => {
    if (!focusRequest?.token) return;
    load(focusRequest.profileId ?? undefined, focusRequest.signalId ?? undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusRequest?.token]);

  const selectedSignal = useMemo(
    () => signals.find((signal) => signal.id === selectedSignalId) || signals[0],
    [selectedSignalId, signals]
  );

  const selectedBrief = useMemo(() => {
    if (!selectedSignal) return briefs[0];
    return briefs.find((brief) => brief.signal_id === selectedSignal.id);
  }, [briefs, selectedSignal]);

  const displayedActions = useMemo(() => {
    const profileActions = selectedProfileId
      ? actions.filter((action) => action.profile_id === selectedProfileId)
      : actions;
    if (!selectedSignal) return profileActions;
    const signalActions = profileActions.filter((action) => action.signal_id === selectedSignal.id);
    return signalActions.length ? signalActions : profileActions;
  }, [actions, selectedProfileId, selectedSignal]);

  const latestRun = runs[0];
  const latestRunSignalCount = Object.values(latestRun?.signal_counts || {}).reduce((total, count) => total + count, 0);
  const primaryAction = displayedActions[0];

  const createProfile = async (payload: RadarProfileFormValues) => {
    setCreating(true);
    try {
      const created = await createResearchProfile(payload);
      setEditingMode('edit');
      await load(created.id);
    } finally {
      setCreating(false);
    }
  };

  const saveProfile = async (id: string, payload: RadarProfileFormValues) => {
    setSavingProfile(true);
    try {
      await updateResearchProfile(id, payload);
      await load(id);
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to update tracker');
    } finally {
      setSavingProfile(false);
    }
  };

  const removeProfile = async (id: string) => {
    if (!window.confirm('Delete this tracker and its Radar history?')) return;
    setDeletingProfile(true);
    try {
      await deleteResearchProfile(id);
      const remaining = profiles.filter((profile) => profile.id !== id);
      const nextProfileId = remaining[0]?.id || null;
      setEditingMode(nextProfileId ? 'edit' : 'create');
      await load(nextProfileId);
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to delete tracker');
    } finally {
      setDeletingProfile(false);
    }
  };

  const runNow = async () => {
    if (!selectedProfileId) return;
    setRunning(true);
    try {
      await runResearchProfile(selectedProfileId);
      await load(selectedProfileId);
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to run tracker');
    } finally {
      setRunning(false);
    }
  };

  const updateActionStatus = async (actionId: string, status: 'accepted' | 'dismissed' | 'completed') => {
    setBusyActionId(actionId);
    try {
      if (status === 'accepted') {
        await acceptRecommendedAction(actionId);
      } else {
        await updateRecommendedAction(actionId, { status });
      }
      await load(selectedProfileId);
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : `Failed to update action to ${status}`);
    } finally {
      setBusyActionId(null);
    }
  };

  const submitFeedback = async (payload: { signal_id?: string; brief_id?: string; action_id?: string; rating: string; notes?: string }) => {
    setSavingFeedback(true);
    try {
      await sendResearchFeedback(payload);
      setFeedbackStats(await fetchResearchFeedbackStats());
      setFeedbackMessage('Feedback saved.');
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to save Radar feedback');
      setFeedbackMessage(null);
    } finally {
      setSavingFeedback(false);
    }
  };

  return (
    <div className="flex-1 overflow-auto p-6 space-y-6">
      <div className="rounded-2xl border border-slate-200 bg-white p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h1 className="text-2xl font-serif font-bold text-slate-900">Opportunity Radar</h1>
            <p className="mt-2 max-w-3xl text-sm text-slate-600">
              Radar turns your saved jobs, company activity, and internal hiring signals into ranked opportunities. The goal is not more noise. It is to show why something matters, what to do next, and which tracker surfaced it.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => setEditingMode('create')}
              className="rounded-xl border border-slate-300 px-4 py-2 text-sm text-slate-700"
            >
              New tracker
            </button>
            <button
              type="button"
              onClick={runNow}
              disabled={!selectedProfileId || running}
              className="rounded-xl bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
            >
              {running ? 'Running...' : 'Run now'}
            </button>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-4">
          <div className="rounded-xl border border-slate-200 p-3">
            <div className="text-xs uppercase tracking-wide text-slate-500">Trackers</div>
            <div className="mt-1 text-xl font-semibold text-slate-900">{profiles.length}</div>
          </div>
          <div className="rounded-xl border border-slate-200 p-3">
            <div className="text-xs uppercase tracking-wide text-slate-500">Signals in view</div>
            <div className="mt-1 text-xl font-semibold text-slate-900">{signals.length}</div>
          </div>
          <div className="rounded-xl border border-slate-200 p-3">
            <div className="text-xs uppercase tracking-wide text-slate-500">Actions in view</div>
            <div className="mt-1 text-xl font-semibold text-slate-900">{displayedActions.length}</div>
          </div>
          <div className="rounded-xl border border-slate-200 p-3">
            <div className="text-xs uppercase tracking-wide text-slate-500">Latest run output</div>
            <div className="mt-1 text-xl font-semibold text-slate-900">{latestRunSignalCount}</div>
          </div>
        </div>

        {errorMessage ? (
          <div className="mt-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
            {errorMessage}
          </div>
        ) : null}
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
        <div className="space-y-4 xl:col-span-3">
          <div className="rounded-2xl border border-slate-200 bg-white p-4 space-y-2">
            <h2 className="font-semibold text-slate-800">Trackers</h2>
            {!profiles.length ? (
              <div className="text-sm text-slate-500">No trackers yet. Create one to tell Radar what to watch.</div>
            ) : (
              profiles.map((profile) => (
                <button
                  key={profile.id}
                  onClick={() => {
                    setSelectedProfileId(profile.id);
                    setEditingMode('edit');
                    load(profile.id);
                  }}
                  className={`w-full rounded-xl border px-3 py-2 text-left ${selectedProfileId === profile.id ? 'border-slate-300 bg-slate-100' : 'border-slate-200'}`}
                >
                  <div className="text-sm font-medium text-slate-900">{profile.name}</div>
                  <div className="mt-1 text-xs text-slate-500">
                    {profile.frequency} · min {profile.minimum_score} · {profile.active ? 'active' : 'paused'}
                  </div>
                </button>
              ))
            )}
          </div>

          <RadarProfileForm
            mode={editingMode === 'create' || !selectedProfile ? 'create' : 'edit'}
            profile={editingMode === 'edit' ? selectedProfile : null}
            busy={creating || savingProfile}
            deleting={deletingProfile}
            onCreate={createProfile}
            onUpdate={saveProfile}
            onDelete={removeProfile}
            onCancelCreate={() => setEditingMode(selectedProfile ? 'edit' : 'create')}
          />

          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <div className="mb-2 flex items-center justify-between gap-3">
              <h2 className="font-semibold text-slate-800">Recent runs</h2>
              {selectedProfile ? <div className="text-xs text-slate-500">{selectedProfile.name}</div> : null}
            </div>
            <ResearchRunHistory runs={runs} />
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-4 xl:col-span-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 className="font-semibold text-slate-800">Signal feed</h2>
            {selectedProfile ? <div className="text-xs text-slate-500">Tracker: {selectedProfile.name}</div> : null}
          </div>
          <SignalFeed
            loading={loading}
            signals={signals}
            selectedSignalId={selectedSignal?.id}
            onSelectSignal={(signal) => setSelectedSignalId(signal.id)}
          />
        </div>

        <div className="space-y-4 xl:col-span-5">
          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <h2 className="mb-2 font-semibold text-slate-800">Selected signal</h2>
            <SignalDetailPanel signal={selectedSignal} />
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <h2 className="mb-2 font-semibold text-slate-800">Score breakdown</h2>
            <OpportunityScoreBreakdown score={selectedSignal?.score} />
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <div className="mb-2">
              <h2 className="font-semibold text-slate-800">Recommended actions</h2>
              <p className="mt-1 text-xs text-slate-500">
                {selectedSignal ? 'Showing actions tied to the selected signal when available.' : 'Select a signal to focus the action list.'}
              </p>
            </div>
            <RecommendedActions
              actions={displayedActions}
              busyActionId={busyActionId}
              onAccept={(actionId) => updateActionStatus(actionId, 'accepted')}
              onDismiss={(actionId) => updateActionStatus(actionId, 'dismissed')}
              onComplete={(actionId) => updateActionStatus(actionId, 'completed')}
            />
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <h2 className="mb-2 font-semibold text-slate-800">Opportunity brief</h2>
            <BriefPanel brief={selectedBrief} />
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <h2 className="mb-2 font-semibold text-slate-800">Feedback</h2>
            <RadarFeedbackPanel
              busy={savingFeedback}
              message={feedbackMessage}
              signalId={selectedSignal?.id}
              briefId={selectedBrief?.id}
              actionId={primaryAction?.id}
              onSubmit={submitFeedback}
            />
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <h2 className="mb-2 font-semibold text-slate-800">Radar quality</h2>
            <RadarInsightsPanel stats={feedbackStats} />
          </div>
        </div>
      </div>
    </div>
  );
}
