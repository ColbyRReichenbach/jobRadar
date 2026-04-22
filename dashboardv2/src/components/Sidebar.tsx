import { motion } from 'motion/react';
import { LayoutDashboard, Mail, Search, Download, BarChart2, MessageSquare, LogOut, RefreshCw, Users, CalendarDays, Settings, Radar } from 'lucide-react';
import { cn } from '../lib/utils';
import { Logo } from './Logo';
import { useAuth } from '../lib/AuthContext';
import { syncGmail } from '../lib/api';
import { useState } from 'react';

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  onGmailSync?: () => void;
}

export function Sidebar({ activeTab, setActiveTab, onGmailSync }: SidebarProps) {
  const { user, signIn, signOut, connectGmail } = useAuth();
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);

  const navItems = [
    { id: 'dashboard', label: 'Pipeline', icon: LayoutDashboard },
    { id: 'radar', label: 'Radar', icon: Radar },
    { id: 'emails', label: 'Inbox', icon: Mail },
    { id: 'conversations', label: 'Conversations', icon: MessageSquare },
    { id: 'network', label: 'Network', icon: Users },
    { id: 'calendar', label: 'Calendar', icon: CalendarDays },
    { id: 'search', label: 'Job Search', icon: Search },
    { id: 'analytics', label: 'Analytics', icon: BarChart2 },
    { id: 'export', label: 'Export Data', icon: Download },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

  const handleSyncGmail = async () => {
    setSyncing(true);
    setSyncError(null);
    setSyncMessage(null);
    try {
      const result = await syncGmail();
      onGmailSync?.();
      setSyncMessage(
        result.new_emails > 0
          ? `Synced ${result.new_emails} new emails from Gmail.`
          : 'Gmail sync finished with no new emails.'
      );
    } catch (err) {
      setSyncError(err instanceof Error ? err.message : 'Gmail sync failed.');
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="w-64 h-screen flex flex-col p-4 shrink-0 bg-[#F5F5F0] border-r border-slate-200/60">
      <motion.div
        className="flex items-center gap-2 px-2 mb-8 mt-2 cursor-pointer"
        initial="initial"
        animate="animate"
        whileHover="hover"
        onClick={() => setActiveTab('dashboard')}
      >
        <div className="w-8 h-8 flex items-center justify-center bg-slate-800 rounded-xl shadow-sm">
          <Logo className="w-5 h-5 text-white" />
        </div>
        <span className="text-lg tracking-tight font-serif font-bold text-slate-900">
          AppTrail
        </span>
      </motion.div>

      <nav className="flex-1 flex flex-col gap-1">
        {navItems.map((item) => {
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={cn(
                "relative flex items-center gap-3 px-3 py-2.5 text-sm transition-all rounded-xl font-medium",
                isActive ? "text-slate-900" : "text-slate-500 hover:text-slate-900 hover:bg-slate-200/50"
              )}
            >
              {isActive && (
                <motion.div
                  layoutId="active-nav-vision"
                  className="absolute inset-0 bg-white shadow-sm rounded-xl border border-slate-200/60"
                  initial={false}
                  transition={{ type: "spring", stiffness: 300, damping: 30 }}
                />
              )}
              <item.icon className={cn(
                "w-4 h-4 relative z-10",
                isActive ? "text-slate-800" : "text-slate-400"
              )} />
              <span className="relative z-10">{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="mt-auto pt-4 border-t border-slate-200/60 space-y-3">
        {!user ? (
          /* Sign in button when not authenticated */
          <button
            onClick={signIn}
            className="w-full flex items-center justify-center gap-3 px-3 py-2.5 bg-white border border-slate-200 rounded-xl font-medium text-sm text-slate-700 hover:bg-slate-50 transition-colors shadow-sm"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/>
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
            </svg>
            Sign in with Google
          </button>
        ) : (
          <>
            {/* Gmail connect / sync */}
            {!user.gmail_connected ? (
              <button
                onClick={connectGmail}
                className="w-full flex items-center justify-center gap-2 px-3 py-2 text-xs font-medium text-indigo-600 bg-indigo-50 rounded-xl hover:bg-indigo-100 transition-colors"
              >
                <Mail className="w-3.5 h-3.5" />
                Connect Gmail
              </button>
            ) : (
              <div className="space-y-2">
                <button
                  onClick={handleSyncGmail}
                  disabled={syncing}
                  className="w-full flex items-center justify-center gap-2 px-3 py-2 text-xs font-medium text-slate-600 bg-slate-100 rounded-xl hover:bg-slate-200 transition-colors disabled:opacity-50"
                >
                  <RefreshCw className={cn("w-3.5 h-3.5", syncing && "animate-spin")} />
                  {syncing ? 'Syncing...' : 'Sync Gmail'}
                </button>
                {(syncError || syncMessage) && (
                  <div
                    className={cn(
                      'rounded-xl border px-3 py-2 text-[11px] leading-5',
                      syncError
                        ? 'border-red-200 bg-red-50 text-red-800'
                        : 'border-emerald-200 bg-emerald-50 text-emerald-800'
                    )}
                  >
                    {syncError || syncMessage}
                  </div>
                )}
              </div>
            )}

            {/* User profile */}
            <div className="flex items-center gap-3 rounded-2xl bg-white px-3 py-3 border border-slate-200/60 shadow-sm">
              {user.picture ? (
                <img src={user.picture} alt={user.name || 'User'} className="w-8 h-8 rounded-full border border-slate-200" referrerPolicy="no-referrer" />
              ) : (
                <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center text-sm font-bold text-slate-500">
                  {(user.name || user.email || '?')[0].toUpperCase()}
                </div>
              )}
              <div className="flex flex-col text-left min-w-0 flex-1">
                <span className="text-sm font-serif font-bold text-slate-900 truncate">{user.name || 'User'}</span>
                <span className="text-xs font-serif italic text-slate-500 truncate">{user.email}</span>
              </div>
              <button
                onClick={signOut}
                aria-label="Sign out"
                className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-200/50 rounded-lg transition-colors shrink-0"
                title="Sign out"
              >
                <LogOut className="w-3.5 h-3.5" />
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
