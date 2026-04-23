import { useState } from 'react';
import { motion } from 'motion/react';
import { Shield, Brain, Users, Database, ExternalLink, Loader2, Globe } from 'lucide-react';
import { DialogShell } from './DialogShell';
import { updateConsent } from '../lib/api';

interface ConsentModalProps {
  onAccepted: () => void;
  onDeclined: () => void;
}

export function ConsentModal({ onAccepted, onDeclined }: ConsentModalProps) {
  const [aiProcessing, setAiProcessing] = useState(true);
  const [thirdParty, setThirdParty] = useState(true);
  const [webResearch, setWebResearch] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showDeclineWarning, setShowDeclineWarning] = useState(false);

  const handleAccept = async () => {
    setSaving(true);
    setError(null);
    try {
      await updateConsent({
        core: true,
        ai_processing: aiProcessing,
        third_party_enrichment: thirdParty,
        web_research: webResearch,
      });
      onAccepted();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save consent.');
    } finally {
      setSaving(false);
    }
  };

  const handleDecline = () => {
    if (!showDeclineWarning) {
      setShowDeclineWarning(true);
      return;
    }
    onDeclined();
  };

  return (
    <DialogShell
      onClose={() => {}}
      titleId="consent-modal-title"
      panelClassName="absolute inset-0 m-auto w-full max-w-lg max-h-[90vh] overflow-y-auto bg-white rounded-2xl border border-slate-200/60 shadow-xl p-8"
      overlayClassName="absolute inset-0 bg-slate-900/50 backdrop-blur-sm"
    >
      <div className="space-y-6">
        {/* Header */}
        <div className="text-center">
          <div className="mx-auto w-14 h-14 rounded-2xl bg-indigo-50 flex items-center justify-center mb-4">
            <Shield className="w-7 h-7 text-indigo-600" />
          </div>
          <h2 id="consent-modal-title" className="text-2xl font-serif font-bold text-slate-900">
            Your Data, Your Choice
          </h2>
          <p className="mt-2 text-sm text-slate-500">
            AppTrail needs your consent to collect and process data. Review what we do and choose what you're comfortable with.
          </p>
        </div>

        {/* Core consent (required) */}
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
          <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-lg bg-emerald-50 flex items-center justify-center flex-shrink-0 mt-0.5">
              <Database className="w-4.5 h-4.5 text-emerald-600" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-slate-900">Core Data Collection</span>
                <span className="text-[10px] font-medium uppercase tracking-wider text-emerald-700 bg-emerald-100 px-1.5 py-0.5 rounded">Required</span>
              </div>
              <p className="mt-1 text-xs text-slate-500">
                Store your saved jobs, pipeline status, contacts, emails, and career page visits. This is essential for AppTrail to function.
              </p>
            </div>
            <input
              type="checkbox"
              checked
              disabled
              className="mt-1 w-4 h-4 rounded border-slate-300 text-emerald-600"
            />
          </div>
        </div>

        {/* AI Processing (optional) */}
        <label className="block rounded-xl border border-slate-200 p-4 cursor-pointer hover:bg-slate-50 transition-colors">
          <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-lg bg-violet-50 flex items-center justify-center flex-shrink-0 mt-0.5">
              <Brain className="w-4.5 h-4.5 text-violet-600" />
            </div>
            <div className="flex-1">
              <span className="text-sm font-semibold text-slate-900">AI Processing</span>
              <p className="mt-1 text-xs text-slate-500">
                Send email subjects and bodies to OpenAI to classify emails, generate draft replies, and tailor your resume. No data is stored by OpenAI.
              </p>
              <p className="mt-1.5 text-xs text-slate-400">
                If disabled, emails will use rule-based classification and drafts will use templates.
              </p>
            </div>
            <input
              type="checkbox"
              checked={aiProcessing}
              onChange={(e) => setAiProcessing(e.target.checked)}
              className="mt-1 w-4 h-4 rounded border-slate-300 text-violet-600 focus:ring-violet-500"
            />
          </div>
        </label>

        {/* Third-party enrichment (optional) */}
        <label className="block rounded-xl border border-slate-200 p-4 cursor-pointer hover:bg-slate-50 transition-colors">
          <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-lg bg-amber-50 flex items-center justify-center flex-shrink-0 mt-0.5">
              <Users className="w-4.5 h-4.5 text-amber-600" />
            </div>
            <div className="flex-1">
              <span className="text-sm font-semibold text-slate-900">Third-Party Enrichment</span>
              <p className="mt-1 text-xs text-slate-500">
                Use Hunter.io for contact lookups and Clearbit for company logos. Only company domains are sent — never your personal data.
              </p>
              <p className="mt-1.5 text-xs text-slate-400">
                If disabled, contacts are still created from emails but without enriched data.
              </p>
            </div>
            <input
              type="checkbox"
              checked={thirdParty}
              onChange={(e) => setThirdParty(e.target.checked)}
              className="mt-1 w-4 h-4 rounded border-slate-300 text-amber-600 focus:ring-amber-500"
            />
          </div>
        </label>

        <label className="block rounded-xl border border-slate-200 p-4 cursor-pointer hover:bg-slate-50 transition-colors">
          <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-lg bg-sky-50 flex items-center justify-center flex-shrink-0 mt-0.5">
              <Globe className="w-4.5 h-4.5 text-sky-600" />
            </div>
            <div className="flex-1">
              <span className="text-sm font-semibold text-slate-900">Web Research</span>
              <p className="mt-1 text-xs text-slate-500">
                Allow Radar research trackers to search the public web and save dated reports with external evidence.
              </p>
              <p className="mt-1.5 text-xs text-slate-400">
                If disabled, you can still use internal Radar, but research and hybrid trackers will not run public-web research.
              </p>
            </div>
            <input
              type="checkbox"
              checked={webResearch}
              onChange={(e) => setWebResearch(e.target.checked)}
              className="mt-1 w-4 h-4 rounded border-slate-300 text-sky-600 focus:ring-sky-500"
            />
          </div>
        </label>

        {/* Data Agreement link */}
        <p className="text-xs text-center text-slate-400">
          By continuing, you agree to our{' '}
          <a
            href="https://apptrail.com/privacy"
            target="_blank"
            rel="noopener noreferrer"
            className="text-indigo-500 hover:text-indigo-600 inline-flex items-center gap-0.5"
          >
            Privacy Policy <ExternalLink className="w-3 h-3" />
          </a>
        </p>

        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
            {error}
          </div>
        )}

        {/* Actions */}
        <div className="space-y-3">
          <button
            onClick={handleAccept}
            disabled={saving}
            className="w-full flex items-center justify-center gap-2 px-5 py-3 text-sm font-semibold text-white rounded-xl bg-gradient-to-r from-slate-900 to-blue-700 hover:from-slate-800 hover:to-blue-600 transition-all disabled:opacity-50"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Shield className="w-4 h-4" />}
            Accept & Continue
          </button>

          {showDeclineWarning ? (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              className="rounded-xl border border-amber-200 bg-amber-50 p-4"
            >
              <p className="text-sm text-amber-800 font-medium">Are you sure?</p>
              <p className="mt-1 text-xs text-amber-700">
                Declining will sign you out. AppTrail requires core data consent to function. You can sign in again anytime and accept.
              </p>
              <div className="mt-3 flex gap-2">
                <button
                  onClick={handleDecline}
                  className="px-4 py-2 text-xs font-medium text-red-700 border border-red-200 rounded-lg hover:bg-red-50 transition-colors"
                >
                  Decline & Sign Out
                </button>
                <button
                  onClick={() => setShowDeclineWarning(false)}
                  className="px-4 py-2 text-xs font-medium text-slate-600 border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors"
                >
                  Go Back
                </button>
              </div>
            </motion.div>
          ) : (
            <button
              onClick={handleDecline}
              className="w-full text-center text-xs text-slate-400 hover:text-slate-600 transition-colors py-2"
            >
              Decline all — I don't want to use AppTrail
            </button>
          )}
        </div>
      </div>
    </DialogShell>
  );
}
