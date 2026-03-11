import { useState, useEffect, useCallback } from 'react';
import { Sidebar } from './components/Sidebar';
import { KanbanBoard } from './components/KanbanBoard';
import { EmailFeed } from './components/EmailFeed';
import { JobSearch } from './components/JobSearch';
import { ExportData } from './components/ExportData';
import { Analytics } from './components/Analytics';
import { Conversations } from './components/Conversations';
import { NetworkPage } from './components/NetworkPage';
import { Calendar } from './components/Calendar';
import { Settings } from './components/Settings';
import { LoginPage } from './components/LoginPage';
import { ErrorBoundary } from './components/ErrorBoundary';
import { initialJobs, initialEmails } from './data/mockData';
import { Job, Email } from './types';
import { Menu, X } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { fetchJobs, fetchEmails } from './lib/api';
import { AuthProvider, useAuth } from './lib/AuthContext';

const USE_API = true;

function AppContent() {
  const { user, loading: authLoading } = useAuth();
  const [activeTab, setActiveTab] = useState('dashboard');
  const [jobs, setJobs] = useState<Job[]>(USE_API ? [] : initialJobs);
  const [emails, setEmails] = useState<Email[]>(USE_API ? [] : initialEmails);
  const [isInboxCollapsed, setIsInboxCollapsed] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [loading, setLoading] = useState(USE_API);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [emailFocusRequest, setEmailFocusRequest] = useState<{
    emailId: string;
    threadId?: string;
    tab: 'emails' | 'conversations';
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

  // Close mobile menu when tab changes
  useEffect(() => {
    setIsMobileMenuOpen(false);
  }, [activeTab]);

  if (!authLoading && !user) {
    return <LoginPage />;
  }

  const showInbox = activeTab !== 'emails' && activeTab !== 'conversations';

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
          <div className="w-8 h-8 flex items-center justify-center bg-slate-800 rounded-xl shadow-sm">
            <svg className="w-5 h-5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"></path><line x1="4" y1="22" x2="4" y2="15"></line></svg>
          </div>
          <span className="text-lg tracking-tight font-serif font-bold text-slate-900">
            AppTrail
          </span>
        </div>
        <button
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          className="p-2 -mr-2 text-slate-600 hover:text-slate-900 hover:bg-slate-200/50 rounded-lg transition-colors"
        >
          {isMobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
        </button>
      </div>

      {/* Desktop Sidebar */}
      <div className="hidden md:block">
        <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} onGmailSync={loadData} />
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
              className="fixed inset-y-0 left-0 w-64 bg-[#F5F5F0] z-50 md:hidden shadow-2xl"
            >
              <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} onGmailSync={loadData} />
            </motion.div>
          </>
        )}
      </AnimatePresence>

      <main className="flex-1 flex overflow-hidden pt-16 md:pt-0">
        <div className="flex-1 flex flex-col overflow-hidden">
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
          <div className="flex-1 flex overflow-hidden">
            {activeTab === 'dashboard' && <KanbanBoard jobs={jobs} setJobs={setJobs} />}
            {activeTab === 'search' && <JobSearch jobs={jobs} setJobs={setJobs} />}
            {activeTab === 'analytics' && <Analytics jobs={jobs} />}
            {activeTab === 'export' && <ExportData />}
            {activeTab === 'conversations' && <Conversations emails={emails} jobs={jobs} focusRequest={emailFocusRequest?.tab === 'conversations' ? emailFocusRequest : null} />}
            {activeTab === 'network' && <NetworkPage onOpenEmail={handleOpenEmail} onRefreshData={loadData} />}
            {activeTab === 'calendar' && <Calendar />}
            {activeTab === 'settings' && <Settings />}
            {activeTab === 'emails' && (
              <div className="flex-1 flex overflow-hidden">
                <EmailFeed emails={emails} jobs={jobs} isCollapsed={false} setIsCollapsed={() => {}} forceOpen={true} focusRequest={emailFocusRequest?.tab === 'emails' ? emailFocusRequest : null} />
              </div>
            )}
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
            focusRequest={emailFocusRequest?.tab === 'emails' ? emailFocusRequest : null}
          />
        </div>
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
