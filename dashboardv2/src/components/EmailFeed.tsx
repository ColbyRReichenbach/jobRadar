import React, { CSSProperties, useEffect, useMemo, useRef, useState } from 'react';
import { Email, Job } from '../types';
import { format } from 'date-fns';
import { cn } from '../lib/utils';
import { Mail, AlertCircle, CheckCircle2, XCircle, Clock, ArrowRight, ChevronRight, ChevronLeft, ThumbsDown, AlertTriangle, Plus, Search } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { submitEmailFeedback, checkEmailPipeline, createJob } from '../lib/api';
import { FixedSizeList, ListChildComponentProps } from 'react-window';

interface EmailFeedProps {
  emails: Email[];
  jobs: Job[];
  isCollapsed: boolean;
  setIsCollapsed: (c: boolean) => void;
  forceOpen?: boolean;
}

const EMAIL_ROW_HEIGHT = 184;

function openExternal(url: string) {
  window.open(url, '_blank', 'noopener,noreferrer');
}

interface EmailListItemData {
  emails: Email[];
  jobs: Job[];
  selectedEmailId: string | null;
  onSelectEmail: (email: Email) => void;
  onNotJobRelated: (event: React.MouseEvent, email: Email) => void;
  getClassificationColor: (classification: Email['classification']) => string;
  getClassificationIcon: (classification: Email['classification']) => JSX.Element | undefined;
  getEmailLogo: (email: Email) => string | undefined;
  getEmailCompany: (email: Email) => string | undefined;
}

function EmailListRow({ index, style, data }: ListChildComponentProps<EmailListItemData>) {
  const email = data.emails[index];
  const logoUrl = data.getEmailLogo(email);
  const companyName = data.getEmailCompany(email);
  const isSelected = data.selectedEmailId === email.id;
  const rowStyle: CSSProperties = {
    ...style,
    padding: '0 16px 8px 16px',
  };

  return (
    <div style={rowStyle}>
      <div
        onClick={() => data.onSelectEmail(email)}
        className={cn(
          "p-4 transition-all cursor-pointer rounded-2xl border group relative",
          isSelected
            ? "bg-indigo-50 border-indigo-200 shadow-sm"
            : email.read
              ? "bg-white border-slate-100 hover:border-slate-300 hover:shadow-sm"
              : "bg-indigo-50/30 border-indigo-100 hover:border-indigo-200 hover:shadow-sm"
        )}
      >
        {!email.jobId && email.companyName && (
          <div className="absolute top-2 right-2">
            <div className="w-2 h-2 bg-amber-400 rounded-full" title="Not in pipeline" />
          </div>
        )}

        <div className="flex items-start justify-between mb-2">
          <div className="flex items-center gap-2 min-w-0">
            {logoUrl ? (
              <img
                src={logoUrl}
                alt={companyName || ''}
                className="w-6 h-6 rounded-full border border-slate-100 shrink-0"
                referrerPolicy="no-referrer"
                onError={(event) => { (event.target as HTMLImageElement).style.display = 'none'; }}
              />
            ) : (
              <div className="w-6 h-6 flex items-center justify-center text-[10px] font-medium rounded-full bg-slate-100 text-slate-500 shrink-0">
                {(companyName || email.sender || '?').charAt(0)}
              </div>
            )}
            <span className="text-sm font-serif font-bold text-slate-900 truncate">{email.sender}</span>
          </div>
          <span className="text-[10px] font-medium text-slate-400 shrink-0">
            {format(new Date(email.date), 'MMM d')}
          </span>
        </div>

        {companyName && (
          <p className="text-[10px] text-slate-400 font-medium mb-1 truncate">{companyName}</p>
        )}

        <h3 className="mb-1 text-base font-serif font-bold text-slate-900 truncate">
          {email.subject}
        </h3>

        <p className="text-xs line-clamp-2 mb-3 leading-relaxed text-slate-500">
          {email.snippet}
        </p>

        <div className="flex items-center justify-between mt-2 pt-3 border-t border-slate-100/50">
          <div className={cn(
            "flex items-center gap-1.5 px-2 py-1 text-[10px] uppercase tracking-wider rounded-md font-semibold",
            data.getClassificationColor(email.classification)
          )}>
            {data.getClassificationIcon(email.classification)}
            {email.classification.replace('_', ' ')}
          </div>

          <button
            onClick={(event) => data.onNotJobRelated(event, email)}
            className="opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-slate-600 rounded transition-opacity"
            title="Not job related"
          >
            <ThumbsDown className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}

export function EmailFeed({ emails, jobs, isCollapsed, setIsCollapsed, forceOpen }: EmailFeedProps) {
  const [selectedEmail, setSelectedEmail] = useState<Email | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [filter, setFilter] = useState<'all' | 'pipeline' | 'action_needed' | 'unlinked'>('all');
  const [pipelineAlert, setPipelineAlert] = useState<{
    in_pipeline: boolean;
    suggestion?: string;
    company_name?: string;
  } | null>(null);
  const [dismissedEmails, setDismissedEmails] = useState<Set<string>>(new Set());
  const listContainerRef = useRef<HTMLDivElement>(null);
  const [listHeight, setListHeight] = useState(0);

  const getClassificationIcon = (classification: Email['classification']) => {
    switch (classification) {
      case 'interview': return <CheckCircle2 className="w-4 h-4 text-emerald-500" />;
      case 'rejection': return <XCircle className="w-4 h-4 text-red-500" />;
      case 'action_item': return <AlertCircle className="w-4 h-4 text-orange-500" />;
      case 'update': return <Clock className="w-4 h-4 text-blue-500" />;
    }
  };

  const getClassificationColor = (classification: Email['classification']) => {
    switch (classification) {
      case 'interview': return 'bg-emerald-50 text-emerald-700 border-emerald-200';
      case 'rejection': return 'bg-red-50 text-red-700 border-red-200';
      case 'action_item': return 'bg-orange-50 text-orange-700 border-orange-200';
      case 'update': return 'bg-blue-50 text-blue-700 border-blue-200';
    }
  };

  const collapsed = forceOpen ? false : isCollapsed;

  const feedEmails = emails.filter(e => e.type !== 'conversation' && !dismissedEmails.has(e.id));
  const filteredInboxEmails = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return feedEmails.filter((email) => {
      const matchesSearch = !query || [
        email.sender,
        email.subject,
        email.companyName,
        email.senderEmail,
        email.snippet,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
        .includes(query);

      if (!matchesSearch) return false;
      if (filter === 'pipeline') return !!email.jobId;
      if (filter === 'action_needed') return email.classification === 'action_item' || !!email.actionUrl;
      if (filter === 'unlinked') return !email.jobId;
      return true;
    });
  }, [feedEmails, filter, searchQuery]);

  useEffect(() => {
    if (selectedEmail && !filteredInboxEmails.some((email) => email.id === selectedEmail.id)) {
      setSelectedEmail(null);
      setPipelineAlert(null);
    }
  }, [filteredInboxEmails, selectedEmail]);

  useEffect(() => {
    const element = listContainerRef.current;
    if (!element) return;

    const updateHeight = () => {
      setListHeight(element.getBoundingClientRect().height);
    };

    updateHeight();

    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', updateHeight);
      return () => window.removeEventListener('resize', updateHeight);
    }

    const observer = new ResizeObserver(updateHeight);
    observer.observe(element);
    return () => observer.disconnect();
  }, [collapsed, forceOpen, selectedEmail]);

  const handleNotJobRelated = async (e: React.MouseEvent, email: Email) => {
    e.stopPropagation();
    try {
      await submitEmailFeedback(email.id, false);
      setDismissedEmails(prev => new Set([...prev, email.id]));
      if (selectedEmail?.id === email.id) setSelectedEmail(null);
    } catch (err) {
      console.error('Failed to submit feedback:', err);
    }
  };

  const handleSelectEmail = async (email: Email) => {
    setSelectedEmail(email);
    setPipelineAlert(null);

    // Check pipeline status if not already linked to an application
    if (!email.jobId && email.companyName) {
      try {
        const result = await checkEmailPipeline(email.id);
        if (!result.in_pipeline) {
          setPipelineAlert(result);
        }
      } catch {
        // Ignore pipeline check failures
      }
    }
  };

  const handleAddToPipeline = async () => {
    if (!selectedEmail || !pipelineAlert?.company_name) return;
    try {
      await createJob({
        company: pipelineAlert.company_name,
        role: selectedEmail.subject,
        status: 'applied',
      });
      setPipelineAlert(null);
    } catch (err) {
      console.error('Failed to add to pipeline:', err);
    }
  };

  const getEmailLogo = (email: Email) => {
    // Priority: company logo from email > matched job logo
    if (email.companyLogoUrl) return email.companyLogoUrl;
    const job = jobs.find(j => j.id === email.jobId);
    return job?.logoUrl;
  };

  const getEmailCompany = (email: Email) => {
    if (email.companyName) return email.companyName;
    const job = jobs.find(j => j.id === email.jobId);
    return job?.company;
  };

  const listItemData: EmailListItemData = {
    emails: filteredInboxEmails,
    jobs,
    selectedEmailId: selectedEmail?.id || null,
    onSelectEmail: handleSelectEmail,
    onNotJobRelated: handleNotJobRelated,
    getClassificationColor,
    getClassificationIcon,
    getEmailLogo,
    getEmailCompany,
  };

  return (
    <div className={cn("flex h-full bg-[#F5F5F0]", forceOpen ? "w-full" : "")}>
      {/* List View */}
      <motion.div
        initial={false}
        animate={forceOpen ? undefined : { width: collapsed ? 64 : 320 }}
        style={forceOpen ? { width: undefined } : undefined}
        className={cn(
          "flex flex-col shrink-0 transition-all duration-300 bg-white border-r border-slate-200/60 relative",
          forceOpen ? (selectedEmail ? "w-full md:w-[400px] lg:w-[450px] hidden md:flex" : "w-full md:w-[400px] lg:w-[450px]") : ""
        )}
      >
        {!forceOpen && (
          <button
            onClick={() => setIsCollapsed(!collapsed)}
            className="absolute -left-3 top-8 w-6 h-6 bg-white border border-slate-200 rounded-full flex items-center justify-center shadow-sm z-10 hover:bg-slate-50"
          >
            {collapsed ? <ChevronLeft className="w-3 h-3 text-slate-600" /> : <ChevronRight className="w-3 h-3 text-slate-600" />}
          </button>
        )}

        <div className={cn("p-6 border-b border-slate-100", collapsed ? "flex justify-center px-0 items-center" : (forceOpen ? "block" : "flex items-center justify-between"))}>
          {forceOpen ? (
            <>
              <div className="flex items-center justify-between mb-2">
                <h1 className="text-3xl tracking-tight font-serif font-bold text-slate-900">
                  Inbox
                </h1>
                <span className="text-xs px-2 py-0.5 bg-indigo-100 text-indigo-700 rounded-full font-semibold">
                  {feedEmails.filter(e => !e.read).length} new
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
                  <button
                    onClick={() => setFilter('all')}
                    className={cn("px-3 py-1.5 text-xs font-medium rounded-lg transition-colors", filter === 'all' ? "bg-slate-800 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200")}
                  >
                    All Updates
                  </button>
                  <button
                    onClick={() => setFilter('pipeline')}
                    className={cn("px-3 py-1.5 text-xs font-medium rounded-lg transition-colors", filter === 'pipeline' ? "bg-indigo-100 text-indigo-700" : "bg-slate-100 text-slate-600 hover:bg-slate-200")}
                  >
                    In Pipeline
                  </button>
                  <button
                    onClick={() => setFilter('action_needed')}
                    className={cn("px-3 py-1.5 text-xs font-medium rounded-lg transition-colors", filter === 'action_needed' ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-600 hover:bg-slate-200")}
                  >
                    Action Needed
                  </button>
                  <button
                    onClick={() => setFilter('unlinked')}
                    className={cn("px-3 py-1.5 text-xs font-medium rounded-lg transition-colors", filter === 'unlinked' ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-600 hover:bg-slate-200")}
                  >
                    Needs Matching
                  </button>
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
                <span className="text-xs px-2 py-0.5 bg-indigo-100 text-indigo-700 rounded-full font-semibold">
                  {feedEmails.filter(e => !e.read).length} new
                </span>
              )}
            </>
          )}
        </div>

        <AnimatePresence mode="wait">
          {!forceOpen && selectedEmail ? (
            /* Inline detail view in sidebar */
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
                  onClick={() => { setSelectedEmail(null); setPipelineAlert(null); }}
                  className="p-1.5 text-slate-500 hover:text-slate-900 hover:bg-slate-200 rounded-lg transition-colors"
                >
                  <ArrowRight className="w-4 h-4 rotate-180" />
                </button>
                <span className="text-xs font-medium text-slate-500 truncate">Back to updates</span>
              </div>

              <div className="flex-1 overflow-y-auto p-4">
                {/* Pipeline Alert */}
                {pipelineAlert && !pipelineAlert.in_pipeline && (
                  <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-xl">
                    <div className="flex items-start gap-2">
                      <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-amber-800 font-medium">{pipelineAlert.suggestion}</p>
                        <button
                          onClick={handleAddToPipeline}
                          className="mt-2 flex items-center gap-1 px-3 py-1.5 bg-amber-600 text-white text-xs font-medium rounded-lg hover:bg-amber-700 transition-colors"
                        >
                          <Plus className="w-3 h-3" />
                          Add to Pipeline
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                <div className="mb-3">
                  {/* Company logo badge */}
                  {getEmailLogo(selectedEmail) && (
                    <div className="flex items-center gap-2 mb-2">
                      <img
                        src={getEmailLogo(selectedEmail)!}
                        alt={getEmailCompany(selectedEmail) || ''}
                        className="w-6 h-6 rounded-full border border-slate-100"
                        referrerPolicy="no-referrer"
                        onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                      />
                      <span className="text-xs font-medium text-slate-500">{getEmailCompany(selectedEmail)}</span>
                    </div>
                  )}
                  <div className={cn(
                    "inline-flex items-center gap-1.5 px-2 py-1 text-[10px] uppercase tracking-wider rounded-md font-semibold mb-2",
                    getClassificationColor(selectedEmail.classification)
                  )}>
                    {getClassificationIcon(selectedEmail.classification)}
                    {selectedEmail.classification.replace('_', ' ')}
                  </div>
                  <h3 className="text-lg font-serif font-bold text-slate-900 leading-tight">
                    {selectedEmail.subject}
                  </h3>
                  {selectedEmail.summary && (
                    <p className="text-xs text-slate-500 mt-1 italic">{selectedEmail.summary}</p>
                  )}
                </div>

                <div className="flex items-center gap-2 mb-4 pb-3 border-b border-slate-100">
                  <div className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center text-xs font-bold text-slate-500">
                    {selectedEmail.sender.charAt(0).toUpperCase()}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-slate-900 truncate">{selectedEmail.sender}</div>
                    <div className="text-[11px] text-slate-400 truncate">
                      {selectedEmail.senderEmail || 'unknown'} · {format(new Date(selectedEmail.date), 'MMM d, h:mm a')}
                    </div>
                  </div>
                </div>

                <div className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap break-words overflow-hidden">
                  {selectedEmail.body || selectedEmail.snippet}
                </div>
              </div>

              <div className="p-3 border-t border-slate-100 flex gap-2">
                {selectedEmail.classification === 'action_item' && selectedEmail.actionUrl && (
                  <button
                    onClick={() => openExternal(selectedEmail.actionUrl)}
                    className="flex-1 px-3 py-2 bg-indigo-600 text-white text-xs font-medium rounded-xl shadow-sm hover:bg-indigo-700 transition-colors"
                  >
                    Take Action
                  </button>
                )}
                <button
                  onClick={(e) => handleNotJobRelated(e, selectedEmail)}
                  className="px-3 py-2 bg-slate-100 text-slate-600 text-xs font-medium rounded-xl hover:bg-slate-200 transition-colors flex items-center gap-1"
                >
                  <ThumbsDown className="w-3 h-3" />
                  Not Job Related
                </button>
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="list"
              initial={false}
              className="flex-1 overflow-hidden"
            >
              {collapsed ? (
                <div className="h-full overflow-y-auto p-4 space-y-2">
                  {feedEmails.map((email) => (
                    <div key={email.id} className="w-10 h-10 mx-auto bg-indigo-50 rounded-full flex items-center justify-center relative cursor-pointer" onClick={() => setIsCollapsed(false)}>
                      {getClassificationIcon(email.classification)}
                      {!email.read && <div className="absolute top-0 right-0 w-2.5 h-2.5 bg-indigo-500 rounded-full border-2 border-white" />}
                    </div>
                  ))}
                </div>
              ) : (
                <div ref={listContainerRef} className="h-full overflow-hidden">
                  {filteredInboxEmails.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center px-8 text-center text-slate-400">
                      <Mail className="w-10 h-10 mb-3 opacity-30" />
                      <p className="text-base font-serif text-slate-500">No inbox updates found.</p>
                      <p className="text-sm mt-1">
                        {searchQuery || filter !== 'all'
                          ? 'Adjust your search or filters.'
                          : 'New application updates will appear here after Gmail sync.'}
                      </p>
                    </div>
                  ) : listHeight > 0 && (
                    <FixedSizeList
                      height={listHeight}
                      width="100%"
                      itemCount={filteredInboxEmails.length}
                      itemSize={EMAIL_ROW_HEIGHT}
                      itemData={listItemData}
                      overscanCount={6}
                    >
                      {EmailListRow}
                    </FixedSizeList>
                  )}
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>

      {/* Detail View (Only visible when forceOpen is true, meaning it's the main page view) */}
      {forceOpen && (
        <div className={cn("flex-1 flex flex-col bg-white h-full overflow-hidden", !selectedEmail && "hidden md:flex")}>
          {selectedEmail ? (
            <>
              <div className="p-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
                <div className="flex items-center gap-4">
                  <button
                    onClick={() => { setSelectedEmail(null); setPipelineAlert(null); }}
                    className="md:hidden p-2 -ml-2 text-slate-500 hover:text-slate-900 hover:bg-slate-200 rounded-lg"
                  >
                    <ArrowRight className="w-5 h-5 rotate-180" />
                  </button>
                  <div className="flex items-center gap-3">
                    {getEmailLogo(selectedEmail) && (
                      <img
                        src={getEmailLogo(selectedEmail)!}
                        alt={getEmailCompany(selectedEmail) || ''}
                        className="w-10 h-10 rounded-full border border-slate-100"
                        referrerPolicy="no-referrer"
                        onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                      />
                    )}
                    <div>
                      <h2 className="text-2xl tracking-tight font-serif font-bold text-slate-900">{selectedEmail.subject}</h2>
                      <div className="flex items-center gap-2 mt-1 text-sm text-slate-500">
                        <span className="font-medium text-slate-700">{selectedEmail.sender}</span>
                        <span>&lt;{selectedEmail.senderEmail || 'unknown@example.com'}&gt;</span>
                        {getEmailCompany(selectedEmail) && (
                          <span className="px-2 py-0.5 bg-slate-100 rounded-full text-[10px] font-medium text-slate-600">
                            {getEmailCompany(selectedEmail)}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
                <div className="text-sm text-slate-400 font-medium hidden sm:block">
                  {format(new Date(selectedEmail.date), 'MMM d, yyyy • h:mm a')}
                </div>
              </div>

              {/* Pipeline Alert Banner */}
              {pipelineAlert && !pipelineAlert.in_pipeline && (
                <div className="px-8 pt-4">
                  <div className="max-w-3xl mx-auto p-4 bg-amber-50 border border-amber-200 rounded-xl flex items-start gap-3">
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

              {selectedEmail.summary && (
                <div className="px-8 pt-4">
                  <div className="max-w-3xl mx-auto p-3 bg-slate-50 border border-slate-200 rounded-xl">
                    <p className="text-sm text-slate-600 italic">{selectedEmail.summary}</p>
                  </div>
                </div>
              )}

              <div className="flex-1 overflow-y-auto p-8">
                <div className="max-w-3xl mx-auto">
                  <div className="prose prose-slate prose-sm max-w-none whitespace-pre-wrap break-words overflow-hidden font-sans text-slate-700 leading-relaxed">
                    {selectedEmail.body || selectedEmail.snippet}
                  </div>
                </div>
              </div>

              <div className="p-4 border-t border-slate-100 bg-slate-50">
                <div className="max-w-3xl mx-auto flex gap-3">
                  {selectedEmail.classification === 'action_item' && selectedEmail.actionUrl && (
                    <button
                      onClick={() => openExternal(selectedEmail.actionUrl)}
                      className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-xl shadow-sm hover:bg-indigo-700 transition-colors"
                    >
                      Take Action
                    </button>
                  )}
                  <button
                    onClick={(e) => handleNotJobRelated(e, selectedEmail)}
                    className="px-4 py-2 bg-white border border-slate-200 text-slate-600 text-sm font-medium rounded-xl shadow-sm hover:bg-slate-50 transition-colors flex items-center gap-2"
                  >
                    <ThumbsDown className="w-4 h-4" />
                    Not Job Related
                  </button>
                  <button
                    onClick={() => { setSelectedEmail(null); setPipelineAlert(null); }}
                    className="px-4 py-2 bg-white border border-slate-200 text-slate-700 text-sm font-medium rounded-xl shadow-sm hover:bg-slate-50 transition-colors"
                  >
                    Close
                  </button>
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
    </div>
  );
}
