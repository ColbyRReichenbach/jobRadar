import { useEffect, useMemo, useState } from 'react';
import {
  ConsentStatus,
  acceptRecommendedAction,
  acceptResearchReportAction,
  createResearchProfile,
  deleteResearchProfile,
  fetchConsent,
  fetchOpportunityBriefs,
  fetchOpportunitySignals,
  fetchRecommendedActions,
  fetchResearchFeedbackStats,
  fetchResearchReport,
  fetchResearchReportDiff,
  fetchResearchReports,
  fetchResearchProfiles,
  fetchResearchRunTrace,
  fetchResearchRuns,
  runResearchProfile,
  sendResearchFeedback,
  sendResearchReportFeedback,
  updateRecommendedAction,
  updateResearchProfile,
} from '../lib/api';
import {
  OpportunityBrief,
  OpportunitySignal,
  RadarFeedbackStats,
  RecommendedAction,
  ResearchProfile,
  ResearchReport,
  ResearchReportDetail,
  ResearchReportDiff,
  ResearchRun,
  ResearchRunTrace,
} from '../types';
import { RadarModeSwitch } from './RadarModeSwitch';
import { RadarProfileForm, type RadarProfileFormValues } from './RadarProfileForm';
import { SignalFeed } from './SignalFeed';
import { OpportunityScoreBreakdown } from './OpportunityScoreBreakdown';
import { RecommendedActions } from './RecommendedActions';
import { BriefPanel } from './BriefPanel';
import { ResearchRunHistory } from './ResearchRunHistory';
import { SignalDetailPanel } from './SignalDetailPanel';
import { RadarFeedbackPanel } from './RadarFeedbackPanel';
import { RadarInsightsPanel } from './RadarInsightsPanel';
import { ResearchReportList } from './ResearchReportList';
import { ResearchReportDetail as ResearchReportDetailPanel } from './ResearchReportDetail';
import { ResearchReportDiff as ResearchReportDiffPanel } from './ResearchReportDiff';
import { ResearchRunTracePanel } from './ResearchRunTracePanel';

type RadarSurface = 'signals' | 'reports';

interface RadarFocusRequest {
  profileId?: string;
  signalId?: string;
  reportId?: string;
  token: number;
}

interface RadarProps {
  focusRequest?: RadarFocusRequest | null;
}

function supportsSignalSurface(mode?: ResearchProfile['mode'] | null): boolean {
  return mode !== 'research';
}

function supportsReportSurface(mode?: ResearchProfile['mode'] | null): boolean {
  return mode === 'research' || mode === 'hybrid';
}

function resolveSurface(
  profile: ResearchProfile | null,
  currentSurface: RadarSurface,
  preferredSurface?: RadarSurface | null
): RadarSurface {
  const nextSurface = preferredSurface || currentSurface;
  if (!profile) return nextSurface;
  if (nextSurface === 'reports' && supportsReportSurface(profile.mode)) return 'reports';
  if (nextSurface === 'signals' && supportsSignalSurface(profile.mode)) return 'signals';
  if (supportsReportSurface(profile.mode) && !supportsSignalSurface(profile.mode)) return 'reports';
  return 'signals';
}

function readTraceDebugFlag(): boolean {
  if (import.meta.env.DEV) return true;
  if (typeof window === 'undefined') return false;
  return ['127.0.0.1', 'localhost'].includes(window.location.hostname);
}

function hasResearchConsent(consent: ConsentStatus | null): boolean {
  return Boolean(consent?.consents.core && consent?.consents.ai_processing && consent?.consents.web_research);
}

export function Radar({ focusRequest }: RadarProps) {
  const [profiles, setProfiles] = useState<ResearchProfile[]>([]);
  const [signals, setSignals] = useState<OpportunitySignal[]>([]);
  const [briefs, setBriefs] = useState<OpportunityBrief[]>([]);
  const [actions, setActions] = useState<RecommendedAction[]>([]);
  const [runs, setRuns] = useState<ResearchRun[]>([]);
  const [reports, setReports] = useState<ResearchReport[]>([]);
  const [feedbackStats, setFeedbackStats] = useState<RadarFeedbackStats | null>(null);
  const [consent, setConsent] = useState<ConsentStatus | null>(null);
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(null);
  const [selectedSignalId, setSelectedSignalId] = useState<string | null>(null);
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [surface, setSurface] = useState<RadarSurface>('signals');
  const [selectedReport, setSelectedReport] = useState<ResearchReportDetail | null>(null);
  const [selectedDiff, setSelectedDiff] = useState<ResearchReportDiff | null>(null);
  const [selectedTrace, setSelectedTrace] = useState<ResearchRunTrace | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingReport, setLoadingReport] = useState(false);
  const [loadingTrace, setLoadingTrace] = useState(false);
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

  const selectedSignal = useMemo(
    () => signals.find((signal) => signal.id === selectedSignalId) || signals[0] || null,
    [selectedSignalId, signals]
  );

  const selectedBrief = useMemo(() => {
    if (!selectedSignal) return briefs[0] || null;
    return briefs.find((brief) => brief.signal_id === selectedSignal.id) || null;
  }, [briefs, selectedSignal]);

  const selectedReportSummary = useMemo(
    () => reports.find((report) => report.id === selectedReportId) || null,
    [reports, selectedReportId]
  );

  const signalActions = useMemo(() => {
    const profileActions = selectedProfileId
      ? actions.filter((action) => action.profile_id === selectedProfileId)
      : actions;
    if (!selectedSignal) return profileActions;
    const matching = profileActions.filter((action) => action.signal_id === selectedSignal.id);
    return matching.length ? matching : profileActions;
  }, [actions, selectedProfileId, selectedSignal]);

  const reportActions = selectedReport?.actions || [];
  const traceDebugEnabled = readTraceDebugFlag();
  const latestRun = runs[0] || null;
  const latestRunSignalCount = Object.values(latestRun?.signal_counts || {}).reduce((total, count) => total + count, 0);
  const researchConsentEnabled = hasResearchConsent(consent);

  const load = async (
    requestedProfileId?: string | null,
    preferredSignalId?: string | null,
    preferredReportId?: string | null,
    preferredSurface?: RadarSurface | null
  ) => {
    setLoading(true);
    try {
      const [profileRows, feedbackStatsRow, consentRow] = await Promise.all([
        fetchResearchProfiles(),
        fetchResearchFeedbackStats(),
        fetchConsent(),
      ]);

      const requestedProfileExists =
        requestedProfileId !== undefined &&
        requestedProfileId !== null &&
        profileRows.some((profile) => profile.id === requestedProfileId);
      const activeProfileId =
        requestedProfileExists
          ? requestedProfileId
          : (selectedProfileId && profileRows.some((profile) => profile.id === selectedProfileId) ? selectedProfileId : profileRows[0]?.id || null);
      const activeProfile = profileRows.find((profile) => profile.id === activeProfileId) || null;

      const [signalRows, briefRows, actionRows, runRows, reportRows] = await Promise.all([
        fetchOpportunitySignals(activeProfileId || undefined),
        fetchOpportunityBriefs(activeProfileId || undefined),
        fetchRecommendedActions(activeProfileId || undefined),
        fetchResearchRuns(activeProfileId || undefined),
        fetchResearchReports(activeProfileId || undefined),
      ]);

      const nextSurface = resolveSurface(activeProfile, surface, preferredReportId ? 'reports' : preferredSurface);
      const nextSignalId =
        supportsSignalSurface(activeProfile?.mode) && signalRows.length
          ? (preferredSignalId && signalRows.some((signal) => signal.id === preferredSignalId)
              ? preferredSignalId
              : selectedSignalId && signalRows.some((signal) => signal.id === selectedSignalId)
                ? selectedSignalId
                : signalRows[0].id)
          : null;
      const nextReportId =
        supportsReportSurface(activeProfile?.mode) && reportRows.length
          ? (preferredReportId && reportRows.some((report) => report.id === preferredReportId)
              ? preferredReportId
              : selectedReportId && reportRows.some((report) => report.id === selectedReportId)
                ? selectedReportId
                : reportRows[0].id)
          : null;
      const nextReport = reportRows.find((report) => report.id === nextReportId) || null;
      const nextRunId =
        nextReport?.run_id && runRows.some((run) => run.id === nextReport.run_id)
          ? nextReport.run_id
          : (selectedRunId && runRows.some((run) => run.id === selectedRunId) ? selectedRunId : runRows[0]?.id || null);

      setProfiles(profileRows);
      setSignals(signalRows);
      setBriefs(briefRows);
      setActions(actionRows);
      setRuns(runRows);
      setReports(reportRows);
      setFeedbackStats(feedbackStatsRow);
      setConsent(consentRow);
      setSelectedProfileId(activeProfileId);
      setSelectedSignalId(nextSignalId);
      setSelectedReportId(nextReportId);
      setSelectedRunId(nextRunId);
      setSurface(nextSurface);
      setEditingMode(activeProfileId ? 'edit' : 'create');
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
    load(
      focusRequest.profileId ?? undefined,
      focusRequest.signalId ?? undefined,
      focusRequest.reportId ?? undefined,
      focusRequest.reportId ? 'reports' : undefined
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusRequest?.token]);

  useEffect(() => {
    if (!selectedReportId) {
      setSelectedReport(null);
      setSelectedDiff(null);
      return;
    }

    let cancelled = false;
    setLoadingReport(true);

    Promise.all([fetchResearchReport(selectedReportId), fetchResearchReportDiff(selectedReportId)])
      .then(([reportRow, diffRow]) => {
        if (cancelled) return;
        setSelectedReport(reportRow);
        setSelectedDiff(diffRow);
        if (reportRow.run_id) {
          setSelectedRunId((current) => current || reportRow.run_id || null);
        }
      })
      .catch((error) => {
        if (cancelled) return;
        setErrorMessage(error instanceof Error ? error.message : 'Failed to load research report');
      })
      .finally(() => {
        if (!cancelled) setLoadingReport(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedReportId]);

  useEffect(() => {
    if (!traceDebugEnabled || !selectedRunId) {
      setSelectedTrace(null);
      return;
    }

    let cancelled = false;
    setLoadingTrace(true);

    fetchResearchRunTrace(selectedRunId)
      .then((traceRow) => {
        if (!cancelled) setSelectedTrace(traceRow);
      })
      .catch((error) => {
        if (!cancelled) setErrorMessage(error instanceof Error ? error.message : 'Failed to load run trace');
      })
      .finally(() => {
        if (!cancelled) setLoadingTrace(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedRunId, traceDebugEnabled]);

  const createProfile = async (payload: RadarProfileFormValues) => {
    setCreating(true);
    try {
      const created = await createResearchProfile(payload);
      setEditingMode('edit');
      await load(created.id, undefined, undefined, created.mode === 'research' ? 'reports' : 'signals');
    } finally {
      setCreating(false);
    }
  };

  const saveProfile = async (id: string, payload: RadarProfileFormValues) => {
    setSavingProfile(true);
    try {
      const updated = await updateResearchProfile(id, payload);
      await load(updated.id, undefined, undefined, updated.mode === 'research' ? 'reports' : surface);
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
    if (!selectedProfileId || !selectedProfile) return;
    if (supportsReportSurface(selectedProfile.mode) && !researchConsentEnabled) {
      setErrorMessage('Research and hybrid trackers need core, AI processing, and web research consent before they can run.');
      return;
    }

    setRunning(true);
    try {
      const queuedRun = await runResearchProfile(selectedProfileId);
      await load(
        selectedProfileId,
        selectedSignal?.id,
        selectedReportId,
        selectedProfile.mode === 'research' ? 'reports' : surface
      );
      if (queuedRun?.id) setSelectedRunId(queuedRun.id);
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to run tracker');
    } finally {
      setRunning(false);
    }
  };

  const updateSignalActionStatus = async (actionId: string, status: 'accepted' | 'dismissed' | 'completed') => {
    setBusyActionId(actionId);
    try {
      if (status === 'accepted') {
        await acceptRecommendedAction(actionId);
      } else {
        await updateRecommendedAction(actionId, { status });
      }
      await load(selectedProfileId, selectedSignal?.id, selectedReportId, surface);
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : `Failed to update action to ${status}`);
    } finally {
      setBusyActionId(null);
    }
  };

  const updateReportActionStatus = async (actionId: string, status: 'accepted' | 'dismissed' | 'completed') => {
    if (!selectedReportId) return;
    setBusyActionId(actionId);
    try {
      if (status === 'accepted') {
        await acceptResearchReportAction(selectedReportId, actionId);
      } else {
        await updateRecommendedAction(actionId, { status });
      }
      await load(selectedProfileId, selectedSignal?.id, selectedReportId, 'reports');
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : `Failed to update report action to ${status}`);
    } finally {
      setBusyActionId(null);
    }
  };

  const submitSignalFeedback = async (payload: { rating: string; notes?: string }) => {
    if (!selectedSignal?.id) return;
    setSavingFeedback(true);
    try {
      await sendResearchFeedback({
        signal_id: selectedSignal.id,
        brief_id: selectedBrief?.id,
        action_id: signalActions[0]?.id,
        feedback_scope: 'signal',
        rating: payload.rating,
        notes: payload.notes,
      });
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

  const submitReportFeedback = async (payload: { rating: string; notes?: string }) => {
    if (!selectedReportId) return;
    setSavingFeedback(true);
    try {
      await sendResearchReportFeedback(selectedReportId, payload);
      setFeedbackStats(await fetchResearchFeedbackStats());
      setFeedbackMessage('Feedback saved.');
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to save report feedback');
      setFeedbackMessage(null);
    } finally {
      setSavingFeedback(false);
    }
  };

  return (
    <div className="flex-1 overflow-auto bg-[#F5F5F0] px-4 py-4 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-[118rem] space-y-5">
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <h1 className="text-2xl font-serif font-bold text-slate-900">Opportunity Radar</h1>
              <p className="mt-2 max-w-3xl text-sm text-slate-600">
                Track the roles, companies, and market signals that matter to your search. Radar turns your activity and saved research into ranked opportunities, evidence-backed reports, and focused next steps.
              </p>
            </div>
            <div className="flex flex-wrap gap-2 sm:gap-3">
              <button
                type="button"
                onClick={() => setEditingMode('create')}
                className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50"
              >
                New tracker
              </button>
              <button
                type="button"
                onClick={runNow}
                disabled={!selectedProfileId || running || Boolean(selectedProfile && supportsReportSurface(selectedProfile.mode) && !researchConsentEnabled)}
                className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-800 disabled:opacity-50"
              >
                {running ? 'Running...' : 'Run now'}
              </button>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 2xl:grid-cols-4">
            <div className="rounded-xl border border-slate-200 p-3">
              <div className="text-xs uppercase tracking-wide text-slate-500">Trackers</div>
              <div className="mt-1 text-xl font-semibold text-slate-900">{profiles.length}</div>
            </div>
            <div className="rounded-xl border border-slate-200 p-3">
              <div className="text-xs uppercase tracking-wide text-slate-500">Signals in view</div>
              <div className="mt-1 text-xl font-semibold text-slate-900">{signals.length}</div>
            </div>
            <div className="rounded-xl border border-slate-200 p-3">
              <div className="text-xs uppercase tracking-wide text-slate-500">Reports in view</div>
              <div className="mt-1 text-xl font-semibold text-slate-900">{reports.length}</div>
            </div>
            <div className="rounded-xl border border-slate-200 p-3">
              <div className="text-xs uppercase tracking-wide text-slate-500">Latest run output</div>
              <div className="mt-1 text-xl font-semibold text-slate-900">{latestRunSignalCount}</div>
            </div>
          </div>

          {selectedProfile && supportsReportSurface(selectedProfile.mode) && !researchConsentEnabled ? (
            <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
              This tracker needs core, AI processing, and web research consent before Radar can create saved reports from public sources. Update privacy settings to enable research reports.
            </div>
          ) : null}

          {errorMessage ? (
            <div className="mt-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
              {errorMessage}
            </div>
          ) : null}
        </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(280px,340px)_minmax(0,1fr)] min-[1900px]:grid-cols-[minmax(280px,340px)_minmax(420px,0.95fr)_minmax(460px,1.15fr)]">
        <div className="space-y-4">
          <div className="rounded-2xl border border-slate-200 bg-white p-4 space-y-2">
            <h2 className="font-semibold text-slate-800">Trackers</h2>
            {!profiles.length ? (
              <div className="text-sm text-slate-500">No trackers yet. Create one to tell Radar what to watch.</div>
            ) : (
              profiles.map((profile) => (
                <button
                  key={profile.id}
                  type="button"
                  onClick={() => {
                    setSelectedProfileId(profile.id);
                    setEditingMode('edit');
                    load(profile.id, undefined, undefined, profile.mode === 'research' ? 'reports' : surface);
                  }}
                  className={`w-full rounded-xl border px-3 py-2 text-left ${
                    selectedProfileId === profile.id ? 'border-slate-300 bg-slate-100' : 'border-slate-200'
                  }`}
                >
                  <div className="text-sm font-medium text-slate-900">{profile.name}</div>
                  <div className="mt-1 text-xs text-slate-500">
                    {profile.mode} · {profile.frequency} · min {profile.minimum_score}
                  </div>
                  <div className="mt-1 text-[11px] text-slate-500">
                    {profile.active ? 'active' : 'paused'}
                    {profile.next_run_at ? ` · next ${new Date(profile.next_run_at).toLocaleString()}` : ''}
                  </div>
                </button>
              ))
            )}
          </div>

          <RadarModeSwitch
            trackerMode={selectedProfile?.mode}
            surface={surface}
            onChange={(nextSurface) => setSurface(nextSurface)}
          />

          <details
            className="overflow-hidden rounded-2xl border border-slate-200 bg-white"
            open={editingMode === 'create' || !selectedProfile}
          >
            <summary className="cursor-pointer list-none px-4 py-3 text-sm font-semibold text-slate-800 transition-colors hover:bg-slate-50">
              <div className="flex items-center justify-between gap-3">
                <span>{editingMode === 'create' || !selectedProfile ? 'New tracker' : 'Tracker settings'}</span>
                <span className="text-xs font-normal text-slate-500">
                  {selectedProfile ? selectedProfile.name : 'Define scope'}
                </span>
              </div>
            </summary>
            <div className="border-t border-slate-200 p-4">
              <RadarProfileForm
                mode={editingMode === 'create' || !selectedProfile ? 'create' : 'edit'}
                profile={editingMode === 'edit' ? selectedProfile : null}
                busy={creating || savingProfile}
                deleting={deletingProfile}
                researchConsentEnabled={researchConsentEnabled}
                onCreate={createProfile}
                onUpdate={saveProfile}
                onDelete={removeProfile}
                onCancelCreate={() => setEditingMode(selectedProfile ? 'edit' : 'create')}
              />
            </div>
          </details>

          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <div className="mb-2 flex items-center justify-between gap-3">
              <h2 className="font-semibold text-slate-800">Recent runs</h2>
              {selectedProfile ? <div className="text-xs text-slate-500">{selectedProfile.name}</div> : null}
            </div>
            <ResearchRunHistory
              runs={runs}
              selectedRunId={selectedRunId}
              onSelectRun={(runId) => setSelectedRunId(runId)}
            />
          </div>
        </div>

        <div className="flex min-h-[32rem] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white p-4 shadow-sm xl:min-h-[calc(100vh-13rem)]">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-semibold text-slate-800">{surface === 'signals' ? 'Signal feed' : 'Report history'}</h2>
            {selectedProfile ? <div className="text-xs text-slate-500">Tracker: {selectedProfile.name}</div> : null}
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto pr-1">
            {surface === 'signals' ? (
              <SignalFeed
                loading={loading}
                signals={signals}
                selectedSignalId={selectedSignal?.id}
                onSelectSignal={(signal) => setSelectedSignalId(signal.id)}
              />
            ) : (
              <ResearchReportList
                reports={reports}
                selectedReportId={selectedReportId}
                loading={loading}
                onSelectReport={(report) => {
                  setSelectedReportId(report.id);
                  setSelectedRunId(report.run_id || null);
                  setSurface('reports');
                }}
              />
            )}
          </div>
        </div>

        <div className="space-y-4 xl:col-span-2 min-[1900px]:col-span-1">
          {surface === 'signals' ? (
            <>
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <h2 className="mb-2 font-semibold text-slate-800">Selected signal</h2>
                <SignalDetailPanel signal={selectedSignal || undefined} />
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
                  actions={signalActions}
                  busyActionId={busyActionId}
                  onAccept={(actionId) => updateSignalActionStatus(actionId, 'accepted')}
                  onDismiss={(actionId) => updateSignalActionStatus(actionId, 'dismissed')}
                  onComplete={(actionId) => updateSignalActionStatus(actionId, 'completed')}
                />
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <h2 className="mb-2 font-semibold text-slate-800">Opportunity brief</h2>
                <BriefPanel brief={selectedBrief || undefined} />
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <h2 className="mb-2 font-semibold text-slate-800">Feedback</h2>
                <RadarFeedbackPanel
                  busy={savingFeedback}
                  message={feedbackMessage}
                  enabled={Boolean(selectedSignal?.id)}
                  title="Was this signal useful?"
                  description="Capture whether the current signal, brief, and action framing were actually helpful."
                  onSubmit={submitSignalFeedback}
                />
              </div>
            </>
          ) : (
            <>
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <h2 className="mb-2 font-semibold text-slate-800">Selected report</h2>
                <ResearchReportDetailPanel report={selectedReport} loading={loadingReport} />
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <h2 className="mb-2 font-semibold text-slate-800">What changed</h2>
                <ResearchReportDiffPanel diff={selectedDiff} loading={loadingReport} />
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="mb-2">
                  <h2 className="font-semibold text-slate-800">Report actions</h2>
                  <p className="mt-1 text-xs text-slate-500">
                    Use this list to move dated research findings into your actual job search workflow.
                  </p>
                </div>
                <RecommendedActions
                  actions={reportActions}
                  busyActionId={busyActionId}
                  onAccept={(actionId) => updateReportActionStatus(actionId, 'accepted')}
                  onDismiss={(actionId) => updateReportActionStatus(actionId, 'dismissed')}
                  onComplete={(actionId) => updateReportActionStatus(actionId, 'completed')}
                />
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <h2 className="mb-2 font-semibold text-slate-800">Feedback</h2>
                <RadarFeedbackPanel
                  busy={savingFeedback}
                  message={feedbackMessage}
                  enabled={Boolean(selectedReportId)}
                  title="Was this report useful?"
                  description="Save report-level feedback so recurring runs can be tuned against what actually helps your search."
                  onSubmit={submitReportFeedback}
                />
              </div>

              {traceDebugEnabled ? (
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <h2 className="mb-2 font-semibold text-slate-800">Run trace</h2>
                  <p className="mb-3 text-xs text-slate-500">
                    Review the recorded steps and source activity behind this report.
                  </p>
                  <ResearchRunTracePanel trace={selectedTrace} loading={loadingTrace} />
                </div>
              ) : null}
            </>
          )}

          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <h2 className="mb-2 font-semibold text-slate-800">Radar quality</h2>
            <RadarInsightsPanel stats={feedbackStats} />
          </div>

          {surface === 'reports' && selectedReportSummary && !selectedReport ? (
            <div className="rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-500">
              Loading report {selectedReportSummary.title}...
            </div>
          ) : null}
        </div>
      </div>
    </div>
    </div>
  );
}
