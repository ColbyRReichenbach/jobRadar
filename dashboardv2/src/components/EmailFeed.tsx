import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ApplicationSuggestion, Email, EmailFeedbackPayload, InterviewSuggestion, Job } from '../types';
import { format, formatDistanceToNow } from 'date-fns';
import { cn } from '../lib/utils';
import {
  Mail,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Clock,
  ArrowRight,
  ChevronRight,
  ChevronLeft,
  ThumbsDown,
  AlertTriangle,
  Plus,
  Search,
  ChevronDown,
  ChevronUp,
  Trash2,
  Undo2,
  CalendarPlus,
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import {
  acceptApplicationSuggestion,
  acceptInterviewSuggestion,
  checkEmailPipeline,
  dismissApplicationSuggestion,
  fetchApplicationSuggestions,
  submitEmailFeedback,
  updateEmail,
} from '../lib/api';
import { DialogShell } from './DialogShell';
import { EmailCorrectionDialog } from './EmailCorrectionDialog';

interface EmailFeedProps {
  emails: Email[];
  jobs: Job[];
  isCollapsed: boolean;
  setIsCollapsed: (c: boolean) => void;
  forceOpen?: boolean;
  onOpenAddJob?: (draft: Partial<Job>) => void;
  onNavigateToEmail?: (email: Email) => void;
  onSuggestionAccepted?: () => void | Promise<void>;
  headerAccessory?: React.ReactNode;
  focusRequest?: {
    emailId: string;
    threadId?: string;
    tab: 'emails' | 'conversations';
    token: number;
  } | null;
}

const NOISY_INBOX_DOMAINS = new Set([
  'github.com',
  'notifications.github.com',
  'noreply.github.com',
  'railway.app',
  'railway.com',
  'vercel.com',
  'mailer.vercel.com',
  'linear.app',
]);

const NOISY_INBOX_PATTERN =
  /\b(update|digest|newsletter|billing|invoice|receipt|usage|deployment|security|verification|notification|password|team invite|product update|workflow run failed)\b/i;

type InboxFilter =
  | 'all'
  | 'interview_request'
  | 'rejection'
  | 'offer'
  | 'action_item'
  | 'job_update'
  | 'done';

type EmailThread = {
  id: string;
  emails: Email[];
  latest: Email;
  resolved: boolean;
};

function openExternal(url: string) {
  window.open(url, '_blank', 'noopener,noreferrer');
}

function categoryLabel(category?: string) {
  switch (category) {
    case 'interview_request':
      return 'Interview';
    case 'rejection':
      return 'Rejection';
    case 'offer':
      return 'Offer';
    case 'action_item':
      return 'Action Needed';
    case 'job_update':
      return 'Update';
    default:
      return 'Update';
  }
}

function classificationColor(category?: string, resolved?: boolean) {
  if (resolved) return 'bg-emerald-50 text-emerald-700 border-emerald-200';
  switch (category) {
    case 'interview_request':
      return 'bg-emerald-50 text-emerald-700 border-emerald-200';
    case 'rejection':
      return 'bg-red-50 text-red-700 border-red-200';
    case 'offer':
      return 'bg-violet-50 text-violet-700 border-violet-200';
    case 'action_item':
      return 'bg-amber-50 text-amber-700 border-amber-200';
    case 'job_update':
    default:
      return 'bg-blue-50 text-blue-700 border-blue-200';
  }
}

function classificationIcon(category?: string, resolved?: boolean) {
  if (resolved) return <CheckCircle2 className="w-3 h-3" />;
  switch (category) {
    case 'interview_request':
      return <CheckCircle2 className="w-3 h-3" />;
    case 'rejection':
      return <XCircle className="w-3 h-3" />;
    case 'offer':
      return <AlertCircle className="w-3 h-3" />;
    case 'action_item':
      return <AlertCircle className="w-3 h-3" />;
    case 'job_update':
    default:
      return <Clock className="w-3 h-3" />;
  }
}

export function EmailFeed({
  emails,
  jobs,
  isCollapsed,
  setIsCollapsed,
  forceOpen,
  onOpenAddJob,
  onNavigateToEmail,
  onSuggestionAccepted,
  headerAccessory,
  focusRequest,
}: EmailFeedProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [filter, setFilter] = useState<InboxFilter>('all');
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null);
  const [expandedThreadId, setExpandedThreadId] = useState<string | null>(null);
  const [showDoneThreads, setShowDoneThreads] = useState(false);
  const [pipelineAlert, setPipelineAlert] = useState<{
    in_pipeline: boolean;
    suggestion?: string;
    company_name?: string;
  } | null>(null);
  const [dismissedEmails, setDismissedEmails] = useState<Set<string>>(new Set());
  const [hiddenEmailIds, setHiddenEmailIds] = useState<Set<string>>(new Set());
  const [threadResolutionOverrides, setThreadResolutionOverrides] = useState<Record<string, boolean>>({});
  const [threadPendingDeletion, setThreadPendingDeletion] = useState<EmailThread | null>(null);
  const [creatingInterview, setCreatingInterview] = useState(false);
  const [interviewStatus, setInterviewStatus] = useState<string | null>(null);
  const [applicationSuggestions, setApplicationSuggestions] = useState<ApplicationSuggestion[]>([]);
  const [applicationSuggestionsCollapsed, setApplicationSuggestionsCollapsed] = useState(false);
  const [suggestionStatus, setSuggestionStatus] = useState<string | null>(null);
  const [busySuggestionKey, setBusySuggestionKey] = useState<string | null>(null);
  const [correctionDialog, setCorrectionDialog] = useState<{
    action: 'not_relevant' | 'move_to_conversation';
    email: Email;
  } | null>(null);
  const [interviewDraft, setInterviewDraft] = useState<{
    email: Email;
    scheduledAt: string;
    duration: string;
    location: string;
    interviewerName: string;
    interviewerEmail: string;
    notes: string;
  } | null>(null);
  const messageRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const collapsed = forceOpen ? false : isCollapsed;

  const effectiveEmails = useMemo(
    () =>
      emails.map((email) => {
        const threadId = email.threadId || email.id;
        const overrideResolved = threadResolutionOverrides[threadId];
        return {
          ...email,
          resolved: overrideResolved ?? email.resolved,
          hidden: email.hidden || hiddenEmailIds.has(email.id) || dismissedEmails.has(email.id),
        };
      }),
    [dismissedEmails, emails, hiddenEmailIds, threadResolutionOverrides],
  );

  const inboxEmails = useMemo(
    () =>
      effectiveEmails.filter((email) => {
        if (email.type === 'conversation' || email.hidden) return false;
        const senderDomain = (email.senderDomain || email.senderEmail?.split('@')[1] || '').toLowerCase();
        const isNoise = senderDomain
          ? NOISY_INBOX_DOMAINS.has(senderDomain) &&
            NOISY_INBOX_PATTERN.test(`${email.subject} ${email.snippet}`)
          : false;
        if (email.inPipeline || email.category === 'interview_request' || email.category === 'action_item') {
          return true;
        }
        return !isNoise;
      }),
    [effectiveEmails],
  );

  const filteredEmails = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return inboxEmails.filter((email) => {
      const matchesSearch =
        !query ||
        [email.sender, email.subject, email.companyName, email.senderEmail, email.snippet]
          .filter(Boolean)
          .join(' ')
          .toLowerCase()
          .includes(query);

      if (!matchesSearch) return false;
      if (filter === 'done') return !!email.resolved;
      if (filter === 'all') return !email.resolved;
      return email.category === filter && !email.resolved;
    });
  }, [filter, inboxEmails, searchQuery]);

  const threads = useMemo(() => {
    const grouped = new Map<string, Email[]>();
    filteredEmails.forEach((email) => {
      const key = email.threadId || email.id;
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key)!.push(email);
    });
    return Array.from(grouped.entries())
      .map(([id, threadEmails]) => {
        const sorted = [...threadEmails].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
        return {
          id,
          emails: sorted,
          latest: sorted[0],
          resolved: sorted.every((email) => !!email.resolved),
        };
      })
      .sort((a, b) => new Date(b.latest.date).getTime() - new Date(a.latest.date).getTime());
  }, [filteredEmails]);

  const allThreads = useMemo(() => {
    const grouped = new Map<string, Email[]>();
    inboxEmails.forEach((email) => {
      const key = email.threadId || email.id;
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key)!.push(email);
    });
    return Array.from(grouped.entries()).map(([id, threadEmails]) => {
      const sorted = [...threadEmails].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
      return {
        id,
        emails: sorted,
        latest: sorted[0],
        resolved: sorted.every((email) => !!email.resolved),
      };
    });
  }, [inboxEmails]);

  const activeThreads = threads.filter((thread) => !thread.resolved);
  const doneThreads = allThreads
    .filter((thread) => thread.resolved)
    .sort((a, b) => new Date(b.latest.date).getTime() - new Date(a.latest.date).getTime());
  const visibleThreads = filter === 'done' ? doneThreads : activeThreads;
  const selectedThread = allThreads.find((thread) => thread.id === selectedThreadId) || null;
  const selectedMessage =
    selectedThread?.emails.find((email) => email.id === selectedMessageId) || selectedThread?.latest || null;

  const refreshApplicationSuggestions = async () => {
    if (!forceOpen) return;
    try {
      setApplicationSuggestions(await fetchApplicationSuggestions());
    } catch (err) {
      console.error('Failed to load application suggestions:', err);
    }
  };

  useEffect(() => {
    void refreshApplicationSuggestions();
  }, [forceOpen, emails.length]);

  useEffect(() => {
    if (selectedThread && !allThreads.some((thread) => thread.id === selectedThread.id)) {
      setSelectedThreadId(null);
      setSelectedMessageId(null);
      setPipelineAlert(null);
    }
  }, [allThreads, selectedThread]);

  useEffect(() => {
    if (!focusRequest) return;
    setSearchQuery('');
    setFilter('all');
    const target = allThreads.find(
      (thread) =>
        thread.id === (focusRequest.threadId || focusRequest.emailId) ||
        thread.emails.some((email) => email.id === focusRequest.emailId),
    );
    if (target) {
      setSelectedThreadId(target.id);
      setExpandedThreadId(target.id);
      setSelectedMessageId(focusRequest.emailId);
    }
  }, [allThreads, focusRequest]);

  useEffect(() => {
    if (!selectedMessageId) return;
    messageRefs.current[selectedMessageId]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [selectedMessageId, selectedThreadId]);

  useEffect(() => {
    if (!selectedThreadId) return;
    if (!allThreads.some((thread) => thread.id === selectedThreadId)) {
      setSelectedThreadId(null);
      setSelectedMessageId(null);
      setPipelineAlert(null);
    }
  }, [allThreads, selectedThreadId]);

  useEffect(() => {
    if (!selectedThread || selectedThread.emails.some((email) => email.id === selectedMessageId)) {
      return;
    }
    setSelectedMessageId(selectedThread.latest.id);
  }, [selectedMessageId, selectedThread]);

  const getEmailLogo = (email: Email) => {
    if (email.companyLogoUrl) return email.companyLogoUrl;
    const job = jobs.find((job) => job.id === email.jobId);
    return job?.logoUrl;
  };

  const getEmailCompany = (email: Email) => {
    if (email.companyName) return email.companyName;
    const job = jobs.find((job) => job.id === email.jobId);
    return job?.company;
  };

  const handleSelectEmail = async (threadId: string, email: Email) => {
    setSelectedThreadId(threadId);
    setSelectedMessageId(email.id);
    setPipelineAlert(null);
    setInterviewStatus(null);
    if (!email.jobId && email.companyName) {
      try {
        const result = await checkEmailPipeline(email.id);
        if (!result.in_pipeline) {
          setPipelineAlert(result);
        }
      } catch {
        // Ignore pipeline check failures.
      }
    }
  };

  const handleNavigateToFullView = (email: Email) => {
    onNavigateToEmail?.(email);
  };

  const hideEmailLocally = (email: Email) => {
    setDismissedEmails((prev) => new Set([...prev, email.id]));
    setHiddenEmailIds((prev) => new Set([...prev, email.id]));
    if (selectedMessageId === email.id) {
      setSelectedThreadId(null);
      setSelectedMessageId(null);
    }
  };

  const handleCorrectionSubmit = async (payload: EmailFeedbackPayload) => {
    const email = correctionDialog?.email;
    await submitEmailFeedback(payload);
    if (email) hideEmailLocally(email);
    await onSuggestionAccepted?.();
  };

  const handleDeleteThread = async (thread: EmailThread) => {
    const hiddenIds = thread.emails.map((email) => email.id);
    setHiddenEmailIds((prev) => new Set([...prev, ...hiddenIds]));
    setSelectedThreadId(null);
    setSelectedMessageId(null);
    setThreadPendingDeletion(null);
    try {
      await Promise.all(thread.emails.map((email) => updateEmail(email.id, { hidden: true })));
    } catch (err) {
      setHiddenEmailIds((prev) => {
        const next = new Set(prev);
        hiddenIds.forEach((id) => next.delete(id));
        return next;
      });
      console.error('Failed to delete email from app view:', err);
    }
  };

  const handleThreadResolvedChange = async (
    threadId: string,
    threadEmails: Email[],
    resolved: boolean,
  ) => {
    setThreadResolutionOverrides((prev) => ({ ...prev, [threadId]: resolved }));
    try {
      await Promise.all(threadEmails.map((email) => updateEmail(email.id, { resolved })));
    } catch (err) {
      setThreadResolutionOverrides((prev) => {
        const next = { ...prev };
        delete next[threadId];
        return next;
      });
      console.error('Failed to update email resolution:', err);
    }
  };

  const handleResolveThread = async (resolved: boolean) => {
    if (!selectedThread) return;
    await handleThreadResolvedChange(selectedThread.id, selectedThread.emails, resolved);
  };

  const handleAddToPipeline = async () => {
    if (!selectedMessage || !pipelineAlert?.company_name) return;
    const classificationToStatus: Record<string, Job['status']> = {
      interview_request: 'interviewing',
      offer: 'offer',
      rejection: 'rejected',
      action_item: 'applied',
      job_update: 'applied',
      conversation: 'applied',
    };

    const extractRoleFromEmail = (email: Email) => {
      const candidates = [
        email.subject,
        email.summary,
        email.snippet,
        email.body,
      ].filter(Boolean) as string[];

      const patterns = [
        /\bfor (?:the )?([A-Z][A-Za-z0-9/&,\- ]{2,80}?) (?:role|position)\b/i,
        /\b([A-Z][A-Za-z0-9/&,\- ]{2,80}?) (?:role|position)\b/i,
        /\binterview for (?:the )?([A-Z][A-Za-z0-9/&,\- ]{2,80})\b/i,
        /\boffer for (?:the )?([A-Z][A-Za-z0-9/&,\- ]{2,80})\b/i,
      ];

      for (const text of candidates) {
        for (const pattern of patterns) {
          const match = text.match(pattern);
          if (match?.[1]) {
            return match[1].trim().replace(/\s+/g, ' ');
          }
        }
      }

      return email.subject
        .replace(/^(re|fw|fwd):\s*/i, '')
        .replace(/\b(application update|decision on your candidacy|following up on our conversation|thank you for applying)\b/gi, '')
        .replace(/\s+/g, ' ')
        .trim();
    };

    const extractUrlFromEmail = (email: Email) => {
      if (email.actionUrl) return email.actionUrl;
      const text = [email.body, email.snippet, email.summary].filter(Boolean).join(' ');
      const match = text.match(/https?:\/\/[^\s)>"']+/i);
      return match?.[0];
    };

    onOpenAddJob?.({
      company: pipelineAlert.company_name,
      role: extractRoleFromEmail(selectedMessage),
      url: extractUrlFromEmail(selectedMessage),
      status: classificationToStatus[selectedMessage.category || 'job_update'] || 'applied',
      notes: `Created from email: ${selectedMessage.subject}`,
      source: 'other',
    });
    setPipelineAlert(null);
  };

  const openInterviewDraft = (email: Email) => {
    setInterviewStatus(null);
    setInterviewDraft({
      email,
      scheduledAt: '',
      duration: '30',
      location: '',
      interviewerName: email.sender || '',
      interviewerEmail: email.senderEmail || '',
      notes: `Created from email: ${email.subject}`,
    });
  };

  const handleCreateInterviewFromDraft = async () => {
    if (!interviewDraft) return;
    setCreatingInterview(true);
    setInterviewStatus(null);
    try {
      const suggestion: InterviewSuggestion = {
        email_id: interviewDraft.email.id,
        subject: interviewDraft.email.subject,
        sender: interviewDraft.email.sender,
        sender_email: interviewDraft.email.senderEmail || null,
        company_name: interviewDraft.email.companyName || null,
        role_title: null,
        application_id: interviewDraft.email.jobId || null,
        interview_type: 'phone',
        scheduled_at: null,
        duration_minutes: null,
        location_or_link: null,
        snippet: interviewDraft.email.snippet || null,
        received_at: interviewDraft.email.date || null,
        confidence: interviewDraft.email.confidence || 0,
      };
      await acceptInterviewSuggestion(suggestion, {
        scheduled_at: interviewDraft.scheduledAt,
        duration_minutes: interviewDraft.duration ? Number(interviewDraft.duration) : undefined,
        location_or_link: interviewDraft.location || undefined,
        interviewer_name: interviewDraft.interviewerName || undefined,
        interviewer_email: interviewDraft.interviewerEmail || undefined,
        notes: interviewDraft.notes || undefined,
      });
      setInterviewStatus('Interview added to your calendar view.');
      hideEmailLocally(interviewDraft.email);
      setInterviewDraft(null);
      await onSuggestionAccepted?.();
    } catch (err) {
      setInterviewStatus(err instanceof Error ? err.message : 'Could not create the interview.');
    } finally {
      setCreatingInterview(false);
    }
  };

  const handleAcceptApplicationSuggestion = async (suggestion: ApplicationSuggestion) => {
    setBusySuggestionKey(suggestion.suggestion_key);
    setSuggestionStatus(null);
    try {
      const result = await acceptApplicationSuggestion(suggestion);
      setApplicationSuggestions((prev) => prev.filter((item) => item.suggestion_key !== suggestion.suggestion_key));
      setSuggestionStatus(
        result.duplicate
          ? `${result.application.company} was already in your pipeline. Source emails were left unchanged.`
          : `${result.application.company} was added to your pipeline and ${result.linked_email_count} email${result.linked_email_count === 1 ? '' : 's'} were linked.`,
      );
      await onSuggestionAccepted?.();
    } catch (err) {
      setSuggestionStatus(err instanceof Error ? err.message : 'Could not add this suggestion.');
    } finally {
      setBusySuggestionKey(null);
    }
  };

  const handleDismissApplicationSuggestion = async (suggestion: ApplicationSuggestion) => {
    setBusySuggestionKey(suggestion.suggestion_key);
    setSuggestionStatus(null);
    try {
      await dismissApplicationSuggestion(suggestion);
      setApplicationSuggestions((prev) => prev.filter((item) => item.suggestion_key !== suggestion.suggestion_key));
      setSuggestionStatus('Suggestion dismissed.');
    } catch (err) {
      setSuggestionStatus(err instanceof Error ? err.message : 'Could not dismiss this suggestion.');
    } finally {
      setBusySuggestionKey(null);
    }
  };

  const renderApplicationSuggestions = () => {
    if (!forceOpen && applicationSuggestions.length === 0 && !suggestionStatus) return null;
    if (applicationSuggestions.length === 0 && !suggestionStatus) return null;

    return (
      <div className="space-y-2 pb-2">
        <div className="flex items-start justify-between gap-3 px-1">
          <div>
            <h2 className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">Suggested applications</h2>
            <p className="mt-1 text-xs text-slate-500">
              Review job updates AppTrail found in Gmail before adding them to your pipeline.
            </p>
          </div>
          {applicationSuggestions.length > 0 && (
            <button
              type="button"
              onClick={() => setApplicationSuggestionsCollapsed((value) => !value)}
              className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-50"
              aria-expanded={!applicationSuggestionsCollapsed}
            >
              {applicationSuggestionsCollapsed ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronUp className="h-3.5 w-3.5" />}
              {applicationSuggestionsCollapsed ? 'Show' : 'Hide'}
            </button>
          )}
        </div>
        {applicationSuggestionsCollapsed ? (
          <p className="rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-500">
            {applicationSuggestions.length} suggestion{applicationSuggestions.length === 1 ? '' : 's'} hidden.
          </p>
        ) : (
          <>
            {suggestionStatus && (
              <div className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
                {suggestionStatus}
              </div>
            )}
            {applicationSuggestions.slice(0, 4).map((suggestion) => {
              const latestEvidence = suggestion.evidence[0];
              const isBusy = busySuggestionKey === suggestion.suggestion_key;
              return (
                <div key={suggestion.suggestion_key} className="rounded-2xl border border-indigo-100 bg-indigo-50/60 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-bold text-slate-900 truncate">
                        {suggestion.role_title}
                      </p>
                      <p className="text-xs font-medium text-indigo-700 truncate">
                        {suggestion.company}
                      </p>
                    </div>
                    <span className="shrink-0 rounded-full bg-white px-2 py-1 text-[10px] font-semibold text-slate-500">
                      {Math.round(suggestion.confidence * 100)}%
                    </span>
                  </div>
                  <p className="mt-2 line-clamp-2 text-xs text-slate-600">
                    {latestEvidence?.subject || latestEvidence?.snippet || `${suggestion.email_count} related Gmail update${suggestion.email_count === 1 ? '' : 's'}.`}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => void handleAcceptApplicationSuggestion(suggestion)}
                      disabled={isBusy}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-800 disabled:opacity-50"
                    >
                      <Plus className="h-3.5 w-3.5" />
                      {suggestion.existing_application ? 'Link emails' : 'Add to pipeline'}
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleDismissApplicationSuggestion(suggestion)}
                      disabled={isBusy}
                      className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                    >
                      Dismiss
                    </button>
                  </div>
                </div>
              );
            })}
          </>
        )}
      </div>
    );
  };

  const renderThreadCard = (thread: (typeof allThreads)[number], allowExpand = true) => {
    const email = thread.latest;
    const job = jobs.find((job) => job.id === email.jobId);
    const isSelected = selectedThreadId === thread.id;
    const isExpanded = expandedThreadId === thread.id;
    const hasMultiple = thread.emails.length > 1;
    const statusClass = classificationColor(email.category, thread.resolved);

    return (
      <div key={thread.id} className="flex flex-col gap-1">
        <motion.div
          onClick={() => {
            setSelectedThreadId(thread.id);
            setSelectedMessageId(thread.latest.id);
            if (hasMultiple && allowExpand) {
              setExpandedThreadId(isExpanded ? null : thread.id);
            }
          }}
          className={cn(
            'p-4 rounded-2xl cursor-pointer transition-all border',
            thread.resolved
              ? 'bg-slate-50 border-slate-100 opacity-80'
              : isSelected
                ? 'bg-indigo-50 border-indigo-200 shadow-sm'
                : 'bg-white border-slate-100 hover:border-slate-300 hover:shadow-sm',
          )}
        >
          <div className="flex items-start justify-between gap-3 mb-2">
            <div className="flex items-center gap-3 min-w-0">
              {getEmailLogo(email) ? (
                <img
                  src={getEmailLogo(email)!}
                  alt={getEmailCompany(email) || ''}
                  className="w-8 h-8 rounded-full border border-slate-100"
                  referrerPolicy="no-referrer"
                  onError={(event) => {
                    (event.target as HTMLImageElement).style.display = 'none';
                  }}
                />
              ) : (
                <div className="w-8 h-8 flex items-center justify-center text-xs font-medium rounded-full bg-slate-100 text-slate-500 shrink-0">
                  {(email.sender || '?').charAt(0)}
                </div>
              )}
              <div className="min-w-0">
                <h3 className="text-base font-serif font-bold text-slate-900 flex items-center gap-2 truncate">
                  <span className="truncate">{email.sender}</span>
                  {hasMultiple && (
                    <span className="text-xs bg-slate-200 text-slate-600 px-1.5 py-0.5 rounded-md font-sans font-medium">
                      {thread.emails.length}
                    </span>
                  )}
                </h3>
                <p className="text-xs text-slate-500 truncate">
                  {getEmailCompany(email) || job?.company || 'General update'}
                </p>
              </div>
            </div>
            <span className="text-[10px] font-medium text-slate-400 whitespace-nowrap">
              {formatDistanceToNow(new Date(email.date), { addSuffix: true })}
            </span>
          </div>

          <h4 className="text-sm font-serif font-bold text-slate-900 mb-1 truncate">{email.subject}</h4>
          <p className="text-xs text-slate-500 line-clamp-2 mb-3 [overflow-wrap:anywhere]">{email.snippet}</p>

          <div className="flex items-center justify-between">
            <span className={cn('inline-flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-semibold uppercase tracking-wider', statusClass)}>
              {classificationIcon(email.category, thread.resolved)}
              {thread.resolved ? 'Done' : categoryLabel(email.category)}
            </span>
            {hasMultiple && allowExpand && (
              <div className="text-slate-400 hover:text-slate-600">
                {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </div>
            )}
          </div>
        </motion.div>

        <AnimatePresence>
          {hasMultiple && isExpanded && allowExpand && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              <div className="pl-6 pr-2 py-2 space-y-2 border-l-2 border-indigo-100 ml-4 max-h-[260px] overflow-y-auto">
                {thread.emails.slice(1).map((oldEmail) => (
                  <button
                    type="button"
                    key={oldEmail.id}
                    onClick={(event) => {
                      event.stopPropagation();
                      void handleSelectEmail(thread.id, oldEmail);
                    }}
                    className={cn(
                      'w-full text-left p-3 rounded-xl border text-sm transition-colors',
                      selectedMessageId === oldEmail.id
                        ? 'bg-indigo-50 border-indigo-200'
                        : 'bg-white border-slate-200',
                    )}
                  >
                    <div className="flex justify-between items-center gap-3 mb-1">
                      <span className="font-semibold text-slate-700 truncate">
                        {oldEmail.subject}
                      </span>
                      <span className="text-[10px] text-slate-400 shrink-0">
                        {format(new Date(oldEmail.date), 'MMM d')}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500 line-clamp-2 [overflow-wrap:anywhere]">{oldEmail.snippet}</p>
                  </button>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    );
  };

  return (
    <div className={cn('flex h-full bg-[#F5F5F0]', forceOpen ? 'w-full' : '')}>
      <motion.div
        initial={false}
        animate={forceOpen ? undefined : { width: collapsed ? 64 : 320 }}
        style={forceOpen ? { width: undefined } : undefined}
        className={cn(
          'flex flex-col shrink-0 transition-all duration-300 bg-white border-r border-slate-200/60 relative',
          forceOpen
            ? selectedThreadId
              ? 'w-full md:w-[420px] lg:w-[470px] hidden md:flex'
              : 'w-full md:w-[420px] lg:w-[470px]'
            : '',
        )}
      >
        {!forceOpen && (
          <button
            onClick={() => setIsCollapsed(!collapsed)}
            aria-label={collapsed ? 'Expand updates panel' : 'Collapse updates panel'}
            title={collapsed ? 'Expand updates' : 'Collapse updates'}
            className="absolute -left-3 top-8 w-6 h-6 bg-white border border-slate-200 rounded-full flex items-center justify-center shadow-sm z-10 hover:bg-slate-50"
          >
            {collapsed ? <ChevronLeft className="w-3 h-3 text-slate-600" /> : <ChevronRight className="w-3 h-3 text-slate-600" />}
          </button>
        )}

        <div className={cn('p-6 border-b border-slate-100', collapsed ? 'flex justify-center px-0 items-center' : forceOpen ? 'block' : 'flex items-center justify-between')}>
          {forceOpen ? (
            <>
              <div className="flex items-center justify-between mb-2">
                <h1 className="text-3xl tracking-tight font-serif font-bold text-slate-900">Inbox</h1>
                <span className="text-xs px-2 py-0.5 bg-indigo-100 text-indigo-700 rounded-full font-semibold">
                  {activeThreads.reduce((count, thread) => count + thread.emails.filter((email) => !email.read).length, 0)} new
                </span>
              </div>
              <div className="flex flex-col gap-4 mt-4">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                  <input
                    type="text"
                    placeholder="Search updates, people, or companies..."
                    value={searchQuery}
                    onChange={(event) => setSearchQuery(event.target.value)}
                    className="w-full pl-9 pr-4 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all"
                  />
                </div>
                <div className="flex gap-2 flex-wrap">
                  {[
                    ['all', 'All', 'bg-slate-800 text-white', 'bg-slate-100 text-slate-600 hover:bg-slate-200'],
                    ['interview_request', 'Interview', 'bg-emerald-100 text-emerald-700', 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100'],
                    ['rejection', 'Rejection', 'bg-red-100 text-red-700', 'bg-red-50 text-red-700 hover:bg-red-100'],
                    ['offer', 'Offer', 'bg-violet-100 text-violet-700', 'bg-violet-50 text-violet-700 hover:bg-violet-100'],
                    ['action_item', 'Action Needed', 'bg-amber-100 text-amber-700', 'bg-amber-50 text-amber-700 hover:bg-amber-100'],
                    ['job_update', 'Update', 'bg-blue-100 text-blue-700', 'bg-blue-50 text-blue-700 hover:bg-blue-100'],
                    ['done', 'Done', 'bg-emerald-100 text-emerald-700', 'bg-slate-100 text-slate-600 hover:bg-slate-200'],
                  ].map(([value, label, activeClassName, idleClassName]) => (
                    <button
                      key={value}
                      onClick={() => setFilter(value as InboxFilter)}
                      className={cn(
                        'px-3 py-1.5 text-xs font-medium rounded-lg transition-colors',
                        filter === value ? activeClassName : idleClassName,
                      )}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <>
              <div className="flex items-center gap-2">
                <Mail className="w-5 h-5 text-slate-700" />
                {!collapsed && <h2 className="text-3xl tracking-tight font-serif font-bold text-slate-900">Updates</h2>}
              </div>
              {!collapsed && (
                <div className="flex items-center gap-2">
                  {headerAccessory}
                  <span className="text-xs px-2 py-0.5 bg-indigo-100 text-indigo-700 rounded-full font-semibold">
                    {activeThreads.reduce((count, thread) => count + thread.emails.filter((email) => !email.read).length, 0)} new
                  </span>
                </div>
              )}
            </>
          )}
        </div>

        <AnimatePresence mode="wait">
          {!forceOpen && selectedThread && selectedMessage ? (
            <motion.div
              key="detail"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.15 }}
              className="flex-1 flex flex-col overflow-hidden"
            >
              <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-100 bg-slate-50/50">
                <button
                  onClick={() => {
                    setSelectedThreadId(null);
                    setSelectedMessageId(null);
                    setPipelineAlert(null);
                  }}
                  className="p-1.5 text-slate-500 hover:text-slate-900 hover:bg-slate-200 rounded-lg transition-colors"
                >
                  <ArrowRight className="w-4 h-4 rotate-180" />
                </button>
                <span className="text-xs font-medium text-slate-500 truncate">Back to updates</span>
                {onNavigateToEmail && (
                  <button
                    type="button"
                    onClick={() => selectedMessage && handleNavigateToFullView(selectedMessage)}
                    className="ml-auto inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
                  >
                    {selectedMessage?.type === 'conversation' ? 'View in Conversations' : 'View in Inbox'}
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {selectedThread.emails.map((email) => (
                  <button
                    key={email.id}
                    type="button"
                    onClick={() => setSelectedMessageId(email.id)}
                    className={cn(
                      'w-full text-left p-4 rounded-2xl border transition-colors',
                      selectedMessageId === email.id ? 'bg-indigo-50 border-indigo-200' : 'bg-white border-slate-100',
                    )}
                  >
                    <div className="flex items-start justify-between gap-3 mb-2">
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-slate-900 truncate">{email.subject}</div>
                        <div className="text-[11px] text-slate-400 truncate">{email.sender}</div>
                      </div>
                      <span className="text-[10px] text-slate-400">{format(new Date(email.date), 'MMM d')}</span>
                    </div>
                    <p className="text-xs text-slate-500 line-clamp-2 [overflow-wrap:anywhere]">{email.snippet}</p>
                    {selectedMessageId === email.id && onNavigateToEmail && (
                      <div className="mt-3">
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            handleNavigateToFullView(email);
                          }}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-[11px] font-medium text-slate-700 hover:bg-slate-100"
                        >
                          {email.type === 'conversation' ? 'View in Conversations' : 'View in Inbox'}
                          <ArrowRight className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    )}
                  </button>
                ))}
              </div>
            </motion.div>
          ) : (
            <motion.div key="list" initial={false} className="flex-1 overflow-hidden">
              {collapsed ? (
                <div className="h-full overflow-y-auto p-4 space-y-2">
                  {visibleThreads.map((thread) => (
                    <div
                      key={thread.id}
                      className="w-10 h-10 mx-auto bg-indigo-50 rounded-full flex items-center justify-center relative cursor-pointer"
                      onClick={() => setIsCollapsed(false)}
                    >
                      {classificationIcon(thread.latest.category, thread.resolved)}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="h-full overflow-y-auto p-4 space-y-2">
                  {renderApplicationSuggestions()}
                  {visibleThreads.length === 0 && applicationSuggestions.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center px-8 text-center text-slate-400">
                      <Mail className="w-10 h-10 mb-3 opacity-30" />
                      <p className="text-base font-serif text-slate-500">No inbox updates found.</p>
                      <p className="text-sm mt-1">
                        {searchQuery || filter !== 'all'
                          ? 'Adjust your search or filters.'
                          : 'New application updates will appear here after Gmail sync.'}
                      </p>
                    </div>
                  ) : (
                    <>
                      {visibleThreads.map((thread) => renderThreadCard(thread, filter !== 'done'))}
                      {filter !== 'done' && doneThreads.length > 0 && (
                        <div className="pt-4">
                          <button
                            onClick={() => setShowDoneThreads((prev) => !prev)}
                            className="w-full flex items-center justify-between px-4 py-3 rounded-2xl border border-slate-200 bg-slate-50 text-slate-700 font-medium"
                          >
                            <span className="inline-flex items-center gap-2">
                              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                              Done
                              <span className="text-xs text-slate-400">{doneThreads.length}</span>
                            </span>
                            {showDoneThreads ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                          </button>
                          <AnimatePresence>
                            {showDoneThreads && (
                              <motion.div
                                initial={{ opacity: 0, height: 0 }}
                                animate={{ opacity: 1, height: 'auto' }}
                                exit={{ opacity: 0, height: 0 }}
                                className="overflow-hidden mt-2 space-y-2"
                              >
                                {doneThreads.map((thread) => (
                                  <div key={thread.id} className="relative">
                                    {renderThreadCard(thread, false)}
                                    <button
                                      type="button"
                                      onClick={(event) => {
                                        event.stopPropagation();
                                        void handleThreadResolvedChange(thread.id, thread.emails, false);
                                      }}
                                      className="absolute top-4 right-4 inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-white border border-slate-200 text-[11px] font-medium text-slate-600 hover:bg-slate-50"
                                    >
                                      <Undo2 className="w-3 h-3" />
                                      Undo
                                    </button>
                                  </div>
                                ))}
                              </motion.div>
                            )}
                          </AnimatePresence>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>

      {forceOpen && (
        <div className={cn('flex-1 flex flex-col bg-white h-full overflow-hidden', !selectedThread && 'hidden md:flex')}>
          {selectedThread && selectedMessage ? (
            <>
              <div className="p-5 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
                <div className="flex items-center gap-4 min-w-0">
                  <button
                    onClick={() => {
                      setSelectedThreadId(null);
                      setSelectedMessageId(null);
                      setPipelineAlert(null);
                    }}
                    className="md:hidden p-2 -ml-2 text-slate-500 hover:text-slate-900 hover:bg-slate-200 rounded-lg"
                  >
                    <ArrowRight className="w-5 h-5 rotate-180" />
                  </button>
                  <div className="flex items-center gap-3 min-w-0">
                    {getEmailLogo(selectedMessage) && (
                      <img
                        src={getEmailLogo(selectedMessage)!}
                        alt={getEmailCompany(selectedMessage) || ''}
                        className="w-10 h-10 rounded-full border border-slate-100"
                        referrerPolicy="no-referrer"
                        onError={(event) => {
                          (event.target as HTMLImageElement).style.display = 'none';
                        }}
                      />
                    )}
                    <div className="min-w-0">
                      <h2 className="text-2xl tracking-tight font-serif font-bold text-slate-900 truncate">{selectedMessage.subject || selectedThread.latest.subject}</h2>
                      <div className="flex items-center gap-2 mt-1 text-sm text-slate-500 min-w-0">
                        <span className="font-medium text-slate-700 truncate">{selectedMessage.sender || selectedThread.latest.sender}</span>
                        <span className="truncate">&lt;{selectedMessage.senderEmail || selectedThread.latest.senderEmail || 'unknown@example.com'}&gt;</span>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="text-sm text-slate-400 font-medium hidden sm:block">
                  {format(new Date(selectedMessage.date), 'MMM d, yyyy • h:mm a')}
                </div>
              </div>

              {pipelineAlert && !pipelineAlert.in_pipeline && (
                <div className="px-8 pt-4">
                  <div className="max-w-[72rem] mx-auto p-4 bg-amber-50 border border-amber-200 rounded-xl flex items-start gap-3">
                    <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
                    <div className="flex-1">
                      <p className="text-sm text-amber-800 font-medium">{pipelineAlert.suggestion}</p>
                      <button
                        onClick={handleAddToPipeline}
                        className="mt-2 flex items-center gap-1 px-4 py-2 bg-amber-600 text-white text-sm font-medium rounded-lg hover:bg-amber-700 transition-colors"
                      >
                        <Plus className="w-4 h-4" />
                        Add to Pipeline
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {selectedThread.resolved && (
                <div className="px-8 pt-4">
                  <div className="max-w-[72rem] mx-auto p-4 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <CheckCircle2 className="w-5 h-5 text-emerald-500 shrink-0" />
                      <span className="text-sm font-medium text-emerald-800">This update thread is done and compacted into your Done section.</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => void handleResolveThread(false)}
                      className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-white border border-emerald-200 text-sm font-medium text-emerald-700 hover:bg-emerald-100 shrink-0"
                    >
                      <Undo2 className="w-4 h-4" />
                      Undo
                    </button>
                  </div>
                </div>
              )}

              <div className="flex-1 overflow-y-auto p-4 lg:p-5">
                <div className="max-w-[72rem] mx-auto space-y-3">
                  {selectedThread.emails
                    .slice()
                    .reverse()
                    .map((email) => (
                      <div
                        key={email.id}
                        ref={(node) => {
                          messageRefs.current[email.id] = node;
                        }}
                        className={cn(
                          'flex flex-col gap-3 p-4 rounded-2xl border transition-colors overflow-hidden',
                          selectedMessageId === email.id
                            ? 'ring-2 ring-indigo-200 border-indigo-200'
                            : 'bg-white border-slate-100 shadow-sm',
                        )}
                      >
                        <div className="flex items-center justify-between gap-4 border-b border-slate-100/60 pb-3">
                          <div className="flex items-center gap-3 min-w-0">
                            <div className="w-8 h-8 rounded-full bg-slate-100 text-slate-600 flex items-center justify-center font-bold text-xs">
                              {email.sender.charAt(0)}
                            </div>
                            <div className="min-w-0">
                              <div className="font-bold text-slate-900 truncate">{email.sender}</div>
                              <div className="text-xs text-slate-500 truncate">
                                {email.senderEmail || 'unknown@example.com'}
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            <span className={cn('inline-flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-semibold uppercase tracking-wider', classificationColor(email.category, email.resolved))}>
                              {classificationIcon(email.category, email.resolved)}
                              {email.resolved ? 'Done' : categoryLabel(email.category)}
                            </span>
                            <span className="text-xs text-slate-400 font-medium">
                              {format(new Date(email.date), 'MMM d, yyyy • h:mm a')}
                            </span>
                          </div>
                        </div>
                        <div
                          className="text-sm whitespace-pre-wrap break-words [overflow-wrap:anywhere] font-sans text-slate-700 leading-5 cursor-pointer"
                          onClick={() => setSelectedMessageId(email.id)}
                        >
                          {email.body || email.snippet}
                        </div>
                      </div>
                    ))}
                </div>
              </div>

              <div className="p-4 border-t border-slate-100 bg-slate-50">
                <div className="max-w-[72rem] mx-auto flex gap-3 flex-wrap">
                  {selectedMessage.classification === 'action_item' && selectedMessage.actionUrl && (
                    <button
                      onClick={() => openExternal(selectedMessage.actionUrl!)}
                      className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-xl shadow-sm hover:bg-indigo-700 transition-colors"
                    >
                      Take Action
                    </button>
                  )}
                  {selectedMessage.category === 'interview_request' && (
                    <button
                      onClick={() => openInterviewDraft(selectedMessage)}
                      disabled={creatingInterview}
                      className="px-4 py-2 bg-emerald-600 text-white text-sm font-medium rounded-xl shadow-sm hover:bg-emerald-700 transition-colors inline-flex items-center gap-2 disabled:opacity-50"
                    >
                      <CalendarPlus className="w-4 h-4" />
                      Add to Calendar
                    </button>
                  )}
                  <button
                    onClick={() => setCorrectionDialog({ action: 'move_to_conversation', email: selectedMessage })}
                    className="px-4 py-2 bg-white border border-slate-200 text-slate-700 text-sm font-medium rounded-xl shadow-sm hover:bg-slate-50 transition-colors inline-flex items-center gap-2"
                  >
                    <ArrowRight className="w-4 h-4" />
                    Move to Conversations
                  </button>
                  <button
                    onClick={() => handleResolveThread(!selectedThread.resolved)}
                    className="px-4 py-2 bg-white border border-slate-200 text-slate-700 text-sm font-medium rounded-xl shadow-sm hover:bg-slate-50 transition-colors inline-flex items-center gap-2"
                  >
                    {selectedThread.resolved ? <Undo2 className="w-4 h-4" /> : <CheckCircle2 className="w-4 h-4" />}
                    {selectedThread.resolved ? 'Undo Done' : 'Mark as Done'}
                  </button>
                  <button
                    onClick={() => setThreadPendingDeletion(selectedThread)}
                    className="px-4 py-2 bg-white border border-slate-200 text-slate-700 text-sm font-medium rounded-xl shadow-sm hover:bg-slate-50 transition-colors inline-flex items-center gap-2"
                  >
                    <Trash2 className="w-4 h-4" />
                    Delete
                  </button>
                  <button
                    onClick={() => setCorrectionDialog({ action: 'not_relevant', email: selectedMessage })}
                    className="px-4 py-2 bg-white border border-slate-200 text-slate-600 text-sm font-medium rounded-xl shadow-sm hover:bg-slate-50 transition-colors flex items-center gap-2"
                  >
                    <ThumbsDown className="w-4 h-4" />
                    Not Job Related
                  </button>
                  {interviewStatus && (
                    <div className="basis-full text-sm text-slate-500">
                      {interviewStatus}
                    </div>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-center p-8 bg-[#F5F5F0]/50">
              <div className="w-16 h-16 bg-white rounded-2xl shadow-sm border border-slate-200 flex items-center justify-center mb-4">
                <Mail className="w-8 h-8 text-slate-300" />
              </div>
              <h3 className="text-2xl tracking-tight font-serif font-bold text-slate-900 mb-2">No Update Selected</h3>
              <p className="text-slate-500 max-w-sm">Select an inbox update from the list to view the full details.</p>
            </div>
          )}
        </div>
      )}

      <AnimatePresence>
        {correctionDialog && (
          <EmailCorrectionDialog
            action={correctionDialog.action}
            surface="inbox"
            emailId={correctionDialog.email.id}
            subject={correctionDialog.email.subject}
            onClose={() => setCorrectionDialog(null)}
            onSubmit={handleCorrectionSubmit}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {interviewDraft && (
          <DialogShell
            onClose={() => setInterviewDraft(null)}
            titleId="email-interview-draft-title"
            wrapperClassName="fixed inset-0 z-[60] flex items-end justify-center p-0 sm:items-center sm:p-4"
            panelClassName="bg-white w-full max-w-xl max-h-[92dvh] sm:max-h-[min(720px,calc(100dvh-2rem))] rounded-t-[2rem] sm:rounded-3xl shadow-2xl overflow-hidden flex flex-col"
          >
            <div className="shrink-0 border-b border-slate-100 p-4 sm:p-6">
              <h2 id="email-interview-draft-title" className="text-xl font-serif font-bold text-slate-900">
                Add Interview
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                Confirm the date and details before adding this to your calendar.
              </p>
              <p className="mt-2 truncate text-xs text-slate-400">{interviewDraft.email.subject}</p>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
              <label className="block">
                <span className="text-xs font-medium uppercase tracking-[0.18em] text-slate-400">Date and Time</span>
                <input
                  type="datetime-local"
                  value={interviewDraft.scheduledAt}
                  onChange={(event) => setInterviewDraft((prev) => prev ? { ...prev, scheduledAt: event.target.value } : prev)}
                  className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm outline-none focus:border-emerald-400 focus:ring-2 focus:ring-emerald-500/20"
                />
              </label>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block">
                  <span className="text-xs font-medium uppercase tracking-[0.18em] text-slate-400">Duration</span>
                  <input
                    type="number"
                    min="15"
                    step="15"
                    value={interviewDraft.duration}
                    onChange={(event) => setInterviewDraft((prev) => prev ? { ...prev, duration: event.target.value } : prev)}
                    className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm outline-none focus:border-emerald-400 focus:ring-2 focus:ring-emerald-500/20"
                  />
                </label>
                <label className="block">
                  <span className="text-xs font-medium uppercase tracking-[0.18em] text-slate-400">Location / Link</span>
                  <input
                    value={interviewDraft.location}
                    onChange={(event) => setInterviewDraft((prev) => prev ? { ...prev, location: event.target.value } : prev)}
                    className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm outline-none focus:border-emerald-400 focus:ring-2 focus:ring-emerald-500/20"
                  />
                </label>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block">
                  <span className="text-xs font-medium uppercase tracking-[0.18em] text-slate-400">Interviewer</span>
                  <input
                    value={interviewDraft.interviewerName}
                    onChange={(event) => setInterviewDraft((prev) => prev ? { ...prev, interviewerName: event.target.value } : prev)}
                    className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm outline-none focus:border-emerald-400 focus:ring-2 focus:ring-emerald-500/20"
                  />
                </label>
                <label className="block">
                  <span className="text-xs font-medium uppercase tracking-[0.18em] text-slate-400">Email</span>
                  <input
                    type="email"
                    value={interviewDraft.interviewerEmail}
                    onChange={(event) => setInterviewDraft((prev) => prev ? { ...prev, interviewerEmail: event.target.value } : prev)}
                    className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm outline-none focus:border-emerald-400 focus:ring-2 focus:ring-emerald-500/20"
                  />
                </label>
              </div>
              <label className="block">
                <span className="text-xs font-medium uppercase tracking-[0.18em] text-slate-400">Notes</span>
                <textarea
                  rows={3}
                  value={interviewDraft.notes}
                  onChange={(event) => setInterviewDraft((prev) => prev ? { ...prev, notes: event.target.value } : prev)}
                  className="mt-2 w-full resize-y rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 text-sm outline-none focus:border-emerald-400 focus:ring-2 focus:ring-emerald-500/20"
                />
              </label>
              {interviewStatus && (
                <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                  {interviewStatus}
                </div>
              )}
            </div>
            <div className="shrink-0 border-t border-slate-100 bg-white p-4 sm:px-6">
              <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                <button
                  onClick={() => setInterviewDraft(null)}
                  className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  onClick={() => void handleCreateInterviewFromDraft()}
                  disabled={creatingInterview || !interviewDraft.scheduledAt}
                  className="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                >
                  {creatingInterview ? 'Adding...' : 'Add to Calendar'}
                </button>
              </div>
            </div>
          </DialogShell>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {threadPendingDeletion && (
          <DialogShell
            onClose={() => setThreadPendingDeletion(null)}
            titleId="delete-email-thread-title"
            panelClassName="fixed inset-4 md:inset-auto md:top-1/2 md:left-1/2 md:-translate-x-1/2 md:-translate-y-1/2 md:w-full md:max-w-md bg-white rounded-3xl shadow-2xl z-50 flex flex-col overflow-hidden"
          >
            <div className="p-6 border-b border-slate-100">
              <h2 id="delete-email-thread-title" className="text-xl font-serif font-bold text-slate-900">
                Delete From AppTrail
              </h2>
            </div>
            <div className="p-6 space-y-4">
              <p className="text-sm text-slate-600">
                This will remove this email thread from AppTrail and it will not come back on future Gmail syncs. It will remain in your Gmail account.
              </p>
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setThreadPendingDeletion(null)}
                  className="px-4 py-2 bg-white border border-slate-200 text-slate-700 text-sm font-medium rounded-xl"
                >
                  Cancel
                </button>
                <button
                  onClick={() => void handleDeleteThread(threadPendingDeletion)}
                  className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-sm font-medium rounded-xl"
                >
                  Delete
                </button>
              </div>
            </div>
          </DialogShell>
        )}
      </AnimatePresence>
    </div>
  );
}
