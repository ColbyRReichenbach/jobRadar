import { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { Bell, Mail, Save, Loader2, KeyRound, Copy, RefreshCw, Chrome, ExternalLink, Shield, Download, Trash2, Brain, Users, Globe, Link2 } from 'lucide-react';
import {
  ApiKeyStatus,
  ConsentStatus,
  GmailSyncAuditRow,
  NotificationPrefs,
  deleteSourcePrivateLink,
  fetchApiKeyStatus,
  fetchConsent,
  fetchGmailSyncAudit,
  fetchNotificationPreferences,
  fetchSourcePrivateLinks,
  generateApiKey,
  updateConsent,
  updateNotificationPreferences,
  deleteAccount,
  exportCsv,
  exportAccountData,
} from '../lib/api';
import type { SourcePrivateLink } from '../lib/api';
import { useAuth } from '../lib/AuthContext';
import { DEFAULT_LOCAL_NOTIFICATION_PREFS, LocalNotificationPrefs, loadLocalNotificationPrefs, saveLocalNotificationPrefs } from '../lib/localNotificationPrefs';

function formatSyncReason(reason: string) {
  return reason
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function decisionClassName(decision: string) {
  if (decision === 'stored') return 'bg-emerald-50 text-emerald-700 border-emerald-200';
  if (decision === 'filtered') return 'bg-amber-50 text-amber-700 border-amber-200';
  return 'bg-slate-50 text-slate-600 border-slate-200';
}

export function Settings() {
  const [prefs, setPrefs] = useState<NotificationPrefs>({
    sms_enabled: false,
    sms_phone: null,
    weekly_digest_enabled: false,
    radar_updates_enabled: true,
    inbox_updates_enabled: true,
    conversations_enabled: true,
    network_enabled: true,
    interviews_enabled: true,
    followups_enabled: true,
    listings_enabled: true,
    browser_notifications_enabled: false,
    quiet_hours_enabled: false,
    quiet_hours_start: null,
    quiet_hours_end: null,
  });
  const [localPrefs, setLocalPrefs] = useState<LocalNotificationPrefs>(DEFAULT_LOCAL_NOTIFICATION_PREFS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [phone, setPhone] = useState('');
  const [apiKeyStatus, setApiKeyStatus] = useState<ApiKeyStatus | null>(null);
  const [newApiKey, setNewApiKey] = useState('');
  const [copySaved, setCopySaved] = useState(false);
  const [generatingKey, setGeneratingKey] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [consent, setConsent] = useState<ConsentStatus | null>(null);
  const [savingConsent, setSavingConsent] = useState(false);
  const [exportingAccount, setExportingAccount] = useState(false);
  const [exportingCsv, setExportingCsv] = useState(false);
  const [gmailAuditRows, setGmailAuditRows] = useState<GmailSyncAuditRow[]>([]);
  const [sourcePrivateLinks, setSourcePrivateLinks] = useState<SourcePrivateLink[]>([]);
  const [deletingPrivateLinkId, setDeletingPrivateLinkId] = useState<string | null>(null);
  const [showAllGmailDiagnostics, setShowAllGmailDiagnostics] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteInput, setDeleteInput] = useState('');
  const [deleting, setDeleting] = useState(false);
  const { signOut } = useAuth();

  useEffect(() => {
    loadPrefs();
  }, []);

  useEffect(() => {
    if (loading) return;
    saveLocalNotificationPrefs(localPrefs);
  }, [localPrefs, loading]);

  const loadPrefs = async () => {
    setErrorMessage(null);
    try {
      const [prefsData, keyStatus, consentData, privateLinks] = await Promise.all([
        fetchNotificationPreferences(),
        fetchApiKeyStatus(),
        fetchConsent(),
        fetchSourcePrivateLinks().catch(() => []),
      ]);
      const auditRows = await fetchGmailSyncAudit(25).catch(() => []);
      setPrefs(prefsData);
      setLocalPrefs(loadLocalNotificationPrefs());
      setPhone(prefsData.sms_phone || '');
      setApiKeyStatus(keyStatus);
      setConsent(consentData);
      setSourcePrivateLinks(privateLinks);
      setGmailAuditRows(auditRows);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to load settings.');
    } finally {
      setLoading(false);
    }
  };

  const savePrefs = async () => {
    setSaving(true);
    setSaved(false);
    setErrorMessage(null);
    setStatusMessage(null);
    try {
      let browserNotificationsEnabled = localPrefs.browser_notifications_enabled;
      if (
        localPrefs.browser_notifications_enabled &&
        typeof window !== 'undefined' &&
        'Notification' in window &&
        Notification.permission !== 'granted'
      ) {
        const permission = await Notification.requestPermission();
        browserNotificationsEnabled = permission === 'granted';
        if (permission !== 'granted') {
          setStatusMessage('Browser notifications were not granted. In-app notifications will still work.');
        }
      }
      const data = await updateNotificationPreferences({
        sms_enabled: prefs.sms_enabled,
        sms_phone: phone || null,
        weekly_digest_enabled: prefs.weekly_digest_enabled,
        radar_updates_enabled: prefs.radar_updates_enabled,
        inbox_updates_enabled: prefs.inbox_updates_enabled,
        conversations_enabled: prefs.conversations_enabled,
        network_enabled: prefs.network_enabled,
        interviews_enabled: prefs.interviews_enabled,
        followups_enabled: prefs.followups_enabled,
        listings_enabled: prefs.listings_enabled,
      });
      const nextLocalPrefs = {
        ...localPrefs,
        browser_notifications_enabled: browserNotificationsEnabled,
      };
      setLocalPrefs(nextLocalPrefs);
      setPrefs((current) => ({
        ...data,
        browser_notifications_enabled: nextLocalPrefs.browser_notifications_enabled,
        quiet_hours_enabled: nextLocalPrefs.quiet_hours_enabled,
        quiet_hours_start: nextLocalPrefs.quiet_hours_start,
        quiet_hours_end: nextLocalPrefs.quiet_hours_end,
      }));
      setSaved(true);
      setStatusMessage((current) => current || 'Preferences saved.');
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to save preferences.');
    } finally {
      setSaving(false);
    }
  };

  const handleDeletePrivateLink = async (id: string) => {
    setDeletingPrivateLinkId(id);
    setErrorMessage(null);
    try {
      await deleteSourcePrivateLink(id);
      setSourcePrivateLinks((current) => current.filter((link) => link.id !== id));
      setStatusMessage('Private link deleted.');
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to delete private link.');
    } finally {
      setDeletingPrivateLinkId(null);
    }
  };

  const togglePref = (
    key:
      | 'inbox_updates_enabled'
      | 'radar_updates_enabled'
      | 'conversations_enabled'
      | 'network_enabled'
      | 'interviews_enabled'
      | 'followups_enabled'
      | 'listings_enabled'
  ) => {
    setPrefs((current) => ({ ...current, [key]: !current[key] }));
  };

  const toggleLocalPref = (
    key: 'browser_notifications_enabled' | 'quiet_hours_enabled'
  ) => {
    setLocalPrefs((current) => ({ ...current, [key]: !current[key] }));
  };

  const visibleGmailAuditRows = showAllGmailDiagnostics ? gmailAuditRows : gmailAuditRows.slice(0, 3);

  const createNewApiKey = async () => {
    setGeneratingKey(true);
    setCopySaved(false);
    setErrorMessage(null);
    setStatusMessage(null);
    try {
      const data = await generateApiKey();
      setNewApiKey(data.api_key);
      setApiKeyStatus({
        has_api_key: true,
        last4: data.last4,
        created_at: data.created_at,
        last_used_at: null,
      });
      setStatusMessage('New API key generated. Copy it now; it will only be shown once.');
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to generate API key.');
    } finally {
      setGeneratingKey(false);
    }
  };

  const copyApiKey = async () => {
    if (!newApiKey) return;
    try {
      await navigator.clipboard.writeText(newApiKey);
      setCopySaved(true);
      setStatusMessage('API key copied to clipboard.');
      setTimeout(() => setCopySaved(false), 2500);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to copy API key.');
    }
  };

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-auto p-8">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-2xl font-serif font-bold text-slate-900 mb-1">Settings</h1>
        <p className="text-sm text-slate-500 mb-8">Manage notifications, browser alerts, and account tools.</p>

        {(errorMessage || statusMessage) && (
          <div className={`mb-6 rounded-2xl border px-4 py-3 text-sm ${
            errorMessage ? 'border-red-200 bg-red-50 text-red-800' : 'border-emerald-200 bg-emerald-50 text-emerald-800'
          }`}>
            {errorMessage || statusMessage}
          </div>
        )}

        <div className="space-y-6">
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.025 }}
            className="bg-white rounded-2xl border border-slate-200/60 p-6 shadow-sm"
          >
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-amber-50 flex items-center justify-center">
                <Bell className="w-5 h-5 text-amber-600" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-slate-900">Notification Center</h2>
                <p className="text-xs text-slate-500">Choose which events create persistent alerts</p>
              </div>
            </div>

            <div className="space-y-4">
              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  id="browser-notifications-toggle"
                  aria-label="Browser banner notifications"
                  type="checkbox"
                  checked={localPrefs.browser_notifications_enabled}
                  onChange={() => toggleLocalPref('browser_notifications_enabled')}
                  className="mt-0.5 w-4 h-4 rounded border-slate-300 text-amber-600 focus:ring-amber-500"
                />
                <span className="text-sm text-slate-700">
                  <span className="block font-medium text-slate-900">Browser banner notifications</span>
                  Show system-style notifications on this device when AppTrail is open in a background tab or installed web app.
                </span>
              </label>

              <div className="grid gap-3 md:grid-cols-2">
                {[
                  ['inbox_updates_enabled', 'Inbox updates', 'Interview, offer, rejection, and status updates'],
                  ['radar_updates_enabled', 'Radar reports', 'New Radar signals, research reports, and report-ready alerts'],
                  ['conversations_enabled', 'Conversations', 'New recruiter or hiring-team threads that need attention'],
                  ['network_enabled', 'Network', 'New real-person contacts added from conversations'],
                  ['interviews_enabled', 'Interviews', 'Calendar interview sync events and changes'],
                  ['followups_enabled', 'Follow-ups', 'Applications that have gone quiet and need action'],
                  ['listings_enabled', 'Dead listings', 'Jobs that appear to have closed or expired'],
                ].map(([key, label, description]) => (
                  <label key={key} className="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={prefs[key as keyof NotificationPrefs] as boolean}
                      onChange={() => togglePref(key as Parameters<typeof togglePref>[0])}
                      className="mt-0.5 w-4 h-4 rounded border-slate-300 text-amber-600 focus:ring-amber-500"
                    />
                    <span className="text-sm text-slate-700">
                      <span className="block font-medium text-slate-900">{label}</span>
                      {description}
                    </span>
                  </label>
                ))}
              </div>

              <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-4">
                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    id="quiet-hours-toggle"
                    aria-label="Quiet hours"
                    type="checkbox"
                    checked={localPrefs.quiet_hours_enabled}
                    onChange={() => toggleLocalPref('quiet_hours_enabled')}
                    className="mt-0.5 w-4 h-4 rounded border-slate-300 text-amber-600 focus:ring-amber-500"
                  />
                  <span className="text-sm text-slate-700">
                    <span className="block font-medium text-slate-900">Quiet hours</span>
                    Suppress toast/browser banners on this device during the hours below while still storing alerts in AppTrail.
                  </span>
                </label>
                {localPrefs.quiet_hours_enabled && (
                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    <label className="space-y-1">
                      <span className="text-xs font-medium uppercase tracking-[0.18em] text-slate-400">Start</span>
                      <select
                        id="quiet-hours-start"
                        value={localPrefs.quiet_hours_start ?? 22}
                        onChange={(event) => setLocalPrefs((current) => ({ ...current, quiet_hours_start: Number(event.target.value) }))}
                        className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"
                      >
                        {Array.from({ length: 24 }, (_, hour) => (
                          <option key={hour} value={hour}>{hour.toString().padStart(2, '0')}:00</option>
                        ))}
                      </select>
                    </label>
                    <label className="space-y-1">
                      <span className="text-xs font-medium uppercase tracking-[0.18em] text-slate-400">End</span>
                      <select
                        id="quiet-hours-end"
                        value={localPrefs.quiet_hours_end ?? 7}
                        onChange={(event) => setLocalPrefs((current) => ({ ...current, quiet_hours_end: Number(event.target.value) }))}
                        className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"
                      >
                        {Array.from({ length: 24 }, (_, hour) => (
                          <option key={hour} value={hour}>{hour.toString().padStart(2, '0')}:00</option>
                        ))}
                      </select>
                    </label>
                  </div>
                )}
              </div>
            </div>
          </motion.div>

          {/* Weekly Digest */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
            className="bg-white rounded-2xl border border-slate-200/60 p-6 shadow-sm"
          >
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-emerald-50 flex items-center justify-center">
                <Mail className="w-5 h-5 text-emerald-600" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-slate-900">Weekly Digest</h2>
                <p className="text-xs text-slate-500">Summary of your job search activity</p>
              </div>
            </div>

            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={prefs.weekly_digest_enabled}
                onChange={(e) => setPrefs({ ...prefs, weekly_digest_enabled: e.target.checked })}
                className="w-4 h-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
              />
              <span className="text-sm text-slate-700">
                Receive a weekly summary of applications, interviews, and follow-ups
              </span>
            </label>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.075 }}
            className="bg-white rounded-2xl border border-slate-200/60 p-6 shadow-sm"
          >
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center">
                <RefreshCw className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-slate-900">Gmail Sync Diagnostics</h2>
                <p className="text-xs text-slate-500">Recent messages checked during Gmail sync</p>
              </div>
            </div>

            {gmailAuditRows.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-200 px-4 py-3 text-sm text-slate-500">
                Sync decisions will appear here after the next Gmail sync.
              </div>
            ) : (
              <div className="overflow-x-auto rounded-xl border border-slate-200">
                <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
                  <thead className="bg-slate-50 text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                    <tr>
                      <th className="px-4 py-3">Message</th>
                      <th className="px-4 py-3">Decision</th>
                      <th className="px-4 py-3">Reason</th>
                      <th className="px-4 py-3">When</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 bg-white">
                    {visibleGmailAuditRows.map((row) => (
                      <tr key={row.id}>
                        <td className="max-w-[24rem] px-4 py-3">
                          <div className="font-medium text-slate-900 truncate">
                            {row.subject || '(no subject)'}
                          </div>
                          <div className="text-xs text-slate-500 truncate">
                            {[row.sender, row.sender_email || row.sender_domain].filter(Boolean).join(' • ') || 'Gmail message'}
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`inline-flex rounded-full border px-2 py-1 text-xs font-semibold capitalize ${decisionClassName(row.decision)}`}>
                            {row.decision}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-slate-600">
                          {formatSyncReason(row.reason)}
                          {row.classification ? <span className="block text-xs text-slate-400">{formatSyncReason(row.classification)}</span> : null}
                        </td>
                        <td className="px-4 py-3 text-xs text-slate-500 whitespace-nowrap">
                          {row.created_at ? new Date(row.created_at).toLocaleString() : 'Unknown'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {gmailAuditRows.length > 3 ? (
                  <div className="flex flex-col gap-3 border-t border-slate-200 bg-slate-50 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                    <p className="text-xs text-slate-500">
                      Showing {visibleGmailAuditRows.length} of {gmailAuditRows.length} checked messages.
                    </p>
                    <button
                      type="button"
                      onClick={() => setShowAllGmailDiagnostics((current) => !current)}
                      className="inline-flex items-center justify-center rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 transition-colors hover:bg-slate-100"
                    >
                      {showAllGmailDiagnostics ? 'Show fewer' : 'Show all checked messages'}
                    </button>
                  </div>
                ) : null}
              </div>
            )}
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="bg-white rounded-2xl border border-slate-200/60 p-6 shadow-sm"
          >
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-violet-50 flex items-center justify-center">
                <KeyRound className="w-5 h-5 text-violet-600" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-slate-900">Extension API Key</h2>
                <p className="text-xs text-slate-500">Generate a personal key for the Chrome extension</p>
              </div>
            </div>

            <div className="space-y-4">
              <p className="text-sm text-slate-600">
                Use this key only in the extension setup screen. It is tied to your account and replaces the old shared environment key flow.
              </p>

              {apiKeyStatus?.has_api_key ? (
                <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
                  <p>Active key ending in <span className="font-semibold text-slate-900">{apiKeyStatus.last4}</span></p>
                  <p className="mt-1 text-xs text-slate-500">
                    Created {apiKeyStatus.created_at ? new Date(apiKeyStatus.created_at).toLocaleString() : 'unknown'}
                    {apiKeyStatus.last_used_at ? ` • Last used ${new Date(apiKeyStatus.last_used_at).toLocaleString()}` : ''}
                  </p>
                </div>
              ) : (
                <div className="rounded-xl border border-dashed border-slate-200 px-4 py-3 text-sm text-slate-500">
                  No personal API key generated yet.
                </div>
              )}

              {newApiKey && (
                <div className="space-y-2">
                  <label className="block text-xs font-medium text-slate-600">
                    Newly generated key
                  </label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      readOnly
                      value={newApiKey}
                      className="flex-1 px-3 py-2 text-sm border border-slate-200 rounded-xl bg-slate-50 text-slate-700"
                    />
                    <button
                      onClick={copyApiKey}
                      className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-slate-700 border border-slate-200 rounded-xl hover:bg-slate-50 transition-colors"
                    >
                      <Copy className="w-4 h-4" />
                      {copySaved ? 'Copied' : 'Copy'}
                    </button>
                  </div>
                  <p className="text-xs text-amber-600">
                    Copy this now. For security, the full key is only shown once after generation.
                  </p>
                </div>
              )}

              <button
                onClick={createNewApiKey}
                disabled={generatingKey}
                className="inline-flex items-center gap-2 px-4 py-2.5 bg-violet-600 text-white text-sm font-medium rounded-xl hover:bg-violet-700 transition-colors disabled:opacity-50"
              >
                {generatingKey ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                {apiKeyStatus?.has_api_key ? 'Rotate API Key' : 'Generate API Key'}
              </button>
            </div>
          </motion.div>

          {/* Chrome Extension */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.125 }}
            className="bg-white rounded-2xl border border-slate-200/60 p-6 shadow-sm"
          >
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center">
                <Chrome className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-slate-900">Chrome Extension</h2>
                <p className="text-xs text-slate-500">Track jobs from any career page while you browse</p>
              </div>
            </div>

            <div className="space-y-4">
              <p className="text-sm text-slate-600">
                The AppTrail extension detects job listings on 15+ ATS platforms, tracks your career page visits, and lets you save jobs to your pipeline with one click.
              </p>

              <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                <div className="grid gap-2 text-sm text-slate-600">
                  <div className="flex items-start gap-2">
                    <span className="text-emerald-500 mt-0.5">1.</span>
                    <span>{import.meta.env.VITE_CHROME_EXTENSION_URL ? 'Install the extension from the Chrome Web Store' : 'Install the extension (link available after store publication)'}</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="text-emerald-500 mt-0.5">2.</span>
                    <span>Generate an API key above and paste it into the extension setup</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="text-emerald-500 mt-0.5">3.</span>
                    <span>Browse job listings — AppTrail will detect and track them automatically</span>
                  </div>
                </div>
              </div>

              {import.meta.env.VITE_CHROME_EXTENSION_URL ? (
                <a
                  href={import.meta.env.VITE_CHROME_EXTENSION_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 px-4 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-xl hover:bg-blue-700 transition-colors"
                >
                  <Chrome className="w-4 h-4" />
                  Get the Extension
                  <ExternalLink className="w-3.5 h-3.5 opacity-60" />
                </a>
              ) : (
                <div className="rounded-xl border border-dashed border-slate-200 px-4 py-3 text-sm text-slate-500">
                  Chrome Web Store link will appear here once the extension is published.
                </div>
              )}
            </div>
          </motion.div>

          {/* Privacy & Data */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 }}
            className="bg-white rounded-2xl border border-slate-200/60 p-6 shadow-sm"
          >
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-indigo-50 flex items-center justify-center">
                <Shield className="w-5 h-5 text-indigo-600" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-slate-900">Privacy & Data</h2>
                <p className="text-xs text-slate-500">Control how your data is processed and manage your account</p>
              </div>
            </div>

            {consent && (
              <div className="space-y-4">
                <label className="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={consent.consents.ai_processing}
                    onChange={(e) => setConsent({
                      ...consent,
                      consents: { ...consent.consents, ai_processing: e.target.checked },
                    })}
                    className="mt-0.5 w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <span className="text-sm text-slate-700">
                    <span className="flex items-center gap-1.5 font-medium text-slate-900">
                      <Brain className="w-3.5 h-3.5 text-violet-500" /> AI Processing
                    </span>
                    Allow OpenAI-backed classification, Copilot answers, Radar summaries, draft generation, resume parsing, and resume tailoring. Safety filters redact secrets before provider calls where possible; AI trace payloads are retained for a limited audit window and then redacted.
                  </span>
                </label>

                <label className="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={consent.consents.third_party_enrichment}
                    onChange={(e) => setConsent({
                      ...consent,
                      consents: { ...consent.consents, third_party_enrichment: e.target.checked },
                    })}
                    className="mt-0.5 w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <span className="text-sm text-slate-700">
                    <span className="flex items-center gap-1.5 font-medium text-slate-900">
                      <Users className="w-3.5 h-3.5 text-amber-500" /> Third-Party Enrichment
                    </span>
                    Use Hunter.io and Clearbit for contact lookups and company logos. Only company domains are sent.
                  </span>
                </label>

                <label className="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={consent.consents.web_research}
                    onChange={(e) => setConsent({
                      ...consent,
                      consents: { ...consent.consents, web_research: e.target.checked },
                    })}
                    className="mt-0.5 w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <span className="text-sm text-slate-700">
                    <span className="flex items-center gap-1.5 font-medium text-slate-900">
                      <Globe className="w-3.5 h-3.5 text-sky-500" /> Web Research
                    </span>
                    Allow Radar to query public sources and save dated research reports with citations, deltas, and follow-up actions tied to your profile.
                  </span>
                </label>

                <label className="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={consent.consents.source_intelligence}
                    onChange={(e) => setConsent({
                      ...consent,
                      consents: { ...consent.consents, source_intelligence: e.target.checked },
                    })}
                    className="mt-0.5 w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <span className="text-sm text-slate-700">
                    <span className="flex items-center gap-1.5 font-medium text-slate-900">
                      <Link2 className="w-3.5 h-3.5 text-emerald-500" /> Source Intelligence
                    </span>
                    Use sanitized job-source metadata from my applications to improve company job search. Private application links, scheduling links, and email contents are not shared.
                  </span>
                </label>

                <button
                  onClick={async () => {
                    setSavingConsent(true);
                    setErrorMessage(null);
                    try {
                      const updated = await updateConsent({
                        core: true,
                        ai_processing: consent.consents.ai_processing,
                        third_party_enrichment: consent.consents.third_party_enrichment,
                        web_research: consent.consents.web_research,
                        source_intelligence: consent.consents.source_intelligence,
                      });
                      setConsent(updated);
                      setStatusMessage('Privacy preferences updated.');
                      setTimeout(() => setStatusMessage(null), 3000);
                    } catch (err) {
                      setErrorMessage(err instanceof Error ? err.message : 'Failed to update consent.');
                    } finally {
                      setSavingConsent(false);
                    }
                  }}
                  disabled={savingConsent}
                  className="inline-flex items-center gap-2 px-4 py-2.5 bg-indigo-600 text-white text-sm font-medium rounded-xl hover:bg-indigo-700 transition-colors disabled:opacity-50"
                >
                  {savingConsent ? <Loader2 className="w-4 h-4 animate-spin" /> : <Shield className="w-4 h-4" />}
                  Update Privacy Preferences
                </button>

                <div className="rounded-xl border border-slate-200 bg-white">
                  <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
                    <div>
                      <h3 className="text-sm font-semibold text-slate-900">Private Application Links</h3>
                      <p className="text-xs text-slate-500">Raw tokenized URLs stay encrypted and user-scoped.</p>
                    </div>
                    <button
                      onClick={loadPrefs}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-50"
                    >
                      <RefreshCw className="w-3.5 h-3.5" />
                      Refresh
                    </button>
                  </div>
                  {sourcePrivateLinks.length > 0 ? (
                    <div className="divide-y divide-slate-100">
                      {sourcePrivateLinks.slice(0, 8).map((link) => (
                        <div key={link.id} className="grid gap-3 px-4 py-3 text-xs text-slate-600 sm:grid-cols-[1fr_auto] sm:items-center">
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-semibold text-slate-900">{link.provider || 'unknown'}</span>
                              <span className="rounded-full bg-slate-100 px-2 py-0.5 font-medium">{link.link_type.replace(/_/g, ' ')}</span>
                              <span className="rounded-full bg-amber-50 px-2 py-0.5 font-medium text-amber-700">{link.sanitization_status.replace(/_/g, ' ')}</span>
                            </div>
                            <p className="mt-1 truncate text-slate-500">{link.company_domain || 'No company domain'} - {link.created_at ? new Date(link.created_at).toLocaleDateString() : 'Unknown date'}</p>
                          </div>
                          <button
                            onClick={() => handleDeletePrivateLink(link.id)}
                            disabled={deletingPrivateLinkId === link.id}
                            className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-red-100 px-3 py-2 font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
                          >
                            {deletingPrivateLinkId === link.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                            Delete
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="px-4 py-5 text-sm text-slate-500">No private application links stored.</div>
                  )}
                </div>
              </div>
            )}

            {/* Data Export */}
            <div className="mt-6 pt-5 border-t border-slate-200">
              <h3 className="text-sm font-semibold text-slate-900 mb-2">Export Your Data</h3>
              <p className="text-xs text-slate-500 mb-3">
                Download either a spreadsheet-friendly pipeline CSV or a full account archive.
              </p>
              <div className="grid gap-3 sm:grid-cols-2">
                <button
                  onClick={async () => {
                    setExportingCsv(true);
                    setErrorMessage(null);
                    try {
                      await exportCsv();
                      setStatusMessage('Pipeline CSV exported successfully.');
                      setTimeout(() => setStatusMessage(null), 3000);
                    } catch (err) {
                      setErrorMessage(err instanceof Error ? err.message : 'Failed to export pipeline CSV.');
                    } finally {
                      setExportingCsv(false);
                    }
                  }}
                  disabled={exportingCsv}
                  className="inline-flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium text-slate-700 border border-slate-200 rounded-xl hover:bg-slate-50 transition-colors disabled:opacity-50"
                >
                  {exportingCsv ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                  Download CSV
                </button>

                <button
                  onClick={async () => {
                    setExportingAccount(true);
                    setErrorMessage(null);
                    try {
                      const blob = await exportAccountData();
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement('a');
                      a.href = url;
                      a.download = 'opportunity-radar-export.json';
                      a.click();
                      URL.revokeObjectURL(url);
                      setStatusMessage('Account archive exported successfully.');
                      setTimeout(() => setStatusMessage(null), 3000);
                    } catch (err) {
                      setErrorMessage(err instanceof Error ? err.message : 'Failed to export account archive.');
                    } finally {
                      setExportingAccount(false);
                    }
                  }}
                  disabled={exportingAccount}
                  className="inline-flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium text-slate-700 border border-slate-200 rounded-xl hover:bg-slate-50 transition-colors disabled:opacity-50"
                >
                  {exportingAccount ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                  Download Archive
                </button>
              </div>
            </div>
          </motion.div>

          {/* Danger Zone */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.175 }}
            className="bg-white rounded-2xl border border-red-200/60 p-6 shadow-sm"
          >
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-red-50 flex items-center justify-center">
                <Trash2 className="w-5 h-5 text-red-500" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-red-900">Danger Zone</h2>
                <p className="text-xs text-red-400">Irreversible actions</p>
              </div>
            </div>

            <p className="text-sm text-slate-600 mb-4">
              Permanently delete your account and all associated data. This includes all jobs, contacts, emails, interviews, and settings. This action cannot be undone.
            </p>

            {showDeleteConfirm ? (
              <div className="rounded-xl border border-red-200 bg-red-50 p-4 space-y-3">
                <p className="text-sm font-medium text-red-800">
                  Type <span className="font-mono bg-red-100 px-1.5 py-0.5 rounded">DELETE</span> to confirm:
                </p>
                <input
                  type="text"
                  value={deleteInput}
                  onChange={(e) => setDeleteInput(e.target.value)}
                  placeholder="DELETE"
                  className="w-full px-3 py-2 text-sm border border-red-200 rounded-xl bg-white text-red-900 placeholder-red-300 focus:ring-red-500 focus:border-red-500"
                />
                <div className="flex gap-2">
                  <button
                    onClick={async () => {
                      if (deleteInput !== 'DELETE') return;
                      setDeleting(true);
                      setErrorMessage(null);
                      try {
                        await deleteAccount();
                        signOut();
                      } catch (err) {
                        setErrorMessage(err instanceof Error ? err.message : 'Failed to delete account.');
                        setDeleting(false);
                      }
                    }}
                    disabled={deleteInput !== 'DELETE' || deleting}
                    className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-xl hover:bg-red-700 transition-colors disabled:opacity-50"
                  >
                    {deleting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                    Delete My Account
                  </button>
                  <button
                    onClick={() => {
                      setShowDeleteConfirm(false);
                      setDeleteInput('');
                    }}
                    className="px-4 py-2 text-sm font-medium text-slate-600 border border-slate-200 rounded-xl hover:bg-slate-50 transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setShowDeleteConfirm(true)}
                className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-red-700 border border-red-200 rounded-xl hover:bg-red-50 transition-colors"
              >
                <Trash2 className="w-4 h-4" />
                Delete My Account
              </button>
            )}
          </motion.div>

          {/* Save Button */}
          <div className="flex items-center gap-3">
            <button
              onClick={savePrefs}
              disabled={saving}
              className="flex items-center gap-2 px-5 py-2.5 bg-slate-900 text-white text-sm font-medium rounded-xl hover:bg-slate-800 transition-colors disabled:opacity-50"
            >
              {saving ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Save className="w-4 h-4" />
              )}
              {saving ? 'Saving...' : 'Save Preferences'}
            </button>
            {saved && (
              <motion.span
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                className="text-sm text-emerald-600 font-medium"
              >
                Saved successfully
              </motion.span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
