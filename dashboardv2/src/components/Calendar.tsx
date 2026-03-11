import { useState, useEffect, useMemo, useId, useRef } from 'react';
import { AnimatePresence } from 'motion/react';
import { ChevronLeft, ChevronRight, Plus, Phone, Code, Building2, Users, X, Clock, MapPin, MessageSquare, BookOpen, AlertCircle, RefreshCw } from 'lucide-react';
import { cn } from '../lib/utils';
import { apiFetch, authHeaders, fetchInterviews, syncCalendar } from '../lib/api';
import { DialogShell } from './DialogShell';
import { useAuth } from '../lib/AuthContext';

interface InterviewData {
  id: string;
  application_id: string | null;
  interview_type: string;
  scheduled_at: string | null;
  duration_minutes: number | null;
  interviewer_name: string | null;
  interviewer_email: string | null;
  location_or_link: string | null;
  notes: string | null;
  outcome: string;
  created_at: string;
  company_name?: string;
  role_title?: string;
}

interface InterviewNoteData {
  id: string;
  interview_id: string | null;
  application_id: string | null;
  questions_asked: string | null;
  went_well: string | null;
  to_improve: string | null;
  overall_feeling: string | null;
  created_at: string;
}

const FEELING_COLORS: Record<string, string> = {
  great: 'bg-emerald-100 text-emerald-700',
  good: 'bg-blue-100 text-blue-700',
  okay: 'bg-amber-100 text-amber-700',
  poor: 'bg-red-100 text-red-700',
};

const TYPE_ICONS: Record<string, typeof Phone> = {
  phone: Phone,
  technical: Code,
  onsite: Building2,
  panel: Users,
};

const TYPE_COLORS: Record<string, string> = {
  phone: 'bg-blue-50 text-blue-700 border-blue-200',
  technical: 'bg-purple-50 text-purple-700 border-purple-200',
  onsite: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  panel: 'bg-amber-50 text-amber-700 border-amber-200',
};

const OUTCOME_COLORS: Record<string, string> = {
  pending: 'bg-slate-100 text-slate-600',
  passed: 'bg-emerald-100 text-emerald-700',
  failed: 'bg-red-100 text-red-700',
};

export function Calendar() {
  const { user, connectCalendar, refreshUser } = useAuth();
  const selectedInterviewTitleId = useId();
  const selectedInterviewCloseButtonRef = useRef<HTMLButtonElement>(null);
  const [interviews, setInterviews] = useState<InterviewData[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncingCalendar, setSyncingCalendar] = useState(false);
  const [currentDate, setCurrentDate] = useState(new Date());
  const [viewMode, setViewMode] = useState<'month' | 'week'>('month');
  const [selectedInterview, setSelectedInterview] = useState<InterviewData | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [pastDueInterviews, setPastDueInterviews] = useState<InterviewData[]>([]);
  const [showNoteForm, setShowNoteForm] = useState(false);
  const [interviewNotes, setInterviewNotes] = useState<InterviewNoteData[]>([]);
  const [prepData, setPrepData] = useState<{ past_notes: InterviewNoteData[]; company_context: any } | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  useEffect(() => {
    loadInterviews();
    loadPastDue();
  }, []);

  const getErrorMessage = async (res: Response, fallback: string) => {
    const payload = await res.json().catch(() => null);
    if (payload && typeof payload.detail === 'string') {
      return payload.detail;
    }
    return fallback;
  };

  const loadInterviews = async () => {
    setLoading(true);
    try {
      setInterviews(await fetchInterviews());
      setErrorMessage(null);
    } catch {
      setErrorMessage('Failed to load interviews.');
    } finally {
      setLoading(false);
    }
  };

  const loadPastDue = async () => {
    try {
      const res = await apiFetch('/api/interviews/past-due', { headers: authHeaders() });
      if (!res.ok) {
        setErrorMessage(await getErrorMessage(res, 'Failed to load past-due interviews.'));
        return;
      }
      setPastDueInterviews(await res.json());
    } catch {
      setErrorMessage('Failed to load past-due interviews.');
    }
  };

  const loadNotes = async (interviewId: string) => {
    try {
      const res = await apiFetch(`/api/interviews/${interviewId}/notes`, { headers: authHeaders() });
      if (!res.ok) {
        setErrorMessage(await getErrorMessage(res, 'Failed to load interview notes.'));
        return;
      }
      setInterviewNotes(await res.json());
    } catch {
      setErrorMessage('Failed to load interview notes.');
    }
  };

  const loadPrep = async (interviewId: string) => {
    try {
      const res = await apiFetch(`/api/interviews/${interviewId}/prep`, { headers: authHeaders() });
      if (!res.ok) {
        setErrorMessage(await getErrorMessage(res, 'Failed to load interview prep.'));
        return;
      }
      setPrepData(await res.json());
    } catch {
      setErrorMessage('Failed to load interview prep.');
    }
  };

  const handleSelectInterview = async (interview: InterviewData) => {
    setErrorMessage(null);
    setSelectedInterview(interview);
    setShowNoteForm(false);
    setInterviewNotes([]);
    setPrepData(null);
    await loadNotes(interview.id);
    // Load prep for upcoming interviews
    if (interview.scheduled_at && new Date(interview.scheduled_at) > new Date()) {
      await loadPrep(interview.id);
    }
  };

  const handleSaveNote = async (interviewId: string, note: { questions_asked: string; went_well: string; to_improve: string; overall_feeling: string }) => {
    try {
      const res = await apiFetch(`/api/interviews/${interviewId}/notes`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify(note),
      });
      if (!res.ok) {
        setErrorMessage(await getErrorMessage(res, 'Failed to save interview note.'));
        return;
      }
      setErrorMessage(null);
      setShowNoteForm(false);
      setStatusMessage('Interview note saved.');
      await loadNotes(interviewId);
      await loadPastDue();
    } catch {
      setErrorMessage('Failed to save interview note.');
    }
  };

  const handleAdd = async (data: Partial<InterviewData>) => {
    try {
      const res = await apiFetch('/api/interviews', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify(data),
      });
      if (!res.ok) {
        setErrorMessage(await getErrorMessage(res, 'Failed to create interview.'));
        return;
      }
      setErrorMessage(null);
      setStatusMessage('Interview added.');
      setShowAddModal(false);
      loadInterviews();
    } catch {
      setErrorMessage('Failed to create interview.');
    }
  };

  const handleUpdate = async (id: string, data: Partial<InterviewData>) => {
    try {
      const res = await apiFetch(`/api/interviews/${id}`, {
        method: 'PATCH',
        headers: authHeaders(),
        body: JSON.stringify(data),
      });
      if (!res.ok) {
        setErrorMessage(await getErrorMessage(res, 'Failed to update interview.'));
        return;
      }
      setErrorMessage(null);
      setStatusMessage('Interview updated.');
      setSelectedInterview(null);
      loadInterviews();
    } catch {
      setErrorMessage('Failed to update interview.');
    }
  };

  const handleSyncCalendar = async () => {
    setSyncingCalendar(true);
    setErrorMessage(null);
    setStatusMessage(null);
    try {
      const result = await syncCalendar();
      await Promise.all([loadInterviews(), loadPastDue()]);
      const totalSynced = result.created + result.updated;
      setStatusMessage(
        totalSynced > 0
          ? `Google Calendar synced ${totalSynced} interviews (${result.created} new, ${result.updated} updated).`
          : 'Google Calendar sync finished with no new interview events.'
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Calendar sync failed.';
      setErrorMessage(message);
      if (message.includes('Reconnect your Google account with Calendar access')) {
        await refreshUser();
      }
    } finally {
      setSyncingCalendar(false);
    }
  };

  // Calendar grid computation
  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();

  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const firstDayOfWeek = new Date(year, month, 1).getDay();

  const calendarDays = useMemo(() => {
    const days: { date: Date; isCurrentMonth: boolean }[] = [];
    // Previous month padding
    const prevMonthDays = new Date(year, month, 0).getDate();
    for (let i = firstDayOfWeek - 1; i >= 0; i--) {
      days.push({ date: new Date(year, month - 1, prevMonthDays - i), isCurrentMonth: false });
    }
    // Current month
    for (let d = 1; d <= daysInMonth; d++) {
      days.push({ date: new Date(year, month, d), isCurrentMonth: true });
    }
    // Next month padding
    const remaining = 42 - days.length;
    for (let d = 1; d <= remaining; d++) {
      days.push({ date: new Date(year, month + 1, d), isCurrentMonth: false });
    }
    return days;
  }, [year, month, daysInMonth, firstDayOfWeek]);

  const interviewsByDate = useMemo(() => {
    const map = new Map<string, InterviewData[]>();
    for (const interview of interviews) {
      if (!interview.scheduled_at) continue;
      const dateKey = new Date(interview.scheduled_at).toDateString();
      if (!map.has(dateKey)) map.set(dateKey, []);
      map.get(dateKey)!.push(interview);
    }
    return map;
  }, [interviews]);

  const today = new Date().toDateString();

  const prevMonth = () => setCurrentDate(new Date(year, month - 1, 1));
  const nextMonth = () => setCurrentDate(new Date(year, month + 1, 1));

  const upcomingInterviews = interviews
    .filter(i => i.scheduled_at && new Date(i.scheduled_at) > new Date() && i.outcome === 'pending')
    .sort((a, b) => new Date(a.scheduled_at!).getTime() - new Date(b.scheduled_at!).getTime())
    .slice(0, 5);

  return (
    <div className="flex-1 h-full overflow-y-auto p-4 md:p-8 bg-[#F5F5F0]">
      <div className="w-full">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl tracking-tight font-serif font-bold text-slate-900">Calendar</h1>
            <p className="mt-1 text-slate-500 font-serif italic">
              Track your interviews and prep schedule.
            </p>
            {user?.calendar_connected && (
              <p className="mt-2 text-xs font-medium uppercase tracking-[0.2em] text-emerald-700">
                Google Calendar connected
              </p>
            )}
          </div>
          <div className="flex items-center gap-3">
            {!user?.calendar_connected ? (
              <button
                onClick={connectCalendar}
                className="px-4 py-2.5 text-sm bg-emerald-100 hover:bg-emerald-200 text-emerald-900 rounded-xl font-medium shadow-sm"
              >
                Connect Google Calendar
              </button>
            ) : (
              <button
                onClick={handleSyncCalendar}
                disabled={syncingCalendar}
                className="px-4 py-2.5 text-sm bg-white hover:bg-slate-50 text-slate-700 rounded-xl font-medium shadow-sm border border-slate-200 flex items-center gap-2 disabled:opacity-60"
              >
                <RefreshCw className={cn('w-4 h-4', syncingCalendar && 'animate-spin')} />
                {syncingCalendar ? 'Syncing...' : 'Sync Calendar'}
              </button>
            )}
            <button
              onClick={() => setShowAddModal(true)}
              className="px-4 py-2.5 text-sm bg-slate-800 hover:bg-slate-900 text-white rounded-xl font-medium shadow-sm flex items-center gap-2"
            >
              <Plus className="w-4 h-4" /> Add Interview
            </button>
          </div>
        </div>

        {(errorMessage || statusMessage) && (
          <div className={cn(
            'mb-6 rounded-2xl border px-4 py-3 text-sm',
            errorMessage ? 'border-red-200 bg-red-50 text-red-800' : 'border-emerald-200 bg-emerald-50 text-emerald-800'
          )}>
            {errorMessage || statusMessage}
          </div>
        )}

        <div className="flex gap-6 flex-col xl:flex-row">
          {/* Calendar Grid */}
          <div className="flex-1 bg-white rounded-3xl shadow-sm border border-slate-100 p-6">
            <div className="flex items-center justify-between mb-6">
              <button onClick={prevMonth} aria-label="Show previous month" className="p-2 hover:bg-slate-100 rounded-lg"><ChevronLeft className="w-5 h-5" /></button>
              <h2 className="text-xl font-serif font-bold text-slate-900">
                {currentDate.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
              </h2>
              <button onClick={nextMonth} aria-label="Show next month" className="p-2 hover:bg-slate-100 rounded-lg"><ChevronRight className="w-5 h-5" /></button>
            </div>

            <div className="grid grid-cols-7 gap-px">
              {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(day => (
                <div key={day} className="p-2 text-center text-xs font-medium text-slate-400">{day}</div>
              ))}
              {calendarDays.map(({ date, isCurrentMonth }, i) => {
                const dateKey = date.toDateString();
                const dayInterviews = interviewsByDate.get(dateKey) || [];
                const isToday = dateKey === today;
                return (
                  <div
                    key={i}
                    className={cn(
                      "min-h-[80px] p-1.5 border border-slate-50 rounded-lg transition-colors",
                      !isCurrentMonth && "opacity-30",
                      isToday && "bg-indigo-50/50 border-indigo-100",
                    )}
                  >
                    <span className={cn(
                      "inline-flex w-6 h-6 items-center justify-center text-xs rounded-full",
                      isToday ? "bg-indigo-600 text-white font-bold" : "text-slate-600"
                    )}>
                      {date.getDate()}
                    </span>
                    {dayInterviews.map(interview => {
                      const Icon = TYPE_ICONS[interview.interview_type] || Phone;
                      return (
                        <button
                          key={interview.id}
                          onClick={() => handleSelectInterview(interview)}
                          className={cn(
                            "w-full mt-0.5 px-1.5 py-0.5 text-[10px] font-medium rounded-md border flex items-center gap-1 truncate",
                            TYPE_COLORS[interview.interview_type] || TYPE_COLORS.phone,
                          )}
                        >
                          <Icon className="w-3 h-3 shrink-0" />
                          <span className="truncate">{interview.interviewer_name || interview.interview_type}</span>
                        </button>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Upcoming Sidebar */}
          <div className="w-full xl:w-80 shrink-0 space-y-4">
            {/* Post-Interview Prompts */}
            {pastDueInterviews.length > 0 && (
              <div className="bg-amber-50 rounded-3xl shadow-sm border border-amber-200 p-6">
                <h3 className="text-sm font-bold text-amber-900 mb-3 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4" /> Needs Debrief
                </h3>
                <div className="space-y-2">
                  {pastDueInterviews.slice(0, 3).map(interview => (
                    <button
                      key={interview.id}
                      onClick={() => { handleSelectInterview(interview); setShowNoteForm(true); }}
                      className="w-full text-left p-3 rounded-xl bg-white/80 hover:bg-white transition-colors border border-amber-100"
                    >
                      <p className="text-sm font-medium text-slate-900">
                        How did your {interview.interview_type} interview{interview.company_name ? ` at ${interview.company_name}` : ''} go?
                      </p>
                      <p className="text-xs text-amber-700 mt-1">
                        {interview.scheduled_at ? new Date(interview.scheduled_at).toLocaleDateString() : ''}
                        {interview.role_title ? ` — ${interview.role_title}` : ''}
                      </p>
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="bg-white rounded-3xl shadow-sm border border-slate-100 p-6">
              <h3 className="text-sm font-bold text-slate-900 mb-4">Upcoming Interviews</h3>
              {upcomingInterviews.length === 0 ? (
                <p className="text-sm text-slate-400 text-center py-4">No upcoming interviews</p>
              ) : (
                <div className="space-y-3">
                  {upcomingInterviews.map(interview => {
                    const Icon = TYPE_ICONS[interview.interview_type] || Phone;
                    return (
                      <button
                        key={interview.id}
                        onClick={() => handleSelectInterview(interview)}
                        className="w-full text-left p-3 rounded-xl bg-slate-50 hover:bg-slate-100 transition-colors"
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <Icon className="w-4 h-4 text-slate-500" />
                          <span className="text-sm font-medium text-slate-900 capitalize">{interview.interview_type}</span>
                        </div>
                        {interview.interviewer_name && (
                          <p className="text-xs text-slate-500">with {interview.interviewer_name}</p>
                        )}
                        <p className="text-xs text-slate-400 mt-1">
                          {interview.scheduled_at ? new Date(interview.scheduled_at).toLocaleString() : 'No date set'}
                        </p>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Interview Detail Modal */}
      <AnimatePresence>
        {selectedInterview && (
          <DialogShell
            onClose={() => setSelectedInterview(null)}
            titleId={selectedInterviewTitleId}
            initialFocusRef={selectedInterviewCloseButtonRef}
            wrapperClassName="fixed inset-0 z-50 flex items-center justify-center p-4"
            overlayClassName="absolute inset-0 bg-slate-900/20 backdrop-blur-sm"
            panelClassName="bg-white w-full max-w-md rounded-3xl shadow-2xl overflow-hidden"
          >
              <div className="p-6 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
                <h2 id={selectedInterviewTitleId} className="text-xl font-serif font-bold text-slate-900 capitalize">
                  {selectedInterview.interview_type} Interview
                </h2>
                <button
                  ref={selectedInterviewCloseButtonRef}
                  onClick={() => setSelectedInterview(null)}
                  aria-label="Close interview details"
                  className="p-1 hover:bg-slate-200 rounded-lg"
                >
                  <X className="w-5 h-5 text-slate-500" />
                </button>
              </div>
              <div className="p-6 space-y-4">
                {selectedInterview.scheduled_at && (
                  <div className="flex items-center gap-3 text-sm">
                    <Clock className="w-4 h-4 text-slate-400" />
                    <span>{new Date(selectedInterview.scheduled_at).toLocaleString()}</span>
                    {selectedInterview.duration_minutes && (
                      <span className="text-slate-400">({selectedInterview.duration_minutes} min)</span>
                    )}
                  </div>
                )}
                {selectedInterview.interviewer_name && (
                  <div className="flex items-center gap-3 text-sm">
                    <Users className="w-4 h-4 text-slate-400" />
                    <span>{selectedInterview.interviewer_name}</span>
                  </div>
                )}
                {selectedInterview.location_or_link && (
                  <div className="flex items-center gap-3 text-sm">
                    <MapPin className="w-4 h-4 text-slate-400" />
                    {selectedInterview.location_or_link.startsWith('http') ? (
                      <a href={selectedInterview.location_or_link} target="_blank" rel="noopener noreferrer" className="text-indigo-600 hover:underline truncate">
                        Join Meeting
                      </a>
                    ) : (
                      <span>{selectedInterview.location_or_link}</span>
                    )}
                  </div>
                )}
                {selectedInterview.notes && (
                  <div className="text-sm text-slate-600 bg-slate-50 p-3 rounded-xl">{selectedInterview.notes}</div>
                )}
                <div className="flex items-center gap-2 pt-2">
                  <span className="text-xs font-medium text-slate-500">Outcome:</span>
                  <span className={cn("px-2 py-0.5 text-xs font-medium rounded-full capitalize", OUTCOME_COLORS[selectedInterview.outcome] || OUTCOME_COLORS.pending)}>
                    {selectedInterview.outcome}
                  </span>
                </div>
                {selectedInterview.outcome === 'pending' && (
                  <div className="flex gap-2 pt-2">
                    <button
                      onClick={() => handleUpdate(selectedInterview.id, { outcome: 'passed' })}
                      className="flex-1 px-3 py-2 text-sm font-medium bg-emerald-50 text-emerald-700 rounded-xl hover:bg-emerald-100"
                    >
                      Passed
                    </button>
                    <button
                      onClick={() => handleUpdate(selectedInterview.id, { outcome: 'failed' })}
                      className="flex-1 px-3 py-2 text-sm font-medium bg-red-50 text-red-700 rounded-xl hover:bg-red-100"
                    >
                      Failed
                    </button>
                  </div>
                )}

                {/* Pre-interview Prep */}
                {prepData && prepData.past_notes.length > 0 && (
                  <div className="border-t border-slate-100 pt-4">
                    <h4 className="text-xs font-bold text-slate-900 mb-2 flex items-center gap-1.5">
                      <BookOpen className="w-3.5 h-3.5" /> Prep: Past Notes at This Company
                    </h4>
                    <div className="space-y-2 max-h-40 overflow-y-auto">
                      {prepData.past_notes.map(note => (
                        <div key={note.id} className="p-2 bg-indigo-50/50 rounded-lg text-xs">
                          {note.overall_feeling && (
                            <span className={cn("px-1.5 py-0.5 rounded-full text-[10px] font-medium mr-2", FEELING_COLORS[note.overall_feeling] || '')}>
                              {note.overall_feeling}
                            </span>
                          )}
                          {note.went_well && <p className="text-slate-600 mt-1">Went well: {note.went_well}</p>}
                          {note.to_improve && <p className="text-slate-500 mt-0.5">To improve: {note.to_improve}</p>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Interview Notes */}
                {interviewNotes.length > 0 && (
                  <div className="border-t border-slate-100 pt-4">
                    <h4 className="text-xs font-bold text-slate-900 mb-2 flex items-center gap-1.5">
                      <MessageSquare className="w-3.5 h-3.5" /> Interview Notes
                    </h4>
                    <div className="space-y-2">
                      {interviewNotes.map(note => (
                        <div key={note.id} className="p-3 bg-slate-50 rounded-xl text-sm space-y-1">
                          {note.overall_feeling && (
                            <span className={cn("px-2 py-0.5 rounded-full text-[10px] font-medium", FEELING_COLORS[note.overall_feeling] || '')}>
                              {note.overall_feeling}
                            </span>
                          )}
                          {note.questions_asked && <p className="text-slate-600"><span className="font-medium">Questions:</span> {note.questions_asked}</p>}
                          {note.went_well && <p className="text-slate-600"><span className="font-medium">Went well:</span> {note.went_well}</p>}
                          {note.to_improve && <p className="text-slate-600"><span className="font-medium">To improve:</span> {note.to_improve}</p>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Add Note Form */}
                {showNoteForm ? (
                  <NoteForm
                    onSave={(note) => handleSaveNote(selectedInterview.id, note)}
                    onCancel={() => setShowNoteForm(false)}
                  />
                ) : (
                  <button
                    onClick={() => setShowNoteForm(true)}
                    className="w-full px-3 py-2 text-sm font-medium text-indigo-600 bg-indigo-50 rounded-xl hover:bg-indigo-100 flex items-center justify-center gap-2"
                  >
                    <MessageSquare className="w-4 h-4" /> Add Interview Notes
                  </button>
                )}
              </div>
          </DialogShell>
        )}
      </AnimatePresence>

      {/* Add Interview Modal */}
      <AnimatePresence>
        {showAddModal && (
          <AddInterviewModal onClose={() => setShowAddModal(false)} onAdd={handleAdd} />
        )}
      </AnimatePresence>
    </div>
  );
}


function AddInterviewModal({ onClose, onAdd }: { onClose: () => void; onAdd: (data: any) => void }) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const [type, setType] = useState('phone');
  const [scheduledAt, setScheduledAt] = useState('');
  const [duration, setDuration] = useState('60');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [location, setLocation] = useState('');
  const [notes, setNotes] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onAdd({
      interview_type: type,
      scheduled_at: scheduledAt || null,
      duration_minutes: duration ? parseInt(duration) : null,
      interviewer_name: name || null,
      interviewer_email: email || null,
      location_or_link: location || null,
      notes: notes || null,
    });
  };

  return (
    <DialogShell
      onClose={onClose}
      titleId={titleId}
      initialFocusRef={closeButtonRef}
      wrapperClassName="fixed inset-0 z-50 flex items-center justify-center p-4"
      overlayClassName="absolute inset-0 bg-slate-900/20 backdrop-blur-sm"
      panelClassName="bg-white w-full max-w-md rounded-3xl shadow-2xl overflow-hidden"
    >
        <div className="p-6 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
          <h2 id={titleId} className="text-xl font-serif font-bold text-slate-900">Add Interview</h2>
          <button
            ref={closeButtonRef}
            onClick={onClose}
            aria-label="Close add interview dialog"
            className="p-1 hover:bg-slate-200 rounded-lg"
          >
            <X className="w-5 h-5 text-slate-500" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="text-xs font-medium text-slate-500 mb-1 block">Type</label>
            <select value={type} onChange={e => setType(e.target.value)} className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm">
              <option value="phone">Phone Screen</option>
              <option value="technical">Technical</option>
              <option value="onsite">Onsite</option>
              <option value="panel">Panel</option>
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500 mb-1 block">Date & Time</label>
            <input type="datetime-local" value={scheduledAt} onChange={e => setScheduledAt(e.target.value)} className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-slate-500 mb-1 block">Duration (min)</label>
              <input type="number" value={duration} onChange={e => setDuration(e.target.value)} className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm" />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-500 mb-1 block">Interviewer</label>
              <input type="text" value={name} onChange={e => setName(e.target.value)} placeholder="Name" className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm" />
            </div>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500 mb-1 block">Location / Link</label>
            <input type="text" value={location} onChange={e => setLocation(e.target.value)} placeholder="Zoom link or address" className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm" />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500 mb-1 block">Notes</label>
            <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={2} className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm resize-none" />
          </div>
          <button type="submit" className="w-full px-4 py-2.5 text-sm bg-slate-800 hover:bg-slate-900 text-white rounded-xl font-medium shadow-sm">
            Add Interview
          </button>
        </form>
    </DialogShell>
  );
}


function NoteForm({ onSave, onCancel }: { onSave: (note: { questions_asked: string; went_well: string; to_improve: string; overall_feeling: string }) => void; onCancel: () => void }) {
  const [questions, setQuestions] = useState('');
  const [wentWell, setWentWell] = useState('');
  const [toImprove, setToImprove] = useState('');
  const [feeling, setFeeling] = useState('good');

  return (
    <div className="border-t border-slate-100 pt-4 space-y-3">
      <h4 className="text-xs font-bold text-slate-900">Debrief Notes</h4>
      <div>
        <label className="text-[10px] font-medium text-slate-500 mb-1 block">How did it feel?</label>
        <div className="flex gap-1.5">
          {['great', 'good', 'okay', 'poor'].map(f => (
            <button
              key={f}
              onClick={() => setFeeling(f)}
              className={cn(
                "px-3 py-1 text-xs font-medium rounded-full border capitalize transition-colors",
                feeling === f ? FEELING_COLORS[f] + ' border-transparent' : 'bg-white text-slate-400 border-slate-200 hover:bg-slate-50',
              )}
            >
              {f}
            </button>
          ))}
        </div>
      </div>
      <div>
        <label className="text-[10px] font-medium text-slate-500 mb-1 block">Questions Asked</label>
        <textarea value={questions} onChange={e => setQuestions(e.target.value)} rows={2} placeholder="What did they ask?" className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm resize-none" />
      </div>
      <div>
        <label className="text-[10px] font-medium text-slate-500 mb-1 block">What Went Well</label>
        <textarea value={wentWell} onChange={e => setWentWell(e.target.value)} rows={2} placeholder="What felt good?" className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm resize-none" />
      </div>
      <div>
        <label className="text-[10px] font-medium text-slate-500 mb-1 block">To Improve</label>
        <textarea value={toImprove} onChange={e => setToImprove(e.target.value)} rows={2} placeholder="What could be better?" className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm resize-none" />
      </div>
      <div className="flex gap-2">
        <button
          onClick={() => onSave({ questions_asked: questions, went_well: wentWell, to_improve: toImprove, overall_feeling: feeling })}
          className="flex-1 px-3 py-2 text-sm font-medium bg-slate-800 text-white rounded-xl hover:bg-slate-900"
        >
          Save Notes
        </button>
        <button
          onClick={onCancel}
          className="px-3 py-2 text-sm font-medium text-slate-500 bg-slate-100 rounded-xl hover:bg-slate-200"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
