import { useState, useMemo, useEffect } from 'react';
import { Job, JobStatus } from '../types';
import { MapPin, DollarSign, Calendar, Filter, Linkedin, Globe, Briefcase, ChevronDown, ChevronUp, X, AlignLeft, StickyNote, ExternalLink, Users, Building2, Link as LinkIcon, Check, Mail } from 'lucide-react';
import { format, isAfter, subDays, subWeeks, subMonths, formatDistanceToNow } from 'date-fns';
import { cn } from '../lib/utils';
import { motion, AnimatePresence } from 'motion/react';
import { updateJob, getWarmPaths } from '../lib/api';
import { AddJobModal } from './AddJobModal';

function WarmConnectionsSection({ jobId, company }: { jobId: string; company: string }) {
  const [connections, setConnections] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getWarmPaths(jobId)
      .then(data => setConnections(data.warm_connections || []))
      .catch(() => setConnections([]))
      .finally(() => setLoading(false));
  }, [jobId]);

  if (loading) return null;
  if (connections.length === 0) return null;

  return (
    <section>
      <h3 className="text-lg font-bold text-slate-900 mb-3 flex items-center gap-2">
        <Users className="w-5 h-5 text-emerald-500" />
        Warm Connections
      </h3>
      <div className="space-y-2">
        {connections.map((conn: any) => (
          <div key={conn.id} className="p-3 bg-emerald-50/50 border border-emerald-100 rounded-xl">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-900">{conn.contact_name || conn.contact_email}</p>
                <p className="text-xs text-slate-500">{conn.email_count} email{conn.email_count !== 1 ? 's' : ''} exchanged</p>
              </div>
              <a
                href={`mailto:${conn.contact_email}`}
                className="flex items-center gap-1 px-2 py-1 text-xs font-medium text-emerald-600 bg-white border border-emerald-200 rounded-lg hover:bg-emerald-50"
              >
                <Mail className="w-3 h-3" /> Reach Out
              </a>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

const SECTIONS: { id: JobStatus; title: string; color: string; bg: string; border: string }[] = [
  { id: 'interviewing', title: 'Interviewing', color: 'text-purple-700', bg: 'bg-purple-100', border: 'border-purple-200' },
  { id: 'offer', title: 'Offers', color: 'text-emerald-700', bg: 'bg-emerald-100', border: 'border-emerald-200' },
  { id: 'applied', title: 'Applied', color: 'text-blue-700', bg: 'bg-blue-100', border: 'border-blue-200' },
  { id: 'saved', title: 'Saved', color: 'text-slate-700', bg: 'bg-slate-100', border: 'border-slate-200' },
  { id: 'rejected', title: 'Rejected', color: 'text-red-700', bg: 'bg-red-100', border: 'border-red-200' },
];

export function KanbanBoard({ jobs, setJobs }: { jobs: Job[], setJobs: (jobs: Job[]) => void }) {
  const [dateFilter, setDateFilter] = useState<string>('all');
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({});
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);

  // Inline editing state
  const [editingNotes, setEditingNotes] = useState(false);
  const [notesText, setNotesText] = useState('');
  const [editingDescription, setEditingDescription] = useState(false);
  const [descriptionText, setDescriptionText] = useState('');
  const [savingField, setSavingField] = useState<string | null>(null);

  const filteredJobs = useMemo(() => {
    return jobs.filter(job => {
      const jobDate = new Date(job.dateAdded);
      const now = new Date();
      if (dateFilter === '24h' && !isAfter(jobDate, subDays(now, 1))) return false;
      if (dateFilter === '3d' && !isAfter(jobDate, subDays(now, 3))) return false;
      if (dateFilter === '1w' && !isAfter(jobDate, subWeeks(now, 1))) return false;
      if (dateFilter === '2w' && !isAfter(jobDate, subWeeks(now, 2))) return false;
      if (dateFilter === '1m' && !isAfter(jobDate, subMonths(now, 1))) return false;

      return true;
    });
  }, [jobs, dateFilter]);

  const updateJobStatus = (jobId: string, newStatus: JobStatus) => {
    setJobs(jobs.map(j => j.id === jobId ? { ...j, status: newStatus } : j));
    if (selectedJob && selectedJob.id === jobId) {
      setSelectedJob({ ...selectedJob, status: newStatus });
    }
    updateJob(jobId, { status: newStatus }).catch(err =>
      console.error('Failed to update job status:', err)
    );
  };

  const toggleSection = (sectionId: string) => {
    setExpandedSections(prev => ({ ...prev, [sectionId]: !prev[sectionId] }));
  };

  const getSourceIcon = (source?: string) => {
    switch (source) {
      case 'linkedin': return <Linkedin className="w-4 h-4 text-[#0A66C2]" />;
      case 'indeed': return <Briefcase className="w-4 h-4 text-[#2164f4]" />;
      case 'glassdoor': return <Globe className="w-4 h-4 text-[#0caa41]" />;
      default: return <Globe className="w-4 h-4 text-slate-400" />;
    }
  };

  const handleSaveNotes = async () => {
    if (!selectedJob) return;
    setSavingField('notes');
    try {
      await updateJob(selectedJob.id, { notes: notesText });
      const updated = { ...selectedJob, notes: notesText };
      setSelectedJob(updated);
      setJobs(jobs.map(j => j.id === selectedJob.id ? updated : j));
    } catch (err) {
      console.error('Failed to save notes:', err);
    } finally {
      setSavingField(null);
      setEditingNotes(false);
    }
  };

  const handleSaveDescription = async () => {
    if (!selectedJob) return;
    setSavingField('description');
    try {
      await updateJob(selectedJob.id, { description: descriptionText });
      const updated = { ...selectedJob, description: descriptionText };
      setSelectedJob(updated);
      setJobs(jobs.map(j => j.id === selectedJob.id ? updated : j));
    } catch (err) {
      console.error('Failed to save description:', err);
    } finally {
      setSavingField(null);
      setEditingDescription(false);
    }
  };

  const startEditingNotes = () => {
    setNotesText(selectedJob?.notes || '');
    setEditingNotes(true);
  };

  const startEditingDescription = () => {
    setDescriptionText(selectedJob?.description || '');
    setEditingDescription(true);
  };

  const handleJobAdded = (newJob: Job) => {
    setJobs([newJob, ...jobs]);
  };

  return (
    <div className="flex-1 h-full overflow-y-auto p-4 md:p-8 bg-[#F5F5F0] flex flex-col relative">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-8 shrink-0">
        <div>
          <h1 className="text-3xl tracking-tight font-serif font-bold text-slate-900">
            Pipeline
          </h1>
          <p className="mt-1 text-slate-500 font-serif italic">
            Track and manage your active job applications.
          </p>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 bg-white px-3 py-1.5 rounded-xl border border-slate-200 shadow-sm">
            <Filter className="w-4 h-4 text-slate-400" />
            <select
              value={dateFilter}
              onChange={(e) => setDateFilter(e.target.value)}
              className="bg-transparent border-none text-sm font-medium text-slate-700 outline-none cursor-pointer"
            >
              <option value="all">All Time</option>
              <option value="24h">Last 24 Hours</option>
              <option value="3d">Last 3 Days</option>
              <option value="1w">Last Week</option>
              <option value="2w">Last 2 Weeks</option>
              <option value="1m">Last Month</option>
            </select>
          </div>
          <button
            onClick={() => setShowAddModal(true)}
            className="px-4 py-2 transition-all bg-slate-800 hover:bg-slate-900 text-white rounded-xl text-sm font-medium shadow-sm"
          >
            + Add Job
          </button>
        </div>
      </div>

      <div className="space-y-10 pb-12">
        {SECTIONS.map(section => {
          const sectionJobs = filteredJobs.filter(j => j.status === section.id);
          if (sectionJobs.length === 0) return null;

          const isExpanded = expandedSections[section.id];
          const displayJobs = isExpanded ? sectionJobs : sectionJobs.slice(0, 8);
          const hasMore = sectionJobs.length > 8;

          return (
            <div key={section.id} className="flex flex-col">
              <div className="flex items-center gap-3 mb-4">
                <div className={cn("px-3 py-1 rounded-full text-xs font-bold tracking-wide uppercase border", section.bg, section.color, section.border)}>
                  {section.title}
                </div>
                <span className="text-slate-400 font-medium text-sm">{sectionJobs.length} jobs</span>
              </div>

              <motion.div layout className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-4">
                <AnimatePresence mode="popLayout">
                  {displayJobs.map(job => (
                    <motion.div
                      layout
                      initial={{ opacity: 0, scale: 0.95 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.95 }}
                      transition={{ duration: 0.2 }}
                      key={job.id}
                      onClick={() => {
                        setSelectedJob(job);
                        setEditingNotes(false);
                        setEditingDescription(false);
                      }}
                      className="group relative transition-all bg-white p-4 rounded-xl shadow-[0_4px_20px_rgb(0,0,0,0.03)] border border-slate-100 flex flex-col min-h-[140px] hover:shadow-md hover:border-indigo-300 cursor-pointer"
                    >
                      <div className="absolute top-3 right-3" title={`Found via ${job.source || 'Unknown'}`}>
                        {getSourceIcon(job.source)}
                      </div>
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex items-center gap-2.5 pr-5 w-full">
                          {job.logoUrl ? (
                            <img src={job.logoUrl} alt={job.company} className="w-8 h-8 rounded-lg border border-slate-100 shrink-0" referrerPolicy="no-referrer" />
                          ) : (
                            <div className="w-8 h-8 flex items-center justify-center font-medium text-xs rounded-lg bg-slate-100 text-slate-500 shrink-0">
                              {job.company.charAt(0)}
                            </div>
                          )}
                          <div className="min-w-0 flex-1">
                            <h3 className="leading-tight font-serif font-bold text-slate-900 text-base break-words line-clamp-2">{job.role}</h3>
                            <p className="text-[11px] mt-0.5 text-slate-500 font-sans truncate">{job.company}</p>
                          </div>
                        </div>
                      </div>

                      <div className="space-y-1.5 mt-auto">
                        <div className="flex items-center text-xs gap-1.5 text-slate-500">
                          <MapPin className="w-3.5 h-3.5 shrink-0" />
                          <span className="truncate">{job.location || 'Location N/A'}</span>
                        </div>
                        <div className="flex items-center text-xs gap-1.5 text-slate-500">
                          <DollarSign className="w-3.5 h-3.5 shrink-0" />
                          <span className="truncate">{job.salary || 'Salary N/A'}</span>
                        </div>
                        {/* Sprint 4: Tech tags */}
                        {job.techStack && job.techStack.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-1.5">
                            {job.techStack.slice(0, 4).map(tech => (
                              <span key={tech} className="px-1.5 py-0.5 text-[9px] font-medium bg-indigo-50 text-indigo-600 rounded-md">
                                {tech}
                              </span>
                            ))}
                            {job.techStack.length > 4 && (
                              <span className="px-1.5 py-0.5 text-[9px] font-medium bg-slate-50 text-slate-500 rounded-md">
                                +{job.techStack.length - 4}
                              </span>
                            )}
                          </div>
                        )}
                        {/* Sprint 5: Match score badge */}
                        {job.matchScore != null && (
                          <div className="mt-1.5">
                            <span className={cn(
                              "px-1.5 py-0.5 text-[9px] font-bold rounded-md",
                              job.matchScore >= 80 ? "bg-emerald-50 text-emerald-600" :
                              job.matchScore >= 50 ? "bg-amber-50 text-amber-600" :
                              "bg-red-50 text-red-500"
                            )}>
                              {job.matchScore}% match
                            </span>
                          </div>
                        )}
                        {/* Sprint 7: Dead listing warning */}
                        {job.listingAlive === false && (
                          <div className="mt-1.5 px-1.5 py-0.5 text-[9px] font-medium bg-orange-50 text-orange-600 rounded-md inline-block">
                            Posting may be closed
                          </div>
                        )}
                        <div className="flex items-center justify-between mt-2.5 pt-2.5 border-t border-slate-100 gap-2">
                          <div className="flex items-center text-[11px] gap-1 text-slate-400 shrink-0">
                            <Calendar className="w-3 h-3 shrink-0" />
                            <span className="truncate">{format(new Date(job.dateAdded), 'MMM d')}</span>
                          </div>
                          <div className="relative min-w-0 flex-1 flex justify-end">
                            <select
                              value={job.status}
                              onClick={(e) => e.stopPropagation()}
                              onChange={(e) => updateJobStatus(job.id, e.target.value as JobStatus)}
                              className="appearance-none bg-slate-50 border border-slate-200 text-slate-600 text-[9px] font-bold uppercase tracking-wider py-1 pl-2 pr-4 rounded-md cursor-pointer outline-none focus:ring-2 focus:ring-indigo-500 transition-colors hover:bg-slate-100 max-w-full truncate"
                            >
                              <option value="interviewing">Interviewing</option>
                              <option value="offer">Offer</option>
                              <option value="applied">Applied</option>
                              <option value="saved">Saved</option>
                              <option value="rejected">Rejected</option>
                            </select>
                            <ChevronDown className="w-3 h-3 text-slate-400 absolute right-1.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                          </div>
                        </div>
                      </div>
                    </motion.div>
                  ))}
                </AnimatePresence>
              </motion.div>

              {hasMore && (
                <div className="mt-6 flex justify-center">
                  <button
                    onClick={() => toggleSection(section.id)}
                    className="flex items-center gap-2 px-5 py-2 bg-white border border-slate-200 hover:bg-slate-50 text-slate-600 rounded-full text-sm font-medium transition-colors shadow-sm"
                  >
                    {isExpanded ? (
                      <>Show Less <ChevronUp className="w-4 h-4" /></>
                    ) : (
                      <>View All {sectionJobs.length} <ChevronDown className="w-4 h-4" /></>
                    )}
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Job Detail Modal */}
      <AnimatePresence>
        {selectedJob && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => { setSelectedJob(null); setEditingNotes(false); setEditingDescription(false); }}
              className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-40"
            />
            <motion.div
              layoutId={`job-card-${selectedJob.id}`}
              className="fixed inset-4 md:inset-auto md:top-1/2 md:left-1/2 md:-translate-x-1/2 md:-translate-y-1/2 md:w-full md:max-w-4xl md:max-h-[85vh] bg-white rounded-3xl shadow-2xl z-50 flex flex-col overflow-hidden"
            >
              {/* Modal Header */}
              <div className="p-4 md:p-5 border-b border-slate-100 flex items-start justify-between bg-slate-50/50 shrink-0">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-xl border border-slate-200 flex items-center justify-center bg-white overflow-hidden shrink-0 shadow-sm">
                    {selectedJob.logoUrl ? (
                      <img src={selectedJob.logoUrl} alt={selectedJob.company} className="w-full h-full object-cover" referrerPolicy="no-referrer" />
                    ) : (
                      <Building2 className="w-6 h-6 text-slate-400" />
                    )}
                  </div>
                  <div>
                    <h2 className="text-xl md:text-2xl font-serif font-bold text-slate-900 mb-0.5">{selectedJob.role}</h2>
                    <div className="flex items-center gap-2 text-sm text-slate-600 font-medium">
                      <span>{selectedJob.company}</span>
                      <span className="w-1 h-1 rounded-full bg-slate-300" />
                      <span className={cn(
                        "px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider",
                        SECTIONS.find(c => c.id === selectedJob.status)?.bg,
                        SECTIONS.find(c => c.id === selectedJob.status)?.color
                      )}>
                        {SECTIONS.find(c => c.id === selectedJob.status)?.title}
                      </span>
                      {selectedJob.umbrellaName && (
                        <span className="px-2 py-0.5 rounded-md text-[10px] font-medium bg-violet-50 text-violet-600">
                          {selectedJob.umbrellaName}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => { setSelectedJob(null); setEditingNotes(false); setEditingDescription(false); }}
                  className="p-2 text-slate-400 hover:text-slate-700 hover:bg-slate-200 rounded-full transition-colors"
                >
                  <X className="w-6 h-6" />
                </button>
              </div>

              {/* Sprint 7: Dead listing warning banner */}
              {selectedJob.listingAlive === false && (
                <div className="mx-4 md:mx-5 mt-3 px-4 py-3 bg-orange-50 border border-orange-200 rounded-xl text-sm text-orange-700 font-medium">
                  This posting may no longer be active.{selectedJob.listingDiedAt && ` Detected ${formatDistanceToNow(new Date(selectedJob.listingDiedAt))} ago.`}
                </div>
              )}
              {/* Sprint 5: Match score in modal */}
              {selectedJob.matchScore != null && (
                <div className={cn(
                  "mx-4 md:mx-5 mt-3 px-4 py-3 rounded-xl text-sm font-medium border",
                  selectedJob.matchScore >= 80 ? "bg-emerald-50 border-emerald-200 text-emerald-700" :
                  selectedJob.matchScore >= 50 ? "bg-amber-50 border-amber-200 text-amber-700" :
                  "bg-red-50 border-red-200 text-red-600"
                )}>
                  {selectedJob.matchScore}% match with your profile
                </div>
              )}

              {/* Modal Body */}
              <div className="flex-1 overflow-y-auto p-4 md:p-5 flex flex-col md:flex-row gap-5">
                {/* Left Column: Main Content */}
                <div className="flex-1 space-y-6">
                  {/* Notes Section */}
                  <section>
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                        <StickyNote className="w-5 h-5 text-indigo-500" />
                        My Notes
                      </h3>
                      {editingNotes ? (
                        <button
                          onClick={handleSaveNotes}
                          disabled={savingField === 'notes'}
                          className="text-sm font-medium text-emerald-600 hover:text-emerald-700 flex items-center gap-1"
                        >
                          <Check className="w-4 h-4" />
                          {savingField === 'notes' ? 'Saving...' : 'Save'}
                        </button>
                      ) : (
                        <button onClick={startEditingNotes} className="text-sm font-medium text-indigo-600 hover:text-indigo-700">Edit</button>
                      )}
                    </div>
                    {editingNotes ? (
                      <textarea
                        autoFocus
                        value={notesText}
                        onChange={(e) => setNotesText(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSaveNotes();
                        }}
                        className="w-full p-4 border border-indigo-200 rounded-2xl text-slate-700 text-sm leading-relaxed min-h-[120px] resize-y focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
                        placeholder="Add interview prep notes, thoughts, or reminders..."
                      />
                    ) : selectedJob.notes ? (
                      <div className="p-4 bg-amber-50/50 border border-amber-100 rounded-2xl text-slate-700 text-sm whitespace-pre-wrap leading-relaxed">
                        {selectedJob.notes}
                      </div>
                    ) : (
                      <div
                        onClick={startEditingNotes}
                        className="p-4 border border-dashed border-slate-200 rounded-2xl text-slate-400 text-sm text-center cursor-text hover:bg-slate-50 transition-colors"
                      >
                        Click to add interview prep notes, thoughts, or reminders...
                      </div>
                    )}
                  </section>

                  {/* Job Description Section */}
                  <section>
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                        <AlignLeft className="w-5 h-5 text-indigo-500" />
                        Job Description
                      </h3>
                      {editingDescription ? (
                        <button
                          onClick={handleSaveDescription}
                          disabled={savingField === 'description'}
                          className="text-sm font-medium text-emerald-600 hover:text-emerald-700 flex items-center gap-1"
                        >
                          <Check className="w-4 h-4" />
                          {savingField === 'description' ? 'Saving...' : 'Save'}
                        </button>
                      ) : (
                        <button onClick={startEditingDescription} className="text-sm font-medium text-indigo-600 hover:text-indigo-700">Edit</button>
                      )}
                    </div>
                    {editingDescription ? (
                      <textarea
                        autoFocus
                        value={descriptionText}
                        onChange={(e) => setDescriptionText(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSaveDescription();
                        }}
                        className="w-full p-4 border border-indigo-200 rounded-2xl text-slate-700 text-sm leading-relaxed min-h-[200px] resize-y focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
                        placeholder="Paste the job description here..."
                      />
                    ) : selectedJob.description ? (
                      <div className="prose prose-slate prose-sm max-w-none whitespace-pre-wrap text-slate-600">
                        {selectedJob.description}
                      </div>
                    ) : (
                      <div
                        onClick={startEditingDescription}
                        className="p-4 border border-dashed border-slate-200 rounded-2xl text-slate-400 text-sm text-center cursor-text hover:bg-slate-50 transition-colors"
                      >
                        Paste the job description here for easy reference...
                      </div>
                    )}
                  </section>

                  {/* Tech Stack in detail modal */}
                  {selectedJob.techStack && selectedJob.techStack.length > 0 && (
                    <section>
                      <h3 className="text-lg font-bold text-slate-900 mb-3">Tech Stack</h3>
                      <div className="flex flex-wrap gap-2">
                        {selectedJob.techStack.map(tech => (
                          <span key={tech} className="px-2.5 py-1 text-xs font-medium bg-indigo-50 text-indigo-600 rounded-lg border border-indigo-100">
                            {tech}
                          </span>
                        ))}
                      </div>
                    </section>
                  )}

                  {/* Sprint 9: Warm Connections placeholder */}
                  <WarmConnectionsSection jobId={selectedJob.id} company={selectedJob.company} />
                </div>

                {/* Right Column: Metadata & Actions */}
                <div className="w-full md:w-64 shrink-0 space-y-5">
                  {/* Quick Actions */}
                  <div className="flex flex-col gap-2">
                    {selectedJob.url && (
                      <a href={selectedJob.url} target="_blank" rel="noopener noreferrer" className="w-full py-2 px-3 bg-slate-900 text-white text-sm font-medium rounded-xl shadow-sm hover:bg-slate-800 transition-colors flex items-center justify-center gap-2">
                        <ExternalLink className="w-4 h-4" />
                        View Original Posting
                      </a>
                    )}
                    <div className="relative w-full">
                      <select
                        value={selectedJob.status}
                        onChange={(e) => updateJobStatus(selectedJob.id, e.target.value as JobStatus)}
                        className="w-full appearance-none py-2 px-3 bg-white border border-slate-200 text-slate-700 text-sm font-medium rounded-xl shadow-sm hover:bg-slate-50 transition-colors cursor-pointer outline-none focus:ring-2 focus:ring-indigo-500"
                      >
                        <option value="interviewing">Move to Interviewing</option>
                        <option value="offer">Move to Offer</option>
                        <option value="applied">Move to Applied</option>
                        <option value="saved">Move to Saved</option>
                        <option value="rejected">Move to Rejected</option>
                      </select>
                      <ChevronDown className="w-4 h-4 text-slate-400 absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none" />
                    </div>
                  </div>

                  {/* Details Card */}
                  <div className="bg-slate-50 border border-slate-100 rounded-xl p-4 space-y-3">
                    <h4 className="font-bold text-slate-900 text-xs uppercase tracking-wider">Details</h4>

                    <div className="space-y-2.5">
                      <div className="flex items-start gap-2.5">
                        <MapPin className="w-3.5 h-3.5 text-slate-400 mt-0.5 shrink-0" />
                        <div>
                          <div className="text-[11px] font-medium text-slate-500">Location</div>
                          <div className="text-sm text-slate-900 font-medium">{selectedJob.location}</div>
                        </div>
                      </div>

                      {selectedJob.salary && (
                        <div className="flex items-start gap-2.5">
                          <DollarSign className="w-3.5 h-3.5 text-slate-400 mt-0.5 shrink-0" />
                          <div>
                            <div className="text-[11px] font-medium text-slate-500">Compensation</div>
                            <div className="text-sm text-slate-900 font-medium">{selectedJob.salary}</div>
                          </div>
                        </div>
                      )}

                      <div className="flex items-start gap-2.5">
                        <Calendar className="w-3.5 h-3.5 text-slate-400 mt-0.5 shrink-0" />
                        <div>
                          <div className="text-[11px] font-medium text-slate-500">Date Added</div>
                          <div className="text-sm text-slate-900 font-medium">{format(new Date(selectedJob.dateAdded), 'MMMM d, yyyy')}</div>
                        </div>
                      </div>

                      {selectedJob.source && (
                        <div className="flex items-start gap-2.5">
                          <LinkIcon className="w-3.5 h-3.5 text-slate-400 mt-0.5 shrink-0" />
                          <div>
                            <div className="text-[11px] font-medium text-slate-500">Source</div>
                            <div className="text-sm text-slate-900 font-medium capitalize">{selectedJob.source.replace('_', ' ')}</div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Contacts Card */}
                  {selectedJob.contacts && selectedJob.contacts.length > 0 && (
                    <div className="bg-slate-50 border border-slate-100 rounded-xl p-4 space-y-3">
                      <h4 className="font-bold text-slate-900 text-xs uppercase tracking-wider flex items-center gap-2">
                        <Users className="w-3.5 h-3.5" />
                        Contacts
                      </h4>
                      <div className="space-y-2.5">
                        {selectedJob.contacts.map(contact => (
                          <div key={contact.id} className="flex flex-col">
                            <span className="text-sm font-bold text-slate-900">{contact.name}</span>
                            <span className="text-xs text-slate-500">{contact.role}</span>
                            <a href={`mailto:${contact.email}`} className="text-xs text-indigo-600 hover:underline mt-0.5">{contact.email}</a>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* Add Job Modal */}
      <AnimatePresence>
        {showAddModal && (
          <AddJobModal
            isOpen={showAddModal}
            onClose={() => setShowAddModal(false)}
            onJobAdded={handleJobAdded}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
