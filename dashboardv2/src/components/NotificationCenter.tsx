import { useEffect, useMemo, useState } from 'react';
import { Bell, Briefcase, Mail, MessageSquare, UserPlus, X } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { cn } from '../lib/utils';
import { AlertItem, fetchAlerts, getUnreadAlertCount, markAlertRead } from '../lib/api';

interface NotificationCenterProps {
  onNavigate: (actionUrl: string | null) => void;
}

function alertMeta(alertType: string) {
  switch (alertType) {
    case 'conversation_message':
      return {
        label: 'Conversation',
        icon: MessageSquare,
        tone: 'bg-violet-50 text-violet-700 border-violet-200',
      };
    case 'network_contact':
      return {
        label: 'Network',
        icon: UserPlus,
        tone: 'bg-emerald-50 text-emerald-700 border-emerald-200',
      };
    case 'interview_request':
    case 'offer':
    case 'rejection':
    case 'action_item':
    case 'job_update':
    case 'email_update':
      return {
        label: 'Update',
        icon: Mail,
        tone: 'bg-blue-50 text-blue-700 border-blue-200',
      };
    case 'follow_up':
      return {
        label: 'Pipeline',
        icon: Briefcase,
        tone: 'bg-amber-50 text-amber-700 border-amber-200',
      };
    case 'dead_listing':
      return {
        label: 'Listing',
        icon: Briefcase,
        tone: 'bg-rose-50 text-rose-700 border-rose-200',
      };
    case 'weekly_digest':
      return {
        label: 'Digest',
        icon: Briefcase,
        tone: 'bg-amber-50 text-amber-700 border-amber-200',
      };
    default:
      return {
        label: 'Alert',
        icon: Bell,
        tone: 'bg-slate-100 text-slate-700 border-slate-200',
      };
  }
}

export function NotificationCenter({ onNavigate }: NotificationCenterProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const loadAlerts = async () => {
    try {
      const [items, unread] = await Promise.all([
        fetchAlerts(),
        getUnreadAlertCount(),
      ]);
      setAlerts(items);
      setUnreadCount(unread);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load notifications.');
    }
  };

  useEffect(() => {
    void loadAlerts();
    const interval = window.setInterval(() => {
      void loadAlerts();
    }, 30000);
    return () => window.clearInterval(interval);
  }, []);

  const unreadAlerts = useMemo(() => alerts.filter((alert) => !alert.read).length, [alerts]);

  const handleOpen = async () => {
    setIsOpen((prev) => !prev);
    if (!isOpen) {
      await loadAlerts();
    }
  };

  const handleSelectAlert = async (alert: AlertItem) => {
    if (!alert.read) {
      try {
        await markAlertRead(alert.id);
        setAlerts((prev) => prev.map((item) => (item.id === alert.id ? { ...item, read: true } : item)));
        setUnreadCount((prev) => Math.max(0, prev - 1));
      } catch {
        // Navigation still matters more than marking read.
      }
    }
    setIsOpen(false);
    onNavigate(alert.action_url);
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => void handleOpen()}
        className="relative inline-flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-600 shadow-sm hover:bg-slate-50"
        aria-label="Open notifications"
      >
        <Bell className="w-4 h-4" />
        {(unreadCount > 0 || unreadAlerts > 0) && (
          <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-red-500 text-white text-[10px] font-semibold flex items-center justify-center">
            {Math.min(unreadCount || unreadAlerts, 99)}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-3 w-[360px] max-w-[calc(100vw-2rem)] rounded-3xl border border-slate-200 bg-white shadow-2xl overflow-hidden z-50">
          <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 bg-slate-50/70">
            <div>
              <h3 className="text-base font-semibold text-slate-900">Notifications</h3>
              <p className="text-xs text-slate-500">{unreadAlerts} unread</p>
            </div>
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-200"
              aria-label="Close notifications"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="max-h-[70vh] overflow-y-auto">
            {error && (
              <div className="px-5 py-4 text-sm text-red-700 bg-red-50 border-b border-red-100">{error}</div>
            )}

            {!alerts.length ? (
              <div className="px-6 py-12 text-center">
                <div className="mx-auto mb-3 h-12 w-12 rounded-2xl bg-slate-100 flex items-center justify-center">
                  <Bell className="w-6 h-6 text-slate-300" />
                </div>
                <p className="text-sm font-medium text-slate-700">No notifications yet</p>
                <p className="text-xs text-slate-500 mt-1">New alerts will show up here across the app.</p>
              </div>
            ) : (
              <div className="p-3 space-y-2">
                {alerts.map((alert) => {
                  const meta = alertMeta(alert.alert_type);
                  const Icon = meta.icon;
                  return (
                    <button
                      key={alert.id}
                      type="button"
                      onClick={() => void handleSelectAlert(alert)}
                      className={cn(
                        'w-full text-left rounded-2xl border px-4 py-3 transition-colors',
                        alert.read ? 'bg-slate-50 border-slate-100 opacity-80' : 'bg-white border-slate-200 hover:bg-slate-50',
                      )}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex items-start gap-3 min-w-0">
                          <div className={cn('mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border', meta.tone)}>
                            <Icon className="w-4 h-4" />
                          </div>
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-semibold text-slate-900 truncate">{alert.title}</span>
                              {!alert.read && <span className="h-2 w-2 rounded-full bg-red-500 shrink-0" />}
                            </div>
                            {alert.body && (
                              <p className="mt-1 text-xs text-slate-500 line-clamp-2 [overflow-wrap:anywhere]">
                                {alert.body}
                              </p>
                            )}
                            <div className="mt-2 flex items-center gap-2">
                              <span className={cn('inline-flex items-center rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider', meta.tone)}>
                                {meta.label}
                              </span>
                              {alert.created_at && (
                                <span className="text-[11px] text-slate-400">
                                  {formatDistanceToNow(new Date(alert.created_at), { addSuffix: true })}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
