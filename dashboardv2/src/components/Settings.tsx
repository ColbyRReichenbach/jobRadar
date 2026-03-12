import { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { Bell, Mail, Save, Loader2, KeyRound, Copy, RefreshCw } from 'lucide-react';
import {
  ApiKeyStatus,
  NotificationPrefs,
  fetchApiKeyStatus,
  fetchNotificationPreferences,
  generateApiKey,
  updateNotificationPreferences,
} from '../lib/api';
import { DEFAULT_LOCAL_NOTIFICATION_PREFS, LocalNotificationPrefs, loadLocalNotificationPrefs, saveLocalNotificationPrefs } from '../lib/localNotificationPrefs';

export function Settings() {
  const [prefs, setPrefs] = useState<NotificationPrefs>({
    sms_enabled: false,
    sms_phone: null,
    weekly_digest_enabled: false,
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

  useEffect(() => {
    loadPrefs();
  }, []);

  const loadPrefs = async () => {
    setErrorMessage(null);
    try {
      const [prefsData, keyStatus] = await Promise.all([
        fetchNotificationPreferences(),
        fetchApiKeyStatus(),
      ]);
      setPrefs(prefsData);
      setLocalPrefs(loadLocalNotificationPrefs());
      setPhone(prefsData.sms_phone || '');
      setApiKeyStatus(keyStatus);
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
      saveLocalNotificationPrefs(nextLocalPrefs);
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

  const togglePref = (
    key:
      | 'inbox_updates_enabled'
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
      <div className="max-w-2xl mx-auto">
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
