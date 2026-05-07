import { useState, useEffect, useCallback, lazy, Suspense } from 'react';
import { Sidebar } from './components/Sidebar';
import { EmailFeed } from './components/EmailFeed';
import { LoginPage } from './components/LoginPage';
import { ErrorBoundary } from './components/ErrorBoundary';
import { NotificationCenter } from './components/NotificationCenter';
import { initialJobs, initialEmails } from './data/mockData';
import { Job, Email } from './types';
import { Menu, X } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { fetchJobs, fetchEmails } from './lib/api';
import { AuthProvider, useAuth } from './lib/AuthContext';
import { AddJobModal } from './components/AddJobModal';
import { ConsentModal } from './components/ConsentModal';
import { CopilotLauncher } from './components/copilot/CopilotLauncher';
import { cn } from './lib/utils';
import { Logo } from './components/Logo';
import { COPILOT_ENABLED } from './lib/featureFlags';

// Lazy-loaded route components for code splitting
const KanbanBoard = lazy(() => import('./components/KanbanBoard').then(m => ({ default: m.KanbanBoard })));
const JobSearch = lazy(() => import('./components/JobSearch').then(m => ({ default: m.JobSearch })));
const Analytics = lazy(() => import('./components/Analytics').then(m => ({ default: m.Analytics })));
const Conversations = lazy(() => import('./components/Conversations').then(m => ({ default: m.Conversations })));
const NetworkPage = lazy(() => import('./components/NetworkPage').then(m => ({ default: m.NetworkPage })));
const Calendar = lazy(() => import('./components/Calendar').then(m => ({ default: m.Calendar })));
const Radar = lazy(() => import('./components/Radar').then(m => ({ default: m.Radar })));
const Settings = lazy(() => import('./components/Settings').then(m => ({ default: m.Settings })));
const ClassifierAudit = lazy(() => import('./components/ClassifierAudit').then(m => ({ default: m.ClassifierAudit })));
const ExtractionReports = lazy(() => import('./components/ExtractionReports').then(m => ({ default: m.ExtractionReports })));
const AiOps = lazy(() => import('./components/admin/AiOps').then(m => ({ default: m.AiOps })));
const SourceIntelligenceAdmin = lazy(() => import('./components/admin/SourceIntelligence').then(m => ({ default: m.SourceIntelligenceAdmin })));
const ProfilePage = lazy(() => import('./components/ProfilePage').then(m => ({ default: m.ProfilePage })));

const AI_OPS_ENABLED = import.meta.env.VITE_ADMIN_AI_OPS_ENABLED === 'true'
  || (import.meta.env.DEV && import.meta.env.VITE_ADMIN_AI_OPS_ENABLED !== 'false');

const TAB_TITLES: Record<string, string> = {
  dashboard: 'Dashboard',
  search: 'Job Search',
  radar: 'Opportunity Radar',
  analytics: 'Analytics',
  conversations: 'Conversations',
  network: 'Network',
  calendar: 'Calendar',
  profile: 'Profile',
  settings: 'Settings',
  audit: 'Classifier Audit',
  'extraction-reports': 'Extraction Reports',
  'source-intelligence': 'Source Intelligence',
  ...(AI_OPS_ENABLED ? { 'ai-ops': 'AI Ops' } : {}),
  emails: 'Inbox',
};
const ADMIN_TABS = new Set(['audit', 'extraction-reports', 'source-intelligence', ...(AI_OPS_ENABLED ? ['ai-ops'] : [])]);

function LazyFallback() {
  return (
    <div className="flex flex-1 items-center justify-center">
      <div className="w-8 h-8 border-2 rounded-full border-slate-300 border-t-slate-600 animate-spin" />
    </div>
  );
}

const USE_API = true;
function AppContent() {
  const { user, loading: authLoading, needsConsent, signOut, refreshUser } = useAuth();
  const [activeTab, setActiveTab] = useState('dashboard');
  const [jobs, setJobs] = useState<Job[]>(USE_API ? [] : initialJobs);
  const [emails, setEmails] = useState<Email[]>(USE_API ? [] : initialEmails);
  const [isInboxCollapsed, setIsInboxCollapsed] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [loading, setLoading] = useState(USE_API);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showAddJobModal, setShowAddJobModal] = useState(false);
  const [isDesktop, setIsDesktop] = useState(false);
  const [pendingJobDraft, setPendingJobDraft] = useState<Partial<Job> | null>(null);
  const [emailFocusRequest, setEmailFocusRequest] = useState<{
    emailId: string;
    threadId?: string;
    tab: 'emails' | 'conversations';
    token: number;
  } | null>(null);
  const [networkFocusRequest, setNetworkFocusRequest] = useState<{
    email: string;
    token: number;
  } | null>(null);
  const [calendarFocusRequest, setCalendarFocusRequest] = useState<{
    interviewId: string;
    token: number;
  } | null>(null);
  const [dashboardFocusRequest, setDashboardFocusRequest] = useState<{
    jobId: string;
    token: number;
  } | null>(null);
  const [radarFocusRequest, setRadarFocusRequest] = useState<{
    profileId?: string;
    signalId?: string;
    reportId?: string;
    token: number;
  } | null>(null);

  const loadData = useCallback(async () => {
    if (!USE_API) return;
    try {
      const [jobsData, emailsData] = await Promise.all([
        fetchJobs(),
        fetchEmails(),
      ]);
      setJobs(jobsData);
      setEmails(emailsData);
      setLoadError(null);
    } catch (err) {
      console.error('Failed to load data from API:', err);
      setLoadError('Live AppTrail data is temporarily unavailable. Retry in a moment.');
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch data from API if configured
  useEffect(() => {
    if (!USE_API) return;
    // Wait for auth to finish loading before fetching data
    if (authLoading) return;
    if (!user) return;

    loadData();
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, [authLoading, loadData, user]);

  // Dynamic page title
  useEffect(() => {
    const title = TAB_TITLES[activeTab];
    document.title = title ? `${title} — Opportunity Radar` : 'Opportunity Radar';
  }, [activeTab]);

  useEffect(() => {
    const media = window.matchMedia('(min-width: 768px)');
    const sync = () => setIsDesktop(media.matches);
    sync();
    media.addEventListener('change', sync);
    return () => media.removeEventListener('change', sync);
  }, []);

  // Close mobile menu when tab changes
  useEffect(() => {
    setIsMobileMenuOpen(false);
  }, [activeTab]);

  useEffect(() => {
    if (user && ADMIN_TABS.has(activeTab) && !user.is_admin) {
      setActiveTab('dashboard');
    }
  }, [activeTab, user]);

  const handleMobileSetActiveTab = useCallback((tab: string) => {
    setActiveTab(tab);
    setIsMobileMenuOpen(false);
  }, []);

  const handleOpenEmail = useCallback((email: any) => {
    const emailKind = email.email_type || email.type;
    const tab = emailKind === 'conversation' ? 'conversations' : 'emails';
    setActiveTab(tab);
    setEmailFocusRequest({
      emailId: email.id,
      threadId: email.thread_id || email.threadId || undefined,
      tab,
      token: Date.now(),
    });
  }, []);

  const handleNotificationNavigate = useCallback((actionUrl: string | null) => {
    if (!actionUrl) return;
    const resolved = new URL(actionUrl, window.location.origin);
    const emailId = resolved.searchParams.get('email_id');
    const threadId = resolved.searchParams.get('thread_id') || undefined;
    const tab = resolved.searchParams.get('tab');
    const email = resolved.searchParams.get('email');
    const interviewId = resolved.searchParams.get('interview_id');
    const jobId = resolved.searchParams.get('job_id');
    const profileId = resolved.searchParams.get('profile_id') || undefined;
    const signalId = resolved.searchParams.get('signal_id') || undefined;
    const reportId = resolved.searchParams.get('report_id') || undefined;

    if (resolved.pathname === '/network') {
      setActiveTab('network');
      if (email) {
        setNetworkFocusRequest({
          email,
          token: Date.now(),
        });
      }
      return;
    }

    if (resolved.pathname === '/calendar' && interviewId) {
      setActiveTab('calendar');
      setCalendarFocusRequest({
        interviewId,
        token: Date.now(),
      });
      return;
    }

    if ((resolved.pathname === '/dashboard' || resolved.pathname === '/') && jobId) {
      setActiveTab('dashboard');
      setDashboardFocusRequest({
        jobId,
        token: Date.now(),
      });
      return;
    }

    if (resolved.pathname === '/radar') {
      setActiveTab('radar');
      setRadarFocusRequest({
        profileId,
        signalId,
        reportId,
        token: Date.now(),
      });
      return;
    }

    if (resolved.pathname === '/conversations' || tab === 'conversations') {
      if (!emailId) return;
      setActiveTab('conversations');
      setEmailFocusRequest({
        emailId,
        threadId,
        tab: 'conversations',
        token: Date.now(),
      });
      return;
    }

    if ((resolved.pathname === '/emails' || tab === 'emails') && emailId) {
      setActiveTab('emails');
      setEmailFocusRequest({
        emailId,
        threadId,
        tab: 'emails',
        token: Date.now(),
      });
      return;
    }
  }, []);

  const handleOpenAddJob = useCallback((draft?: Partial<Job>) => {
    setPendingJobDraft(draft || null);
    setShowAddJobModal(true);
  }, []);

  const handleJobAdded = useCallback((job: Job) => {
    setJobs((prev) => {
      if (prev.some((existing) => existing.id === job.id)) return prev;
      return [job, ...prev];
    });
    setShowAddJobModal(false);
    setPendingJobDraft(null);
    setActiveTab('dashboard');
  }, []);

  if (!authLoading && !user) {
    return <LoginPage />;
  }

  if (!authLoading && needsConsent) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-[#F5F5F0]">
        <ConsentModal
          onAccepted={() => refreshUser()}
          onDeclined={() => signOut()}
        />
      </div>
    );
  }

  const isAdminWorkspace = ADMIN_TABS.has(activeTab);
  const showInbox = !isAdminWorkspace && activeTab !== 'emails' && activeTab !== 'conversations';
  const dockNotificationsInInbox = isDesktop && showInbox && !isInboxCollapsed;
  const notificationClassName = cn(
    'fixed z-40 transition-[right,top] duration-300',
    isDesktop
      ? showInbox
        ? 'top-4 right-24'
        : 'top-4 right-4'
      : 'top-3 right-16'
  );

  if (loading || authLoading) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-[#F5F5F0]">
        <div className="text-center">
          <div className="w-10 h-10 border-2 rounded-full border-slate-300 border-t-slate-600 animate-spin mx-auto mb-4" />
          <p className="text-slate-500 font-serif italic">Loading your pipeline...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen w-full overflow-hidden bg-[#F5F5F0] text-slate-900 font-sans relative">
      {/* Mobile Header */}
      <div className="md:hidden fixed top-0 left-0 right-0 h-16 bg-[#F5F5F0] border-b border-slate-200/60 z-40 flex items-center justify-between px-4">
        <div className="flex items-center gap-2">
          <Logo className="h-10 w-10 shrink-0" />
          <span className="text-lg tracking-tight font-serif font-bold text-slate-900">
            Opportunity Radar
          </span>
        </div>
        <button
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          aria-label={isMobileMenuOpen ? 'Close navigation menu' : 'Open navigation menu'}
          className="p-2 -mr-2 text-slate-600 hover:text-slate-900 hover:bg-slate-200/50 rounded-lg transition-colors"
        >
          {isMobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
        </button>
      </div>

      {/* Desktop Sidebar */}
      <div className="hidden md:block">
        <Sidebar
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          onGmailSync={loadData}
          collapsed={isSidebarCollapsed}
          onToggleCollapsed={() => setIsSidebarCollapsed((current) => !current)}
        />
      </div>

      {/* Mobile Sidebar Overlay */}
      <AnimatePresence>
        {isMobileMenuOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setIsMobileMenuOpen(false)}
              className="fixed inset-0 bg-slate-900/20 backdrop-blur-sm z-40 md:hidden"
            />
            <motion.div
              initial={{ x: '-100%' }}
              animate={{ x: 0 }}
              exit={{ x: '-100%' }}
              transition={{ type: 'spring', bounce: 0, duration: 0.3 }}
              onClick={(event) => {
                const target = event.target as HTMLElement;
                if (target.closest('button,[role="button"]')) {
                  setIsMobileMenuOpen(false);
                }
              }}
              className="fixed inset-y-0 left-0 w-64 bg-[#F5F5F0] z-50 md:hidden shadow-2xl"
            >
              <Sidebar activeTab={activeTab} setActiveTab={handleMobileSetActiveTab} onGmailSync={loadData} />
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {!dockNotificationsInInbox ? (
        <div className={notificationClassName}>
          <NotificationCenter onNavigate={handleNotificationNavigate} />
        </div>
      ) : null}

      <main className="min-w-0 flex-1 flex overflow-hidden pt-16 md:pt-0">
        <div className="min-w-0 flex-1 flex flex-col overflow-hidden">
          {loadError && (
            <div className="px-4 md:px-6 pt-4 md:pt-5">
              <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <span>{loadError}</span>
                <button
                  onClick={() => {
                    setLoading(true);
                    loadData();
                  }}
                  className="px-3 py-2 rounded-xl bg-white border border-amber-200 text-amber-900 font-medium hover:bg-amber-100 transition-colors"
                >
                  Retry
                </button>
              </div>
            </div>
          )}
          <div className="min-w-0 flex-1 flex overflow-hidden">
              <Suspense fallback={<LazyFallback />}>
                {activeTab === 'dashboard' && <KanbanBoard jobs={jobs} setJobs={setJobs} focusRequest={dashboardFocusRequest} />}
                {activeTab === 'search' && <JobSearch jobs={jobs} setJobs={setJobs} />}
                {activeTab === 'radar' && <Radar focusRequest={radarFocusRequest} />}
                {activeTab === 'analytics' && <Analytics jobs={jobs} />}
              {activeTab === 'conversations' && (
                <Conversations
                  emails={emails}
                  jobs={jobs}
                  focusRequest={emailFocusRequest?.tab === 'conversations' ? emailFocusRequest : null}
                  onFeedbackSubmitted={loadData}
                />
              )}
              {activeTab === 'network' && <NetworkPage onOpenEmail={handleOpenEmail} onRefreshData={loadData} focusRequest={networkFocusRequest} />}
              {activeTab === 'calendar' && <Calendar focusRequest={calendarFocusRequest} />}
              {activeTab === 'profile' && <ProfilePage />}
              {activeTab === 'settings' && <Settings />}
              {activeTab === 'audit' && user?.is_admin && <ClassifierAudit />}
              {activeTab === 'extraction-reports' && user?.is_admin && <ExtractionReports />}
              {activeTab === 'source-intelligence' && user?.is_admin && <SourceIntelligenceAdmin />}
              {AI_OPS_ENABLED && activeTab === 'ai-ops' && user?.is_admin && <AiOps />}
              {activeTab === 'emails' && (
                <div className="flex-1 flex overflow-hidden">
                  <EmailFeed
                    emails={emails}
                    jobs={jobs}
                    isCollapsed={false}
                    setIsCollapsed={() => {}}
                    forceOpen={true}
                    onOpenAddJob={handleOpenAddJob}
                    onSuggestionAccepted={loadData}
                    focusRequest={emailFocusRequest?.tab === 'emails' ? emailFocusRequest : null}
                  />
                </div>
              )}
              {(!(activeTab in TAB_TITLES) || (ADMIN_TABS.has(activeTab) && !user?.is_admin)) && (
                <div className="flex flex-1 flex-col items-center justify-center gap-4 text-slate-500">
                  <p className="text-lg font-serif">Page not found</p>
                  <button
                    onClick={() => setActiveTab('dashboard')}
                    className="px-4 py-2 rounded-xl bg-slate-800 text-white text-sm font-medium hover:bg-slate-700 transition-colors"
                  >
                    Back to Dashboard
                  </button>
                </div>
              )}
            </Suspense>
          </div>
        </div>
      </main>

      {showInbox && (
        <div className="hidden lg:block">
          <EmailFeed
            emails={emails}
            jobs={jobs}
            isCollapsed={isInboxCollapsed}
            setIsCollapsed={setIsInboxCollapsed}
            onOpenAddJob={handleOpenAddJob}
            onNavigateToEmail={handleOpenEmail}
            onSuggestionAccepted={loadData}
            focusRequest={emailFocusRequest?.tab === 'emails' ? emailFocusRequest : null}
            headerAccessory={dockNotificationsInInbox ? <NotificationCenter onNavigate={handleNotificationNavigate} /> : undefined}
          />
        </div>
      )}

      <AnimatePresence>
        {showAddJobModal && (
          <AddJobModal
            isOpen={showAddJobModal}
            onClose={() => {
              setShowAddJobModal(false);
              setPendingJobDraft(null);
            }}
            onJobAdded={handleJobAdded}
            initialValues={pendingJobDraft}
          />
        )}
      </AnimatePresence>

      {COPILOT_ENABLED && user && (
        <CopilotLauncher onNavigate={handleNotificationNavigate} />
      )}
    </div>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </ErrorBoundary>
  );
}
