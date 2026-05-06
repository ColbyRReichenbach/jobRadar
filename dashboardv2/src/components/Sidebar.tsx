import { motion } from 'motion/react';
import { LayoutDashboard, Mail, Search, BarChart2, MessageSquare, LogOut, RefreshCw, Users, CalendarDays, Settings, FlaskConical, Bug, Radar as RadarIcon, BrainCircuit, PanelLeftClose, PanelLeftOpen, Network } from 'lucide-react';
import { cn } from '../lib/utils';
import { Logo } from './Logo';
import { useAuth } from '../lib/AuthContext';
import { syncGmail } from '../lib/api';
import { useState } from 'react';

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  onGmailSync?: () => void;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
}

const AI_OPS_ENABLED = import.meta.env.VITE_ADMIN_AI_OPS_ENABLED === 'true'
  || (import.meta.env.DEV && import.meta.env.VITE_ADMIN_AI_OPS_ENABLED !== 'false');

export function Sidebar({ activeTab, setActiveTab, onGmailSync, collapsed = false, onToggleCollapsed }: SidebarProps) {
  const { user, signIn, signOut, connectGmail } = useAuth();
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);

  const navItems = [
    { id: 'dashboard', label: 'Pipeline', icon: LayoutDashboard },
    { id: 'radar', label: 'Radar', icon: RadarIcon },
    { id: 'emails', label: 'Inbox', icon: Mail },
    { id: 'conversations', label: 'Conversations', icon: MessageSquare },
    { id: 'network', label: 'Network', icon: Users },
    { id: 'calendar', label: 'Calendar', icon: CalendarDays },
    { id: 'search', label: 'Job Search', icon: Search },
    { id: 'analytics', label: 'Analytics', icon: BarChart2 },
    { id: 'audit', label: 'Classifier Audit', icon: FlaskConical, adminOnly: true },
    { id: 'extraction-reports', label: 'Extraction Reports', icon: Bug, adminOnly: true },
    { id: 'source-intelligence', label: 'Source Intelligence', icon: Network, adminOnly: true },
    ...(AI_OPS_ENABLED ? [{ id: 'ai-ops', label: 'AI Ops', icon: BrainCircuit, adminOnly: true }] : []),
    { id: 'settings', label: 'Settings', icon: Settings },
  ];
  const visibleNavItems = navItems.filter((item) => !item.adminOnly || user?.is_admin);

  const handleSyncGmail = async () => {
    setSyncing(true);
    setSyncError(null);
    setSyncMessage(null);
    try {
      const result = await syncGmail();
      onGmailSync?.();
      const checkedCount = result.stats?.fetched ?? result.total_found;
      const durationMs = result.duration_ms ?? result.stats?.duration_ms;
      const durationText = durationMs ? ` in ${(durationMs / 1000).toFixed(1)}s` : '';
      const modeText = result.query_mode === 'incremental' ? ' incrementally' : '';
      setSyncMessage(
        result.new_emails > 0
          ? `Synced${modeText} ${result.new_emails} new emails from ${checkedCount} checked${durationText}.`
          : `Gmail sync checked${modeText} ${checkedCount} emails with no new matches${durationText}.`
      );
    } catch (err) {
      setSyncError(err instanceof Error ? err.message : 'Gmail sync failed.');
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div
      className={cn(
        'relative h-screen flex flex-col shrink-0 bg-[#F5F5F0] border-r border-slate-200/60 transition-[width,padding] duration-300',
        collapsed ? 'w-20 p-3' : 'w-64 p-4'
      )}
    >
      {onToggleCollapsed ? (
        <button
          type="button"
          onClick={onToggleCollapsed}
          aria-label={collapsed ? 'Expand navigation sidebar' : 'Collapse navigation sidebar'}
          title={collapsed ? 'Expand navigation' : 'Collapse navigation'}
          className="absolute -right-3 top-6 z-20 flex h-6 w-6 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-500 shadow-sm transition-colors hover:bg-slate-50 hover:text-slate-900"
        >
          {collapsed ? <PanelLeftOpen className="h-3.5 w-3.5" /> : <PanelLeftClose className="h-3.5 w-3.5" />}
        </button>
      ) : null}

      <motion.div
        className={cn(
          'flex items-center mb-8 mt-2 cursor-pointer',
          collapsed ? 'justify-center px-0' : 'gap-2 px-2'
        )}
        initial="initial"
        animate="animate"
        whileHover="hover"
        onClick={() => setActiveTab('dashboard')}
        title={collapsed ? 'Opportunity Radar' : undefined}
      >
        <Logo className={cn('shrink-0', collapsed ? 'h-10 w-10' : 'h-9 w-9')} />
        <span className={cn('text-lg tracking-tight font-serif font-bold text-slate-900', collapsed && 'sr-only')}>
          Opportunity Radar
        </span>
      </motion.div>

      <nav className="flex-1 flex flex-col gap-1">
        {visibleNavItems.map((item) => {
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              title={collapsed ? item.label : undefined}
              className={cn(
                "relative flex items-center text-sm transition-all rounded-xl font-medium",
                collapsed ? 'justify-center px-0 py-3' : 'gap-3 px-3 py-2.5',
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
                "relative z-10",
                collapsed ? 'h-5 w-5' : 'h-4 w-4',
                isActive ? "text-slate-800" : "text-slate-400"
              )} />
              <span className={cn('relative z-10', collapsed && 'sr-only')}>{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="mt-auto pt-4 border-t border-slate-200/60 space-y-3">
        {!user ? (
          /* Sign in button when not authenticated */
          <button
            onClick={() => signIn()}
            title={collapsed ? 'Sign in with Google' : undefined}
            className={cn(
              'w-full flex items-center justify-center bg-white border border-slate-200 rounded-xl font-medium text-sm text-slate-700 hover:bg-slate-50 transition-colors shadow-sm',
              collapsed ? 'px-0 py-3' : 'gap-3 px-3 py-2.5'
            )}
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/>
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
            </svg>
            <span className={collapsed ? 'sr-only' : undefined}>Sign in with Google</span>
          </button>
        ) : (
          <>
            {/* Gmail connect / sync */}
            {!user.gmail_connected ? (
              <button
                onClick={connectGmail}
                title={collapsed ? 'Connect Gmail' : undefined}
                className={cn(
                  'w-full flex items-center justify-center text-xs font-medium text-indigo-600 bg-indigo-50 rounded-xl hover:bg-indigo-100 transition-colors',
                  collapsed ? 'px-0 py-3' : 'gap-2 px-3 py-2'
                )}
              >
                <Mail className="w-3.5 h-3.5" />
                <span className={collapsed ? 'sr-only' : undefined}>Connect Gmail</span>
              </button>
            ) : (
              <div className="space-y-2">
                <button
                  onClick={handleSyncGmail}
                  disabled={syncing}
                  title={collapsed ? (syncing ? 'Syncing Gmail' : 'Sync Gmail') : undefined}
                  className={cn(
                    'w-full flex items-center justify-center text-xs font-medium text-slate-600 bg-slate-100 rounded-xl hover:bg-slate-200 transition-colors disabled:opacity-50',
                    collapsed ? 'px-0 py-3' : 'gap-2 px-3 py-2'
                  )}
                >
                  <RefreshCw className={cn("w-3.5 h-3.5", syncing && "animate-spin")} />
                  <span className={collapsed ? 'sr-only' : undefined}>{syncing ? 'Syncing...' : 'Sync Gmail'}</span>
                </button>
                {(syncError || syncMessage) && !collapsed && (
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
            <div
              className={cn(
                'flex items-center rounded-2xl bg-white border border-slate-200/60 shadow-sm cursor-pointer hover:border-slate-300 transition-colors',
                collapsed ? 'justify-center px-2 py-3' : 'gap-3 px-3 py-3'
              )}
              onClick={() => setActiveTab('profile')}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  setActiveTab('profile');
                }
              }}
              role="button"
              tabIndex={0}
              title={collapsed ? (user.name || user.email || 'Profile') : undefined}
            >
              {user.picture ? (
                <img src={user.picture} alt={user.name || 'User'} className="w-8 h-8 rounded-full border border-slate-200" referrerPolicy="no-referrer" />
              ) : (
                <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center text-sm font-bold text-slate-500">
                  {(user.name || user.email || '?')[0].toUpperCase()}
                </div>
              )}
              <div className={cn('flex flex-col text-left min-w-0 flex-1', collapsed && 'sr-only')}>
                <span className="text-sm font-serif font-bold text-slate-900 truncate">{user.name || 'User'}</span>
                <span className="text-xs font-serif italic text-slate-500 truncate">{user.email}</span>
              </div>
              {!collapsed ? (
                <button
                  onClick={(event) => {
                    event.stopPropagation();
                    signOut();
                  }}
                  aria-label="Sign out"
                  className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-200/50 rounded-lg transition-colors shrink-0"
                  title="Sign out"
                >
                  <LogOut className="w-3.5 h-3.5" />
                </button>
              ) : null}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
