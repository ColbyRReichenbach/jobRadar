import { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { Bell, Phone, Mail, Save, Loader2, KeyRound, Copy, RefreshCw } from 'lucide-react';
import {
  ApiKeyStatus,
  NotificationPrefs,
  fetchApiKeyStatus,
  fetchNotificationPreferences,
  generateApiKey,
  updateNotificationPreferences,
} from '../lib/api';

export function Settings() {
  const [prefs, setPrefs] = useState<NotificationPrefs>({
    sms_enabled: false,
    sms_phone: null,
    weekly_digest_enabled: false,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [phone, setPhone] = useState('');
  const [apiKeyStatus, setApiKeyStatus] = useState<ApiKeyStatus | null>(null);
  const [newApiKey, setNewApiKey] = useState('');
  const [copySaved, setCopySaved] = useState(false);
  const [generatingKey, setGeneratingKey] = useState(false);

  useEffect(() => {
    loadPrefs();
  }, []);

  const loadPrefs = async () => {
    try {
      const [prefsData, keyStatus] = await Promise.all([
        fetchNotificationPreferences(),
        fetchApiKeyStatus(),
      ]);
      setPrefs(prefsData);
      setPhone(prefsData.sms_phone || '');
      setApiKeyStatus(keyStatus);
    } catch (err) {
      console.error('Failed to load settings:', err);
    } finally {
      setLoading(false);
    }
  };

  const savePrefs = async () => {
    setSaving(true);
    setSaved(false);
    try {
      const data = await updateNotificationPreferences({
        sms_enabled: prefs.sms_enabled,
        sms_phone: phone || null,
        weekly_digest_enabled: prefs.weekly_digest_enabled,
      });
      setPrefs(data);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      console.error('Failed to save preferences:', err);
    } finally {
      setSaving(false);
    }
  };

  const createNewApiKey = async () => {
    setGeneratingKey(true);
    setCopySaved(false);
    try {
      const data = await generateApiKey();
      setNewApiKey(data.api_key);
      setApiKeyStatus({
        has_api_key: true,
        last4: data.last4,
        created_at: data.created_at,
        last_used_at: null,
      });
    } catch (err) {
      console.error('Failed to generate API key:', err);
    } finally {
      setGeneratingKey(false);
    }
  };

  const copyApiKey = async () => {
    if (!newApiKey) return;
    try {
      await navigator.clipboard.writeText(newApiKey);
      setCopySaved(true);
      setTimeout(() => setCopySaved(false), 2500);
    } catch (err) {
      console.error('Failed to copy API key:', err);
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
        <p className="text-sm text-slate-500 mb-8">Manage your notification preferences</p>

        <div className="space-y-6">
          {/* SMS Notifications */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-white rounded-2xl border border-slate-200/60 p-6 shadow-sm"
          >
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center">
                <Phone className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-slate-900">SMS Alerts</h2>
                <p className="text-xs text-slate-500">Get text messages for urgent updates</p>
              </div>
            </div>

            <div className="space-y-4">
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={prefs.sms_enabled}
                  onChange={(e) => setPrefs({ ...prefs, sms_enabled: e.target.checked })}
                  className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-slate-700">
                  Enable SMS for offers and interview requests
                </span>
              </label>

              {prefs.sms_enabled && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  className="ml-7"
                >
                  <label className="block text-xs font-medium text-slate-600 mb-1">
                    Phone Number
                  </label>
                  <input
                    type="tel"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="+1 (555) 123-4567"
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                  />
                  <p className="text-xs text-slate-400 mt-1">
                    Used for offer notifications and interview reminders only
                  </p>
                </motion.div>
              )}
            </div>
          </motion.div>

          {/* Weekly Digest */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
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
            transition={{ delay: 0.15 }}
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

          {/* In-App Notifications Info */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="bg-white rounded-2xl border border-slate-200/60 p-6 shadow-sm"
          >
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 rounded-xl bg-amber-50 flex items-center justify-center">
                <Bell className="w-5 h-5 text-amber-600" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-slate-900">In-App Notifications</h2>
                <p className="text-xs text-slate-500">Always enabled</p>
              </div>
            </div>
            <p className="text-sm text-slate-500 ml-[52px]">
              You'll always receive in-app alerts for dead listings, follow-up reminders, and status changes.
            </p>
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
