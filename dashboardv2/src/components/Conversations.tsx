import { useState, useEffect, useMemo } from 'react';
import { Email, Job } from '../types';
import { format, formatDistanceToNow } from 'date-fns';
import { motion, AnimatePresence } from 'motion/react';
import { Search, Filter, Clock, AlertCircle, CheckCircle2, MessageSquare, ArrowRight, Send, ChevronDown, ChevronUp } from 'lucide-react';
import { cn } from '../lib/utils';
import { markEmailResolved, sendEmail, generateDraft } from '../lib/api';

interface ConversationsProps {
  emails: Email[];
  jobs: Job[];
}

export function Conversations({ emails, jobs }: ConversationsProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [filter, setFilter] = useState<'all' | 'needs_reply' | 'waiting'>('all');
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [expandedThreadId, setExpandedThreadId] = useState<string | null>(null);
  const [isReplying, setIsReplying] = useState(false);
  const [replyText, setReplyText] = useState('');
  const [resolvedThreads, setResolvedThreads] = useState<Set<string>>(new Set());

  // Reset reply state when changing threads
  useEffect(() => {
    setIsReplying(false);
    setReplyText('');
  }, [selectedThreadId]);

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

  const conversations = emails.filter((email) => {
    if (email.type !== 'conversation') return false;
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
        const isResolved = sorted.some(e => e.resolved) || resolvedThreads.has(sorted[0].threadId || sorted[0].id);
        return {
          id: sorted[0].threadId || sorted[0].id,
          emails: sorted,
          latest: sorted[0],
          resolved: isResolved,
        };
      })
      .sort((a, b) => {
        // Resolved threads go to the bottom
        if (a.resolved && !b.resolved) return 1;
        if (!a.resolved && b.resolved) return -1;
        return new Date(b.latest.date).getTime() - new Date(a.latest.date).getTime();
      });
  }, [filteredConversations, resolvedThreads]);

  const selectedThread = threads.find(t => t.id === selectedThreadId);

  const handleMarkResolved = async () => {
    if (!selectedThread) return;
    // Mark all emails in thread as resolved
    for (const email of selectedThread.emails) {
      try {
        await markEmailResolved(email.id);
      } catch (err) {
        console.error('Failed to mark email resolved:', err);
      }
    }
    setResolvedThreads(prev => new Set([...prev, selectedThread.id]));
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
                className={cn("px-3 py-1.5 text-xs font-medium rounded-lg transition-colors flex items-center gap-1.5", filter === 'needs_reply' ? "bg-orange-100 text-orange-700" : "bg-slate-100 text-slate-600 hover:bg-slate-200")}
              >
                <AlertCircle className="w-3 h-3" />
                Needs Reply
              </button>
              <button
                onClick={() => setFilter('waiting')}
                className={cn("px-3 py-1.5 text-xs font-medium rounded-lg transition-colors flex items-center gap-1.5", filter === 'waiting' ? "bg-blue-100 text-blue-700" : "bg-slate-100 text-slate-600 hover:bg-slate-200")}
              >
                <Clock className="w-3 h-3" />
                Waiting on Them
              </button>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {threads.length === 0 ? (
            <div className="text-center py-12">
              <MessageSquare className="w-12 h-12 text-slate-300 mx-auto mb-3" />
              <p className="text-slate-500 font-medium">No conversations found.</p>
            </div>
          ) : (
            threads.map((thread) => {
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
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex items-center gap-3">
                        {(email.companyLogoUrl || job?.logoUrl) ? (
                          <img src={email.companyLogoUrl || job?.logoUrl || ''} alt={email.companyName || job?.company || ''} className="w-8 h-8 rounded-full border border-slate-100" referrerPolicy="no-referrer" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} />
                        ) : (
                          <div className="w-8 h-8 flex items-center justify-center text-xs font-medium rounded-full bg-slate-100 text-slate-500">
                            {(email.companyName || job?.company || '?').charAt(0)}
                          </div>
                        )}
                        <div>
                          <h3 className="text-lg font-serif font-bold text-slate-900 flex items-center gap-2">
                            {displaySender}
                            {hasMultiple && (
                              <span className="text-xs bg-slate-200 text-slate-600 px-1.5 py-0.5 rounded-md font-sans font-medium">
                                {thread.emails.length}
                              </span>
                            )}
                            {thread.resolved && (
                              <span className="text-[10px] bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded-md font-sans font-medium uppercase tracking-wider">
                                Resolved
                              </span>
                            )}
                          </h3>
                          <p className="text-sm font-sans text-slate-500">{job?.company} • {job?.role}</p>
                        </div>
                      </div>
                      <span className="text-[10px] font-medium text-slate-400 whitespace-nowrap">
                        {formatDistanceToNow(new Date(email.date), { addSuffix: true })}
                      </span>
                    </div>

                    <h4 className="text-base font-serif font-bold text-slate-900 mb-1 truncate">{email.subject}</h4>
                    <p className="text-xs text-slate-500 line-clamp-2 mb-3">
                      {email.isFromUser && <span className="font-semibold text-slate-700">You: </span>}
                      {email.snippet}
                    </p>

                    <div className="flex items-center justify-between">
                      {thread.resolved ? (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-emerald-50 text-emerald-700 text-[10px] font-semibold uppercase tracking-wider">
                          <CheckCircle2 className="w-3 h-3" />
                          Resolved
                        </span>
                      ) : email.requiresFollowUp ? (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-orange-50 text-orange-700 text-[10px] font-semibold uppercase tracking-wider">
                          <AlertCircle className="w-3 h-3" />
                          Action Needed
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-slate-100 text-slate-600 text-[10px] font-semibold uppercase tracking-wider">
                          <Clock className="w-3 h-3" />
                          Waiting for reply
                        </span>
                      )}

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
                            <div key={oldEmail.id} className={cn("p-3 rounded-xl border text-sm", oldEmail.isFromUser ? "bg-white border-slate-200 ml-4" : "bg-slate-50 border-slate-100 mr-4")}>
                              <div className="flex justify-between items-center mb-1">
                                <span className="font-semibold text-slate-700">{oldEmail.isFromUser ? 'You' : oldEmail.sender}</span>
                                <span className="text-[10px] text-slate-400">{format(new Date(oldEmail.date), 'MMM d')}</span>
                              </div>
                              <p className="text-xs text-slate-500 line-clamp-2">{oldEmail.snippet}</p>
                            </div>
                          ))}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Detail View */}
      <div className={cn("flex-1 flex flex-col bg-white h-full overflow-hidden", !selectedThreadId && "hidden md:flex")}>
        {selectedThread ? (
          <>
            <div className="p-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50 shrink-0">
              <div className="flex items-center gap-4">
                <button
                  onClick={() => setSelectedThreadId(null)}
                  className="md:hidden p-2 -ml-2 text-slate-500 hover:text-slate-900 hover:bg-slate-200 rounded-lg"
                >
                  <ArrowRight className="w-5 h-5 rotate-180" />
                </button>
                <div>
                  <h2 className="text-2xl tracking-tight font-serif font-bold text-slate-900">{selectedThread.latest.subject}</h2>
                  <div className="flex items-center gap-2 mt-1 text-sm text-slate-500">
                    <span className="font-medium text-slate-700">
                      {selectedThread.emails.find(e => !e.isFromUser)?.sender || selectedThread.latest.sender}
                    </span>
                    <span>&lt;{selectedThread.emails.find(e => !e.isFromUser)?.senderEmail || selectedThread.latest.senderEmail || 'unknown@example.com'}&gt;</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-8">
              <div className="max-w-3xl mx-auto space-y-8">
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
                  <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center gap-3">
                    <CheckCircle2 className="w-5 h-5 text-emerald-500" />
                    <span className="text-sm font-medium text-emerald-800">This conversation has been marked as resolved.</span>
                  </div>
                )}

                {/* Render all emails in thread, oldest first */}
                {[...selectedThread.emails].reverse().map((email) => (
                  <div key={email.id} className={cn("flex flex-col gap-3 p-5 rounded-2xl border", email.isFromUser ? "bg-slate-50 border-slate-200 ml-12" : "bg-white border-slate-100 shadow-sm mr-12")}>
                    <div className="flex items-center justify-between border-b border-slate-100/60 pb-3">
                      <div className="flex items-center gap-3">
                        {email.isFromUser ? (
                          <div className="w-8 h-8 rounded-full bg-slate-200 text-slate-600 flex items-center justify-center font-bold text-xs">YOU</div>
                        ) : (
                          <div className="w-8 h-8 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center font-bold text-xs">
                            {email.sender.charAt(0)}
                          </div>
                        )}
                        <div>
                          <div className="font-bold text-slate-900">{email.isFromUser ? 'You' : email.sender}</div>
                          <div className="text-xs text-slate-500">{email.isFromUser ? 'you@example.com' : (email.senderEmail || 'unknown@example.com')}</div>
                        </div>
                      </div>
                      <span className="text-xs text-slate-400 font-medium">
                        {format(new Date(email.date), 'MMM d, yyyy • h:mm a')}
                      </span>
                    </div>
                    <div className="prose prose-slate prose-sm max-w-none whitespace-pre-wrap font-sans text-slate-700 leading-relaxed">
                      {email.body || email.snippet}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="p-4 border-t border-slate-100 bg-slate-50 shrink-0">
              {isReplying ? (
                <div className="max-w-3xl mx-auto flex flex-col gap-3">
                  <textarea
                    autoFocus
                    value={replyText}
                    onChange={(e) => setReplyText(e.target.value)}
                    placeholder="Type your reply..."
                    className="w-full p-3 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 min-h-[120px] resize-y bg-white"
                  />
                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => { setIsReplying(false); setReplyText(''); }}
                      className="px-4 py-2 bg-white border border-slate-200 text-slate-700 text-sm font-medium rounded-xl shadow-sm hover:bg-slate-50 transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={async () => {
                        if (!replyText.trim() || !selectedThread) return;
                        const otherEmail = selectedThread.emails.find(e => !e.isFromUser);
                        const toEmail = otherEmail?.senderEmail || '';
                        if (!toEmail) return;
                        try {
                          await sendEmail({
                            to: toEmail,
                            subject: `Re: ${selectedThread.latest.subject}`,
                            body: replyText,
                            application_id: selectedThread.latest.jobId || undefined,
                            thread_id: selectedThread.latest.threadId || undefined,
                            reply_to_message_id: selectedThread.latest.id || undefined,
                          });
                          setReplyText('');
                          setIsReplying(false);
                        } catch (err) {
                          console.error('Failed to send reply:', err);
                        }
                      }}
                      disabled={!replyText.trim()}
                      className="px-4 py-2 bg-slate-800 hover:bg-slate-900 disabled:bg-slate-400 text-white text-sm font-medium rounded-xl shadow-sm flex items-center gap-2 transition-colors disabled:cursor-not-allowed"
                    >
                      <Send className="w-4 h-4" />
                      Send Reply
                    </button>
                  </div>
                </div>
              ) : (
                <div className="max-w-3xl mx-auto flex gap-3">
                  <button
                    onClick={() => setIsReplying(true)}
                    className="px-4 py-2 bg-slate-800 hover:bg-slate-900 text-white text-sm font-medium rounded-xl shadow-sm transition-colors"
                  >
                    Reply
                  </button>
                  {!selectedThread.resolved && (
                    <button
                      onClick={handleMarkResolved}
                      className="px-4 py-2 bg-white border border-slate-200 text-slate-700 text-sm font-medium rounded-xl shadow-sm hover:bg-slate-50 transition-colors"
                    >
                      Mark as Resolved
                    </button>
                  )}
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
