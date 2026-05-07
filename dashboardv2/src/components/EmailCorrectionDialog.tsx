import { useMemo, useState } from 'react';
import { AlertTriangle, ArrowRightLeft, Inbox, MessageSquare, X } from 'lucide-react';
import { EmailFeedbackPayload } from '../types';
import { DialogShell } from './DialogShell';
import { cn } from '../lib/utils';

type CorrectionAction = 'not_relevant' | 'move_to_inbox' | 'move_to_conversation';

type Option = {
  value: string;
  label: string;
  description: string;
};

const FILTER_OPTIONS: Option[] = [
  { value: 'personal', label: 'Personal', description: 'Personal or non-career conversation.' },
  { value: 'marketing_promo', label: 'Marketing / promo', description: 'Promotional email, campaign, or newsletter.' },
  { value: 'job_board_promo', label: 'External job board alert', description: 'Generic Handshake, LinkedIn, Indeed, or job-board blast.' },
  { value: 'event_newsletter', label: 'Newsletter / event', description: 'Event or content email that is not tied to your pipeline.' },
  { value: 'finance_noise', label: 'Finance / account', description: 'Banking, bill, account, or transaction update.' },
  { value: 'retail_noise', label: 'Retail / receipt', description: 'Shopping, receipt, delivery, or sale email.' },
  { value: 'system_notification', label: 'System notification', description: 'Security, login, deployment, or automated account message.' },
  { value: 'other_filter', label: 'Other', description: 'Something else that should be filtered out.' },
];

const INBOX_OPTIONS: Option[] = [
  { value: 'application_update', label: 'Application update', description: 'Applied, received, reviewed, or general company update.' },
  { value: 'interview_request', label: 'Interview', description: 'Interview request, scheduling, or confirmed interview details.' },
  { value: 'rejection', label: 'Rejection', description: 'Decision or no-longer-moving-forward email.' },
  { value: 'offer', label: 'Offer', description: 'Offer or compensation-related application outcome.' },
  { value: 'assessment', label: 'Assessment / task', description: 'Take-home, assessment, form, or required next step.' },
  { value: 'document_request', label: 'Document request', description: 'Resume, transcript, eligibility, or verification request.' },
  { value: 'other_application', label: 'Other', description: 'Application-related, but not covered above.' },
];

const CONVERSATION_OPTIONS: Option[] = [
  { value: 'recruiter_outreach', label: 'Recruiter outreach', description: 'Recruiter message or role-specific outreach.' },
  { value: 'networking', label: 'Networking / referral', description: 'Networking, referral, intro, or warm contact.' },
  { value: 'alumni_career', label: 'Alumni / career coach', description: 'Alumni, mentor, advisor, or career coach conversation.' },
  { value: 'hiring_manager', label: 'Hiring manager', description: 'Direct hiring manager or team conversation.' },
  { value: 'other_conversation', label: 'Other', description: 'Conversation-related, but not covered above.' },
];

interface EmailCorrectionDialogProps {
  action: CorrectionAction;
  surface: 'inbox' | 'conversation';
  emailId: string;
  subject?: string;
  onClose: () => void;
  onSubmit: (payload: EmailFeedbackPayload) => Promise<void>;
}

function actionConfig(action: CorrectionAction, surface: 'inbox' | 'conversation') {
  if (action === 'move_to_inbox') {
    return {
      title: 'Move to Inbox',
      subtitle: 'Tell AppTrail what kind of application email this is.',
      route: 'application_inbox' as const,
      options: INBOX_OPTIONS,
      icon: <Inbox className="h-5 w-5 text-indigo-600" />,
      submit: 'Move to Inbox',
    };
  }
  if (action === 'move_to_conversation') {
    return {
      title: 'Move to Conversations',
      subtitle: 'Tell AppTrail what kind of relationship thread this is.',
      route: 'conversation' as const,
      options: CONVERSATION_OPTIONS,
      icon: <MessageSquare className="h-5 w-5 text-indigo-600" />,
      submit: 'Move to Conversations',
    };
  }
  return {
    title: surface === 'conversation' ? 'Not Conversation Related' : 'Not Job Related',
    subtitle: 'This will hide the email from AppTrail and save a correction label.',
    route: 'filter' as const,
    options: FILTER_OPTIONS,
    icon: <AlertTriangle className="h-5 w-5 text-amber-600" />,
    submit: surface === 'conversation' ? 'Filter from Conversations' : 'Filter from Inbox',
  };
}

export function EmailCorrectionDialog({
  action,
  surface,
  emailId,
  subject,
  onClose,
  onSubmit,
}: EmailCorrectionDialogProps) {
  const config = useMemo(() => actionConfig(action, surface), [action, surface]);
  const [selected, setSelected] = useState(config.options[0]?.value || '');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    setSaving(true);
    setError(null);
    try {
      await onSubmit({
        email_id: emailId,
        is_job_related: config.route !== 'filter',
        feedback_action: action,
        corrected_route: config.route,
        corrected_subtype: selected,
        feedback_label: selected,
        source_surface: surface,
        notes: notes.trim() || undefined,
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save this correction.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <DialogShell
      onClose={onClose}
      titleId="email-correction-dialog-title"
      wrapperClassName="fixed inset-0 z-[60] flex items-end justify-center p-0 sm:items-center sm:p-4"
      panelClassName="bg-white w-full max-w-2xl max-h-[92dvh] sm:max-h-[min(760px,calc(100dvh-2rem))] rounded-t-[2rem] sm:rounded-3xl shadow-2xl overflow-hidden flex flex-col"
    >
      <div className="shrink-0 border-b border-slate-100 p-4 sm:p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 items-start gap-3">
            <div className="mt-0.5 rounded-xl bg-slate-100 p-2">{config.icon}</div>
            <div className="min-w-0">
              <h2 id="email-correction-dialog-title" className="text-xl font-serif font-bold text-slate-900">
                {config.title}
              </h2>
              <p className="mt-1 text-sm text-slate-500">{config.subtitle}</p>
              {subject && <p className="mt-2 truncate text-xs text-slate-400">{subject}</p>}
            </div>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-1 hover:bg-slate-100" aria-label="Close">
            <X className="h-5 w-5 text-slate-500" />
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6">
        <div className="grid gap-2 sm:grid-cols-2">
          {config.options.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setSelected(option.value)}
              className={cn(
                'min-h-[92px] rounded-2xl border p-3 text-left transition-colors',
                selected === option.value
                  ? 'border-indigo-300 bg-indigo-50'
                  : 'border-slate-200 bg-white hover:bg-slate-50',
              )}
            >
              <span className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                {selected === option.value && <ArrowRightLeft className="h-3.5 w-3.5 text-indigo-600" />}
                {option.label}
              </span>
              <span className="mt-1 block text-xs leading-5 text-slate-500">{option.description}</span>
            </button>
          ))}
        </div>

        <label className="mt-5 block">
          <span className="text-xs font-medium uppercase tracking-[0.18em] text-slate-400">Notes</span>
          <textarea
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            rows={3}
            placeholder="Optional context for future classifier tuning."
            className="mt-2 w-full resize-y rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3 text-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-500/20"
          />
        </label>

        {error && <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
      </div>

      <div className="shrink-0 border-t border-slate-100 bg-white p-4 sm:px-6">
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={saving || !selected}
            className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {saving ? 'Saving...' : config.submit}
          </button>
        </div>
      </div>
    </DialogShell>
  );
}
