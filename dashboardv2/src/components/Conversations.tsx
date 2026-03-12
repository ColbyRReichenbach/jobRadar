import { useState, useEffect, useMemo, useRef } from 'react';
import { Email, Job } from '../types';
import { format, formatDistanceToNow } from 'date-fns';
import { motion, AnimatePresence } from 'motion/react';
import { Search, Clock, AlertCircle, CheckCircle2, MessageSquare, ArrowRight, Send, ChevronDown, ChevronUp, Undo2, Trash2, Users } from 'lucide-react';
import { cn } from '../lib/utils';
import { fetchReplyContext, sendEmail, generateDraft, updateEmail } from '../lib/api';

interface ReplyComposerState {
  to: string;
  cc: string;
  subject: string;
  body: string;
  threadId?: string;
  replyToEmailId?: string;
  mode: 'reply' | 'reply_all';
}

const EMPTY_REPLY_COMPOSER: ReplyComposerState = {
  to: '',
  cc: '',
  subject: '',
  body: '',
  threadId: undefined,
  replyToEmailId: undefined,
  mode: 'reply',
};

interface ConversationsProps {
  emails: Email[];
  jobs: Job[];
  focusRequest?: {
    emailId: string;
    threadId?: string;
    tab: 'emails' | 'conversations';
    token: number;
  } | null;
}

export function Conversations({ emails, jobs, focusRequest }: ConversationsProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [filter, setFilter] = useState<'all' | 'needs_reply' | 'waiting' | 'done'>('all');
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null);
  const [expandedThreadId, setExpandedThreadId] = useState<string | null>(null);
  const [showDoneThreads, setShowDoneThreads] = useState(false);
  const [isReplying, setIsReplying] = useState(false);
  const [replyComposer, setReplyComposer] = useState<ReplyComposerState>(EMPTY_REPLY_COMPOSER);
  const [sendingReply, setSendingReply] = useState(false);
  const [replyError, setReplyError] = useState<string | null>(null);
  const [resolvedThreadOverrides, setResolvedThreadOverrides] = useState<Record<string, boolean>>({});
  const [hiddenEmailIds, setHiddenEmailIds] = useState<Set<string>>(new Set());
  const [localSentEmails, setLocalSentEmails] = useState<Email[]>([]);
  const messageRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // Reset reply state when changing threads
  useEffect(() => {
    setIsReplying(false);
    setReplyComposer(EMPTY_REPLY_COMPOSER);
    setReplyError(null);
  }, [selectedThreadId]);

  useEffect(() => {
    if (!focusRequest) return;
    setSearchQuery('');
    setFilter('all');
    const targetEmail = emails.find((email) => email.id === focusRequest.emailId);
    const targetThreadId = focusRequest.threadId || targetEmail?.threadId || targetEmail?.id || null;
    if (targetThreadId) {
      setSelectedThreadId(targetThreadId);
      setExpandedThreadId(targetThreadId);
      setSelectedMessageId(focusRequest.emailId);
    }
  }, [emails, focusRequest]);

  useEffect(() => {
    if (!selectedMessageId) return;
    const node = messageRefs.current[selectedMessageId];
    node?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [selectedMessageId, selectedThreadId]);

  const noisyConversationDomains = new Set([
    'github.com',
    'notifications.github.com',
    'railway.app',
    'railway.com',
    'vercel.com',
    'account.vercel.com',
    'mailer.vercel.com',
  ]);
  const noisyConversationPattern = /\b(update|digest|newsletter|billing|invoice|receipt|usage|deployment|security|verification|notification|password|team invite|product update)\b/i;

  const effectiveEmails = useMemo(
    () =>
      [...emails, ...localSentEmails].map((email) => {
        const threadId = email.threadId || email.id;
        const overrideResolved = resolvedThreadOverrides[threadId];
        return {
          ...email,
          hidden: email.hidden || hiddenEmailIds.has(email.id),
          resolved: overrideResolved ?? email.resolved,
        };
      }),
    [emails, hiddenEmailIds, localSentEmails, resolvedThreadOverrides],
  );

  const conversations = effectiveEmails.filter((email) => {
    if (email.type !== 'conversation' || email.hidden) return false;
    const senderDomain = (email.senderDomain || email.senderEmail?.split('@')[1] || '').toLowerCase();
    const noisyByDomain = senderDomain ? noisyConversationDomains.has(senderDomain) : false;
    const noisyByContent = noisyConversationPattern.test(`${email.subject} ${email.snippet}`);
    if (email.inPipeline || email.requiresFollowUp) return true;
    return !noisyByDomain && !noisyByContent;
  });

  const filteredConversations = conversations.filter(email => {
    const matchesSearch = email.sender.toLowerCase().includes(searchQuery.toLowerCase()) ||
                          email.subject.toLowerCase().includes(searchQuery.toLowerCase()) ||
                          jobs.find(j => j.id === email.jobId)?.company.toLowerCase().includes(searchQuery.toLowerCase());

    if (!matchesSearch) return false;

    if (filter === 'needs_reply') return email.requiresFollowUp;
    if (filter === 'waiting') return !email.requiresFollowUp;
    if (filter === 'done') return !!email.resolved;

    return true;
  });

  const threads = useMemo(() => {
    const grouped = new Map<string, Email[]>();
    filteredConversations.forEach(email => {
      const key = email.threadId || email.id;
      if (!grouped.has(key)) {
        grouped.set(key, []);
      }
      grouped.get(key)!.push(email);
    });

    return Array.from(grouped.values())
      .map(threadEmails => {
        const sorted = [...threadEmails].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
        const threadId = sorted[0].threadId || sorted[0].id;
        const isResolved = resolvedThreadOverrides[threadId] ?? sorted.some((e) => e.resolved);
        return {
          id: threadId,
          emails: sorted,
          latest: sorted[0],
          resolved: isResolved,
        };
      })
      .sort((a, b) => new Date(b.latest.date).getTime() - new Date(a.latest.date).getTime());
  }, [filteredConversations, resolvedThreadOverrides]);

  const selectedThread = threads.find(t => t.id === selectedThreadId);
  const activeThreads = threads.filter((thread) => !thread.resolved);
  const doneThreads = threads.filter((thread) => thread.resolved);
  const selectedMessage =
    selectedThread?.emails.find((email) => email.id === selectedMessageId) || selectedThread?.latest || null;

  const handleThreadResolvedChange = async (
    threadId: string,
    threadEmails: Email[],
    resolved: boolean,
  ) => {
    setResolvedThreadOverrides((prev) => ({ ...prev, [threadId]: resolved }));
    try {
      await Promise.all(threadEmails.map((email) => updateEmail(email.id, { resolved })));
    } catch (err) {
      setResolvedThreadOverrides((prev) => {
        const next = { ...prev };
        delete next[threadId];
        return next;
      });
      console.error('Failed to mark email resolved:', err);
    }
  };

  const handleMarkResolved = async (resolved: boolean) => {
    if (!selectedThread) return;
    await handleThreadResolvedChange(selectedThread.id, selectedThread.emails, resolved);
  };

  const handleHideThread = async () => {
    if (!selectedThread) return;
    const hiddenIds = selectedThread.emails.map((email) => email.id);
    setHiddenEmailIds((prev) => new Set([...prev, ...hiddenIds]));
    setSelectedThreadId(null);
    setSelectedMessageId(null);
    try {
      await Promise.all(selectedThread.emails.map((email) => updateEmail(email.id, { hidden: true })));
    } catch (err) {
      setHiddenEmailIds((prev) => {
        const next = new Set(prev);
        hiddenIds.forEach((id) => next.delete(id));
        return next;
      });
      console.error('Failed to hide email:', err);
    }
  };

  const handleStartReply = async (mode: 'reply' | 'reply_all') => {
    if (!selectedMessage) return;
    setReplyError(null);
    try {
      const context = await fetchReplyContext(selectedMessage.id, mode === 'reply_all');
      setReplyComposer({
        to: context.to,
        cc: context.cc.join(', '),
        subject: context.subject,
        body: '',
        threadId: context.thread_id,
        replyToEmailId: context.reply_to_email_id,
        mode,
      });
      setIsReplying(true);
    } catch (err) {
      setReplyError(err instanceof Error ? err.message : 'Failed to prepare reply.');
    }
  };

  const handleSendReply = async () => {
    if (!selectedThread || !replyComposer.to.trim() || !replyComposer.subject.trim() || !replyComposer.body.trim()) {
      return;
    }

    setSendingReply(true);
    setReplyError(null);
    try {
      const sentEmail = await sendEmail({
        to: replyComposer.to.trim(),
        cc: replyComposer.cc
          .split(',')
          .map((value) => value.trim())
          .filter(Boolean),
        subject: replyComposer.subject.trim(),
        body: replyComposer.body,
        application_id: selectedThread.latest.jobId || undefined,
        thread_id: replyComposer.threadId,
        reply_to_email_id: replyComposer.replyToEmailId,
      });

      setLocalSentEmails((prev) => {
        if (prev.some((email) => email.id === sentEmail.id)) return prev;
        return [...prev, sentEmail];
      });
      setSelectedThreadId(sentEmail.threadId || selectedThread.id);
      setSelectedMessageId(sentEmail.id);
      setReplyComposer(EMPTY_REPLY_COMPOSER);
      setIsReplying(false);
    } catch (err) {
      setReplyError(err instanceof Error ? err.message : 'Failed to send reply.');
    } finally {
      setSendingReply(false);
    }
  };

  useEffect(() => {
    if (!selectedThreadId) return;
    if (!threads.some((thread) => thread.id === selectedThreadId)) {
      setSelectedThreadId(null);
      setSelectedMessageId(null);
    }
  }, [selectedThreadId, threads]);

  useEffect(() => {
    if (!selectedThread || selectedThread.emails.some((email) => email.id === selectedMessageId)) {
      return;
    }
    setSelectedMessageId(selectedThread.latest.id);
  }, [selectedMessageId, selectedThread]);

  const statusPill = (thread: (typeof threads)[number]) => {
    if (thread.resolved) {
      return {
        label: 'Done',
        className: 'bg-emerald-50 text-emerald-700',
        icon: <CheckCircle2 className="w-3 h-3" />,
      };
    }
    if (thread.latest.requiresFollowUp) {
      return {
        label: 'Needs Reply',
        className: 'bg-amber-50 text-amber-700',
        icon: <AlertCircle className="w-3 h-3" />,
      };
    }
    return {
      label: 'Waiting on Them',
      className: 'bg-red-50 text-red-700',
      icon: <Clock className="w-3 h-3" />,
    };
  };

  return (
    <div className="flex-1 h-full flex bg-[#F5F5F0]">
      {/* List View */}
      <div className={cn("flex flex-col border-r border-slate-200/60 bg-white transition-all duration-300 shrink-0", selectedThreadId ? "w-full md:w-[400px] lg:w-[450px] hidden md:flex" : "w-full md:w-[400px] lg:w-[450px]")}>
        <div className="p-6 border-b border-slate-100">
          <h1 className="text-3xl tracking-tight font-serif font-bold text-slate-900 mb-4">
            Conversations
          </h1>

          <div className="flex flex-col gap-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="text"
                placeholder="Search messages, people, or companies..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-4 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all"
              />
            </div>

            <div className="flex gap-2 flex-wrap">
              <button
                onClick={() => setFilter('all')}
                className={cn("px-3 py-1.5 text-xs font-medium rounded-lg transition-colors", filter === 'all' ? "bg-slate-800 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200")}
              >
                All Active
              </button>
              <button
                onClick={() => setFilter('needs_reply')}
                className={cn("px-3 py-1.5 text-xs font-medium rounded-lg transition-colors flex items-center gap-1.5", filter === 'needs_reply' ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-600 hover:bg-slate-200")}
              >
                <AlertCircle className="w-3 h-3" />
                Needs Reply
              </button>
              <button
                onClick={() => setFilter('waiting')}
                className={cn("px-3 py-1.5 text-xs font-medium rounded-lg transition-colors flex items-center gap-1.5", filter === 'waiting' ? "bg-red-100 text-red-700" : "bg-slate-100 text-slate-600 hover:bg-slate-200")}
              >
                <Clock className="w-3 h-3" />
                Waiting on Them
              </button>
              <button
                onClick={() => setFilter('done')}
                className={cn("px-3 py-1.5 text-xs font-medium rounded-lg transition-colors flex items-center gap-1.5", filter === 'done' ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-600 hover:bg-slate-200")}
              >
                <CheckCircle2 className="w-3 h-3" />
                Done
              </button>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {(filter === 'done' ? doneThreads : activeThreads).length === 0 ? (
            <div className="text-center py-12">
              <MessageSquare className="w-12 h-12 text-slate-300 mx-auto mb-3" />
              <p className="text-slate-500 font-medium">No conversations found.</p>
            </div>
          ) : (
            <>
            {(filter === 'done' ? doneThreads : activeThreads).map((thread) => {
              const email = thread.latest;
              const job = jobs.find(j => j.id === email.jobId);
              const isSelected = selectedThreadId === thread.id;
              const isExpanded = expandedThreadId === thread.id;
              const hasMultiple = thread.emails.length > 1;

              const otherPersonEmail = thread.emails.find(e => !e.isFromUser);
              const displaySender = otherPersonEmail ? otherPersonEmail.sender : email.sender;

              return (
                <div key={thread.id} className="flex flex-col gap-1">
                  <motion.div
                    onClick={() => {
                      setSelectedThreadId(thread.id);
                      setSelectedMessageId(thread.latest.id);
                      if (hasMultiple) {
                        setExpandedThreadId(isExpanded ? null : thread.id);
                      }
                    }}
                    className={cn(
                      "p-4 rounded-2xl cursor-pointer transition-all border",
                      thread.resolved
                        ? "bg-slate-50 border-slate-100 opacity-60"
                        : isSelected
                          ? "bg-indigo-50 border-indigo-200 shadow-sm"
                          : "bg-white border-slate-100 hover:border-slate-300 hover:shadow-sm"
                    )}
                  >
                    <div className="flex items-start justify-between gap-3 mb-2">
                      <div className="flex items-center gap-3 min-w-0">
                        {(email.companyLogoUrl || job?.logoUrl) ? (
                          <img src={email.companyLogoUrl || job?.logoUrl || ''} alt={email.companyName || job?.company || ''} className="w-8 h-8 rounded-full border border-slate-100" referrerPolicy="no-referrer" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} />
                        ) : (
                          <div className="w-8 h-8 flex items-center justify-center text-xs font-medium rounded-full bg-slate-100 text-slate-500">
                            {(email.companyName || job?.company || '?').charAt(0)}
                          </div>
                        )}
                        <div className="min-w-0">
                          <h3 className="text-lg font-serif font-bold text-slate-900 flex items-center gap-2 min-w-0">
                            <span className="truncate">{displaySender}</span>
                            {hasMultiple && (
                              <span className="text-xs bg-slate-200 text-slate-600 px-1.5 py-0.5 rounded-md font-sans font-medium">
                                {thread.emails.length}
                              </span>
                            )}
                            {thread.resolved && (
                              <span className="text-[10px] bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded-md font-sans font-medium uppercase tracking-wider">
                                Done
                              </span>
                            )}
                          </h3>
                          <p className="text-sm font-sans text-slate-500 truncate">{job?.company || email.companyName || 'Conversation'}{job?.role ? ` • ${job.role}` : ''}</p>
                        </div>
                      </div>
                      <span className="text-[10px] font-medium text-slate-400 whitespace-nowrap">
                        {formatDistanceToNow(new Date(email.date), { addSuffix: true })}
                      </span>
                    </div>

                    <h4 className="text-base font-serif font-bold text-slate-900 mb-1 truncate">{email.subject}</h4>
                    <p className="text-xs text-slate-500 line-clamp-2 mb-3 [overflow-wrap:anywhere]">
                      {email.isFromUser && <span className="font-semibold text-slate-700">You: </span>}
                      {email.snippet}
                    </p>

                    <div className="flex items-center justify-between">
                      <span className={cn("inline-flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-semibold uppercase tracking-wider", statusPill(thread).className)}>
                        {statusPill(thread).icon}
                        {statusPill(thread).label}
                      </span>

                      {hasMultiple && (
                        <div className="text-slate-400 hover:text-slate-600">
                          {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                        </div>
                      )}
                    </div>
                  </motion.div>

                  {/* Expanded Thread View in Left Panel */}
                  <AnimatePresence>
                    {isExpanded && hasMultiple && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="overflow-hidden"
                      >
                        <div className="pl-6 pr-2 py-2 space-y-2 border-l-2 border-indigo-100 ml-4 max-h-[250px] overflow-y-auto">
                          {thread.emails.slice(1).map((oldEmail) => (
                            <button
                              type="button"
                              key={oldEmail.id}
                              onClick={(event) => {
                                event.stopPropagation();
                                setSelectedThreadId(thread.id);
                                setSelectedMessageId(oldEmail.id);
                              }}
                              className={cn(
                                "w-full text-left p-3 rounded-xl border text-sm transition-colors",
                                selectedMessageId === oldEmail.id
                                  ? "bg-indigo-50 border-indigo-200"
                                  : oldEmail.isFromUser
                                    ? "bg-white border-slate-200 ml-2"
                                    : "bg-slate-50 border-slate-100 mr-2"
                              )}
                            >
                              <div className="flex justify-between items-center mb-1">
                                <span className="font-semibold text-slate-700">{oldEmail.isFromUser ? 'You' : oldEmail.sender}</span>
                                <span className="text-[10px] text-slate-400">{format(new Date(oldEmail.date), 'MMM d')}</span>
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
            })
            }
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
                      {doneThreads.map((thread) => {
                        const email = thread.latest;
                        return (
                          <button
                            key={thread.id}
                            type="button"
                            onClick={() => {
                              setSelectedThreadId(thread.id);
                              setSelectedMessageId(thread.latest.id);
                            }}
                            className="w-full text-left p-4 rounded-2xl border border-slate-100 bg-white hover:border-slate-300"
                          >
                            <div className="flex items-center justify-between gap-3">
                              <div className="min-w-0">
                                <div className="text-sm font-serif font-bold text-slate-900 truncate">{email.sender}</div>
                                <div className="text-xs text-slate-500 truncate">{email.subject}</div>
                              </div>
                              <div className="flex items-center gap-2 shrink-0">
                                <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-emerald-50 text-emerald-700 text-[10px] font-semibold uppercase tracking-wider">
                                  <CheckCircle2 className="w-3 h-3" />
                                  Done
                                </span>
                                <button
                                  type="button"
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    void handleThreadResolvedChange(thread.id, thread.emails, false);
                                  }}
                                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-white border border-slate-200 text-[11px] font-medium text-slate-600 hover:bg-slate-50"
                                >
                                  <Undo2 className="w-3 h-3" />
                                  Undo
                                </button>
                              </div>
                            </div>
                          </button>
                        );
                      })}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            )}
            </>
          )}
        </div>
      </div>

      {/* Detail View */}
      <div className={cn("flex-1 flex flex-col bg-white h-full overflow-hidden", !selectedThreadId && "hidden md:flex")}>
        {selectedThread ? (
          <>
            <div className="p-5 border-b border-slate-100 flex items-center justify-between bg-slate-50/50 shrink-0">
              <div className="flex items-center gap-4">
                <button
                  onClick={() => {
                    setSelectedThreadId(null);
                    setSelectedMessageId(null);
                  }}
                  className="md:hidden p-2 -ml-2 text-slate-500 hover:text-slate-900 hover:bg-slate-200 rounded-lg"
                >
                  <ArrowRight className="w-5 h-5 rotate-180" />
                </button>
                <div className="min-w-0">
                  <h2 className="text-2xl tracking-tight font-serif font-bold text-slate-900 truncate">{selectedThread.latest.subject}</h2>
                  <div className="flex items-center gap-2 mt-1 text-sm text-slate-500 min-w-0">
                    <span className="font-medium text-slate-700 truncate">
                      {selectedThread.emails.find(e => !e.isFromUser)?.sender || selectedThread.latest.sender}
                    </span>
                    <span className="truncate">&lt;{selectedThread.emails.find(e => !e.isFromUser)?.senderEmail || selectedThread.latest.senderEmail || 'unknown@example.com'}&gt;</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4 lg:p-5">
              <div className="max-w-[72rem] mx-auto space-y-3">
                {selectedThread.latest.requiresFollowUp && !selectedThread.resolved && (
                  <div className="p-4 bg-orange-50 border border-orange-200 rounded-xl flex items-start gap-3">
                    <AlertCircle className="w-5 h-5 text-orange-500 shrink-0 mt-0.5" />
                    <div>
                      <h4 className="text-sm font-bold text-orange-800">Follow-up Recommended</h4>
                      <p className="text-sm text-orange-700 mt-1">It's been a few days since the last message. Consider sending a polite follow-up to keep the conversation active.</p>
                      <button
                        onClick={async () => {
                          const otherEmail = selectedThread.emails.find(e => !e.isFromUser);
                          const job = jobs.find(j => j.id === (otherEmail?.jobId || selectedThread.latest.jobId));
                          try {
                            const draft = await generateDraft({
                              application_id: otherEmail?.jobId || selectedThread.latest.jobId || undefined,
                              contact_email: otherEmail?.senderEmail || undefined,
                              draft_type: 'follow_up',
                            });
                            setReplyText(draft.body);
                            setIsReplying(true);
                          } catch (err) {
                            console.error('Failed to generate draft:', err);
                          }
                        }}
                        className="mt-3 px-4 py-2 bg-white border border-orange-200 text-orange-700 hover:bg-orange-50 text-sm font-medium rounded-lg shadow-sm transition-colors"
                      >
                        Draft Follow-up with AI
                      </button>
                    </div>
                  </div>
                )}

                {selectedThread.resolved && (
                  <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <CheckCircle2 className="w-5 h-5 text-emerald-500 shrink-0" />
                      <span className="text-sm font-medium text-emerald-800">This conversation is done and collapsed into your Done section.</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => void handleMarkResolved(false)}
                      className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-white border border-emerald-200 text-sm font-medium text-emerald-700 hover:bg-emerald-100 shrink-0"
                    >
                      <Undo2 className="w-4 h-4" />
                      Undo
                    </button>
                  </div>
                )}

                {/* Render all emails in thread, oldest first */}
                {[...selectedThread.emails].reverse().map((email) => (
                  <div
                    key={email.id}
                    ref={(node) => {
                      messageRefs.current[email.id] = node;
                    }}
                    className={cn(
                      "flex flex-col gap-3 p-4 rounded-2xl border transition-colors overflow-hidden",
                      selectedMessageId === email.id
                        ? "ring-2 ring-indigo-200 border-indigo-200"
                        : email.isFromUser
                          ? "bg-slate-50 border-slate-200 ml-2"
                          : "bg-white border-slate-100 shadow-sm mr-2"
                    )}
                  >
                    <div className="flex items-center justify-between border-b border-slate-100/60 pb-3 gap-4">
                      <div className="flex items-center gap-3 min-w-0">
                        {email.isFromUser ? (
                          <div className="w-8 h-8 rounded-full bg-slate-200 text-slate-600 flex items-center justify-center font-bold text-xs">YOU</div>
                        ) : (
                          <div className="w-8 h-8 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center font-bold text-xs">
                            {email.sender.charAt(0)}
                          </div>
                        )}
                        <div className="min-w-0">
                          <div className="font-bold text-slate-900 truncate">{email.isFromUser ? 'You' : email.sender}</div>
                          <div className="text-xs text-slate-500 truncate">{email.isFromUser ? 'you@example.com' : (email.senderEmail || 'unknown@example.com')}</div>
                        </div>
                      </div>
                      <span className="text-xs text-slate-400 font-medium shrink-0">
                        {format(new Date(email.date), 'MMM d, yyyy • h:mm a')}
                      </span>
                    </div>
                    <div className="text-sm whitespace-pre-wrap break-words [overflow-wrap:anywhere] font-sans text-slate-700 leading-5 max-w-none">
                      {email.body || email.snippet}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="p-4 border-t border-slate-100 bg-slate-50 shrink-0">
              {isReplying ? (
                <div className="max-w-[72rem] mx-auto flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <h4 className="text-sm font-semibold text-slate-900">
                        {replyComposer.mode === 'reply_all' ? 'Reply All' : 'Reply'}
                      </h4>
                      <p className="text-xs text-slate-500">
                        This reply will be sent inside the Gmail thread.
                      </p>
                    </div>
                  </div>
                  {replyError && (
                    <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                      {replyError}
                    </div>
                  )}
                  <div className="grid gap-3 md:grid-cols-[80px_1fr] md:items-center">
                    <label className="text-xs font-medium uppercase tracking-[0.18em] text-slate-400">To</label>
                    <input
                      autoFocus
                      type="email"
                      value={replyComposer.to}
                      onChange={(e) => setReplyComposer((prev) => ({ ...prev, to: e.target.value }))}
                      className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                    />
                  </div>
                  <div className="grid gap-3 md:grid-cols-[80px_1fr] md:items-center">
                    <label className="text-xs font-medium uppercase tracking-[0.18em] text-slate-400">Cc</label>
                    <input
                      type="text"
                      value={replyComposer.cc}
                      onChange={(e) => setReplyComposer((prev) => ({ ...prev, cc: e.target.value }))}
                      placeholder="comma-separated recipients"
                      className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                    />
                  </div>
                  <div className="grid gap-3 md:grid-cols-[80px_1fr] md:items-center">
                    <label className="text-xs font-medium uppercase tracking-[0.18em] text-slate-400">Subject</label>
                    <input
                      type="text"
                      value={replyComposer.subject}
                      onChange={(e) => setReplyComposer((prev) => ({ ...prev, subject: e.target.value }))}
                      className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                    />
                  </div>
                  <div className="grid gap-3 md:grid-cols-[80px_1fr]">
                    <label className="pt-3 text-xs font-medium uppercase tracking-[0.18em] text-slate-400">Message</label>
                    <textarea
                      value={replyComposer.body}
                      onChange={(e) => setReplyComposer((prev) => ({ ...prev, body: e.target.value }))}
                      placeholder="Write your reply..."
                      className="min-h-[180px] w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 resize-y"
                    />
                  </div>
                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => {
                        setIsReplying(false);
                        setReplyComposer(EMPTY_REPLY_COMPOSER);
                        setReplyError(null);
                      }}
                      className="px-4 py-2 bg-white border border-slate-200 text-slate-700 text-sm font-medium rounded-xl shadow-sm hover:bg-slate-50 transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={() => void handleSendReply()}
                      disabled={sendingReply || !replyComposer.to.trim() || !replyComposer.subject.trim() || !replyComposer.body.trim()}
                      className="px-4 py-2 bg-slate-800 hover:bg-slate-900 disabled:bg-slate-400 text-white text-sm font-medium rounded-xl shadow-sm flex items-center gap-2 transition-colors disabled:cursor-not-allowed"
                    >
                      <Send className="w-4 h-4" />
                      {sendingReply ? 'Sending...' : 'Send Reply'}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="max-w-[72rem] mx-auto flex flex-col gap-3">
                  {replyError && (
                    <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                      {replyError}
                    </div>
                  )}
                  <div className="flex gap-3 flex-wrap">
                    <button
                      onClick={() => void handleStartReply('reply')}
                      className="px-4 py-2 bg-slate-800 hover:bg-slate-900 text-white text-sm font-medium rounded-xl shadow-sm transition-colors"
                    >
                      Reply
                    </button>
                    <button
                      onClick={() => void handleStartReply('reply_all')}
                      className="px-4 py-2 bg-white border border-slate-200 text-slate-700 text-sm font-medium rounded-xl shadow-sm hover:bg-slate-50 transition-colors inline-flex items-center gap-2"
                    >
                      <Users className="w-4 h-4" />
                      Reply All
                    </button>
                    <button
                      onClick={() => handleMarkResolved(!selectedThread.resolved)}
                      className="px-4 py-2 bg-white border border-slate-200 text-slate-700 text-sm font-medium rounded-xl shadow-sm hover:bg-slate-50 transition-colors inline-flex items-center gap-2"
                    >
                      {selectedThread.resolved ? <Undo2 className="w-4 h-4" /> : <CheckCircle2 className="w-4 h-4" />}
                      {selectedThread.resolved ? 'Undo Done' : 'Mark as Done'}
                    </button>
                    <button
                      onClick={handleHideThread}
                      className="px-4 py-2 bg-white border border-slate-200 text-slate-700 text-sm font-medium rounded-xl shadow-sm hover:bg-slate-50 transition-colors inline-flex items-center gap-2"
                    >
                      <Trash2 className="w-4 h-4" />
                      Delete
                    </button>
                  </div>
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-center p-8 bg-[#F5F5F0]/50">
            <div className="w-16 h-16 bg-white rounded-2xl shadow-sm border border-slate-200 flex items-center justify-center mb-4">
              <MessageSquare className="w-8 h-8 text-slate-300" />
            </div>
            <h3 className="text-2xl tracking-tight font-serif font-bold text-slate-900 mb-2">No Conversation Selected</h3>
            <p className="text-slate-500 max-w-sm">Select a conversation from the list to view the full thread and reply.</p>
          </div>
        )}
      </div>
    </div>
  );
}
