import { Search, MapPin, Building2, X, ExternalLink, DollarSign } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import React, { useId, useRef, useState } from 'react';
import { Job } from '../types';
import { searchJobs, createJob } from '../lib/api';
import { DialogShell } from './DialogShell';

interface JobSearchProps {
  jobs: Job[];
  setJobs: (jobs: Job[]) => void;
}

export function JobSearch({ jobs, setJobs }: JobSearchProps) {
  const selectedJobTitleId = useId();
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const [selectedJob, setSelectedJob] = useState<any | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [isSearching, setIsSearching] = useState(false);

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setIsSearching(true);
    try {
      const results = await searchJobs(searchQuery);
      setSearchResults(results.map((r: any) => ({
        id: r.id || r.url || Math.random().toString(),
        company: r.company || 'Unknown',
        role: r.title || 'Unknown Role',
        location: r.location || '',
        salary: r.salary || '',
        type: 'Full-time',
        posted: r.posted_at ? new Date(r.posted_at).toLocaleDateString() : 'Recently',
        description: r.description || r.source || '',
        logoUrl: `https://logo.clearbit.com/${(r.company || '').toLowerCase().replace(/\s+/g, '')}.com`,
        url: r.url,
      })));
    } catch (err) {
      console.error('Search failed:', err);
    } finally {
      setIsSearching(false);
    }
  };

  const handleSave = async (e: React.MouseEvent, result: any) => {
    e.stopPropagation();
    if (jobs.some(j => j.company === result.company && j.role === result.role)) return;

    const newJob: Job = {
      id: result.id,
      company: result.company,
      role: result.role,
      location: result.location,
      salary: result.salary,
      status: 'saved',
      dateAdded: new Date().toISOString(),
      logoUrl: result.logoUrl,
      source: 'other',
      url: result.url,
      description: result.description,
    };

    // Optimistic update
    setJobs([...jobs, newJob]);

    // Persist to backend
    try {
      const saved = await createJob(newJob);
      setJobs(prev => prev.map(j => j.id === result.id ? saved : j));
    } catch (err) {
      console.error('Failed to save job:', err);
    }
  };
  return (
    <div className="flex-1 h-full overflow-y-auto p-4 md:p-8 bg-[#F5F5F0]">
      <div className="w-full">
        <div className="mb-8">
          <h1 className="text-3xl tracking-tight font-serif font-bold text-slate-900">
            Job Search
          </h1>
          <p className="mt-1 text-slate-500 font-serif italic">
            Discover opportunities tailored to your profile.
          </p>
        </div>

        <div className="p-4 mb-8 flex flex-col sm:flex-row items-center gap-4 bg-white rounded-3xl shadow-sm border border-slate-100">
          <div className="flex-1 w-full flex items-center gap-3 px-4 py-2 transition-all bg-slate-50 rounded-xl border border-slate-100 focus-within:border-indigo-300 focus-within:ring-2 focus-within:ring-indigo-100">
            <Search className="w-5 h-5 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="Search roles, companies, or keywords..."
              className="bg-transparent border-none outline-none w-full text-sm text-slate-900 placeholder:text-slate-400"
            />
          </div>
          <div className="flex items-center gap-4 w-full sm:w-auto">
            <button
              onClick={handleSearch}
              disabled={isSearching}
              className="flex-1 sm:flex-none px-6 py-3 text-sm transition-all bg-slate-800 hover:bg-slate-900 text-white rounded-xl font-medium shadow-sm disabled:opacity-50"
            >
              {isSearching ? 'Searching...' : 'Search'}
            </button>
          </div>
        </div>

        {searchResults.length === 0 && !isSearching && (
          <div className="text-center py-16 text-slate-400">
            <Search className="w-12 h-12 mx-auto mb-4 opacity-30" />
            <p className="text-lg font-serif">Search for jobs to get started</p>
            <p className="text-sm mt-1">Try &quot;software engineer&quot; or &quot;product designer&quot;</p>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {searchResults.map((result, i) => {
            const isSaved = jobs.some(j => j.company === result.company && j.role === result.role);
            return (
            <motion.div 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              key={result.id} 
              onClick={() => setSelectedJob(result)}
              onKeyDown={(event) => {
                if (event.target !== event.currentTarget) return;
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  setSelectedJob(result);
                }
              }}
              role="button"
              tabIndex={0}
              aria-label={`Open ${result.role} at ${result.company}`}
              className="p-5 group cursor-pointer transition-all bg-white rounded-3xl border border-slate-100 hover:shadow-[0_8px_30px_rgb(0,0,0,0.04)] focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-300"
            >
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 flex items-center justify-center rounded-xl bg-slate-100">
                    {result.logoUrl ? (
                      <img src={result.logoUrl} alt={result.company} className="w-10 h-10 rounded-xl" referrerPolicy="no-referrer" />
                    ) : (
                      <Building2 className="w-5 h-5 text-slate-400" />
                    )}
                  </div>
                  <div>
                    <h3 className="text-lg font-serif font-bold text-slate-900">{result.role}</h3>
                    <p className="text-sm text-slate-500 font-sans">{result.company}</p>
                  </div>
                </div>
                <button 
                  onClick={(e) => handleSave(e, result)}
                  disabled={isSaved}
                  className="text-sm font-medium opacity-0 group-hover:opacity-100 transition-opacity text-indigo-600 disabled:text-slate-400 disabled:opacity-100"
                >
                  {isSaved ? 'Saved' : 'Save'}
                </button>
              </div>
              
              <div className="space-y-1.5 mb-4">
                <div className="flex items-center text-xs gap-1.5 text-slate-500">
                  <MapPin className="w-3.5 h-3.5 shrink-0" />
                  <span className="truncate">{result.location}</span>
                </div>
                <div className="flex items-center text-xs gap-1.5 text-slate-500">
                  <DollarSign className="w-3.5 h-3.5 shrink-0" />
                  <span className="truncate">{result.salary}</span>
                </div>
              </div>

              <p className="text-sm line-clamp-2 mb-4 text-slate-500">
                {result.description}
              </p>

              <div className="flex items-center justify-between pt-4 border-t border-slate-100">
                <span className="text-xs text-slate-400">Posted {result.posted}</span>
                <button className="text-sm transition-colors font-medium text-slate-900 hover:text-indigo-600">
                  View Details &rarr;
                </button>
              </div>
            </motion.div>
            );
          })}
        </div>
      </div>

      <AnimatePresence>
        {selectedJob && (
          <DialogShell
            onClose={() => setSelectedJob(null)}
            titleId={selectedJobTitleId}
            initialFocusRef={closeButtonRef}
            wrapperClassName="fixed inset-0 z-50 flex items-center justify-center p-4"
            overlayClassName="absolute inset-0 bg-slate-900/20 backdrop-blur-sm"
            panelClassName="bg-white w-full max-w-2xl max-h-[90vh] flex flex-col rounded-3xl shadow-2xl border border-slate-100 relative overflow-hidden"
          >
              {/* Modal Header */}
              <div className="p-6 border-b border-slate-100 flex items-start justify-between bg-slate-50/50 shrink-0">
                <div className="flex items-start gap-4 pr-4">
                  {selectedJob.logoUrl ? (
                    <img src={selectedJob.logoUrl} alt={selectedJob.company} className="w-16 h-16 rounded-2xl border border-slate-100 shrink-0 bg-white" referrerPolicy="no-referrer" />
                  ) : (
                    <div className="w-16 h-16 flex items-center justify-center rounded-2xl bg-white border border-slate-100 shrink-0">
                      <Building2 className="w-8 h-8 text-slate-400" />
                    </div>
                  )}
                  <div className="min-w-0 flex-1">
                    <h2 id={selectedJobTitleId} className="text-2xl tracking-tight font-serif font-bold text-slate-900 break-words">{selectedJob.role}</h2>
                    <p className="text-lg text-slate-500 font-sans truncate">{selectedJob.company}</p>
                  </div>
                </div>
                <button 
                  ref={closeButtonRef}
                  onClick={() => setSelectedJob(null)}
                  aria-label="Close job search details"
                  className="w-8 h-8 flex items-center justify-center rounded-full bg-slate-200/50 text-slate-500 hover:bg-slate-200 transition-colors shrink-0"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Modal Body */}
              <div className="flex-1 overflow-y-auto p-6">
                <div className="space-y-2 mb-8">
                  <div className="flex items-center text-sm gap-2 text-slate-500">
                    <MapPin className="w-4 h-4 shrink-0" />
                    <span className="truncate">{selectedJob.location}</span>
                  </div>
                  <div className="flex items-center text-sm gap-2 text-slate-500">
                    <DollarSign className="w-4 h-4 shrink-0" />
                    <span className="truncate">{selectedJob.salary}</span>
                  </div>
                </div>

                <div className="prose prose-slate max-w-none mb-4">
                  <h3 className="text-xl font-serif font-bold text-slate-900 mb-2">About the role</h3>
                  <p className="text-slate-600 leading-relaxed">{selectedJob.description}</p>
                  <p className="text-slate-600 leading-relaxed mt-4">
                    Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.
                  </p>
                  <h3 className="text-xl font-serif font-bold text-slate-900 mt-6 mb-2">Requirements</h3>
                  <ul className="list-disc pl-5 text-slate-600 space-y-2">
                    <li>3+ years of experience in a similar role</li>
                    <li>Strong portfolio demonstrating your skills</li>
                    <li>Excellent communication and collaboration abilities</li>
                    <li>Experience working in a fast-paced environment</li>
                  </ul>
                </div>
              </div>

              {/* Modal Footer */}
              <div className="p-6 border-t border-slate-100 bg-slate-50/50 shrink-0 flex flex-col sm:flex-row items-center gap-4">
                <button 
                  onClick={(e) => handleSave(e, selectedJob)}
                  disabled={jobs.some(j => j.company === selectedJob.company && j.role === selectedJob.role)}
                  className="w-full sm:flex-1 py-3 bg-slate-800 hover:bg-slate-900 text-white rounded-xl font-medium shadow-sm transition-colors disabled:bg-slate-200 disabled:text-slate-500"
                >
                  {jobs.some(j => j.company === selectedJob.company && j.role === selectedJob.role) ? 'Saved to Pipeline' : 'Save to Pipeline'}
                </button>
                {selectedJob?.url ? (
                  <button
                    onClick={() => window.open(selectedJob.url, '_blank')}
                    className="flex items-center justify-center gap-2 w-full sm:flex-1 py-3 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 rounded-xl font-medium transition-colors"
                  >
                    Apply on Company Site <ExternalLink className="w-4 h-4 shrink-0" />
                  </button>
                ) : (
                  <button
                    disabled
                    className="flex items-center justify-center gap-2 w-full sm:flex-1 py-3 bg-slate-50 border border-slate-200 text-slate-400 rounded-xl font-medium cursor-not-allowed"
                    title="No application URL available"
                  >
                    Apply on Company Site <ExternalLink className="w-4 h-4 shrink-0" />
                  </button>
                )}
              </div>
          </DialogShell>
        )}
      </AnimatePresence>
    </div>
  );
}
