import { Search, MapPin, Building2, X, ExternalLink, DollarSign } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import type { Dispatch, MouseEvent, SetStateAction } from 'react';
import { useId, useRef, useState } from 'react';
import { Job } from '../types';
import { searchJobs, createJob, checkJobDuplicates, createResearchProfile, getSearchMatchPreview } from '../lib/api';
import type { JobSearchResponse } from '../lib/api';
import { DialogShell } from './DialogShell';

interface JobSearchProps {
  jobs: Job[];
  setJobs: Dispatch<SetStateAction<Job[]>>;
}

interface SearchResult {
  id: string;
  company: string;
  role: string;
  location: string;
  salary: string;
  type: string;
  posted: string;
  description: string;
  logoUrl?: string;
  url?: string;
  matchScore?: number | null;
  fitLabel?: 'best_fit' | 'good_fit' | 'stretch' | null;
  matchedSkills?: string[];
  source?: string;
  sourceLabel?: string;
  freshness?: string;
}

function displayRole(result: SearchResult): string {
  return result.role || 'Role unavailable';
}

function displayCompany(result: SearchResult): string {
  return result.company || 'Company unavailable';
}

function providerLabel(source: string): string {
  const labels: Record<string, string> = {
    greenhouse: 'Greenhouse',
    lever: 'Lever',
    ashby: 'Ashby',
    workable: 'Workable',
    workday: 'Workday',
    smartrecruiters: 'SmartRecruiters',
    structured_data: 'Company source',
    broad_search: 'Broad web',
  };
  return labels[source] || source.replace(/_/g, ' ');
}

function freshnessLabel(value: string): string {
  if (value === 'seen_today') return 'Fresh today';
  if (value === 'stale') return 'Stale';
  return value.replace(/_/g, ' ');
}

function sourceStatusText(response: JobSearchResponse): string | null {
  const summary = response.source_summary;
  const mode = response.provider_status?.mode;
  if (summary?.broad_provider_used) return 'No verified company source yet. Using broad web search.';
  if (summary?.verified_source_count) return 'Searching verified company career sources.';
  if (summary?.stale_source_count) return 'Known source needs refresh. We are checking it now.';
  if (summary?.blocked_source_count) return 'This provider is not available through Opportunity Radar.';
  if (mode === 'provider_limited') return 'Broad search is not configured. Add a company career URL or try a known company.';
  return null;
}

export function JobSearch({ jobs, setJobs }: JobSearchProps) {
  const selectedJobTitleId = useId();
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const [selectedJob, setSelectedJob] = useState<SearchResult | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [sourceSummary, setSourceSummary] = useState<JobSearchResponse['source_summary'] | null>(null);
  const [trackingSourceId, setTrackingSourceId] = useState<string | null>(null);

  const openExternal = (url?: string) => {
    if (!url) return;
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setIsSearching(true);
    setHasSearched(true);
    setErrorMessage(null);
    setStatusMessage(null);
    setSourceSummary(null);
    try {
      const searchResponse = await searchJobs(searchQuery);
      setSourceSummary(searchResponse.source_summary || null);
      const results = searchResponse.results;
      const mappedResults: SearchResult[] = results.map((r: any) => ({
        id: r.id || r.url || Math.random().toString(),
        company: r.company || '',
        role: r.title || '',
        location: r.location || '',
        salary: r.salary || '',
        type: 'Full-time',
        posted: r.posted_at ? new Date(r.posted_at).toLocaleDateString() : 'Recently',
        description: r.description || '',
        logoUrl: r.logo_url || undefined,
        url: r.url,
        source: r.source,
        sourceLabel: r.source_label,
        freshness: r.freshness,
      })).filter((result) => result.company || result.role || result.url);
      try {
        const preview = await getSearchMatchPreview(
          mappedResults.map((result) => ({
            id: result.id,
            title: result.role,
            company: result.company,
            location: result.location,
            salary: result.salary,
            description: result.description,
            url: result.url,
          })),
        );
        const previewMap = new Map((preview.jobs || []).map((item) => [item.id || item.url, item]));
        const enriched = mappedResults.map((result) => {
          const match = previewMap.get(result.id) || previewMap.get(result.url || '');
          return {
            ...result,
            matchScore: match?.score ?? null,
            fitLabel: match?.fit_label ?? null,
            matchedSkills: match?.matched_skills ?? [],
          };
        });
        enriched.sort((a, b) => (b.matchScore ?? -1) - (a.matchScore ?? -1));
        setSearchResults(enriched);
        if (!preview.profile_available) {
          setStatusMessage('Add your profile to unlock best-fit scoring on search results.');
        }
      } catch {
        setSearchResults(mappedResults);
      }
      if (results.length === 0) {
        const providerReasons = searchResponse.provider_status?.degraded_reasons || [];
        setStatusMessage(
          providerReasons.length
            ? `No matching jobs found. ${providerReasons[0]}`
            : 'No matching jobs found for that search.'
        );
      } else {
        setStatusMessage(sourceStatusText(searchResponse));
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Search failed.');
    } finally {
      setIsSearching(false);
    }
  };

  const handleSave = async (e: MouseEvent, result: SearchResult) => {
    e.stopPropagation();
    if (jobs.some(j => j.company === result.company && j.role === result.role)) return;

    if (!result.company || !result.role) {
      setErrorMessage('This result is missing a company or job title, so it cannot be saved yet.');
      return;
    }

    try {
      const duplicateCheck = await checkJobDuplicates({
        company: result.company,
        role_title: result.role,
        job_url: result.url,
        location: result.location,
      });
      if (duplicateCheck.duplicate_type === 'hard') {
        setErrorMessage(duplicateCheck.message || 'This job is already in your pipeline.');
        return;
      }
      if (duplicateCheck.duplicate_type === 'soft') {
        const shouldContinue = window.confirm(
          duplicateCheck.message || 'A similar job already exists in your pipeline. Save this one anyway?'
        );
        if (!shouldContinue) {
          setStatusMessage('Skipped saving duplicate job.');
          return;
        }
      }
    } catch {
      // Keep save flow resilient if the warning check fails.
    }

    const optimisticId = result.id || `search-${crypto.randomUUID()}`;
    const newJob: Job = {
      id: optimisticId,
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

    setErrorMessage(null);
    setStatusMessage(null);
    setJobs(prev => [...prev, newJob]);

    try {
      const saved = await createJob(newJob);
      setJobs(prev => prev.map(j => j.id === optimisticId ? saved : j));
      setStatusMessage(`Saved ${result.role} at ${result.company} to your pipeline.`);
    } catch (err) {
      setJobs(prev => prev.filter(j => j.id !== optimisticId));
      setErrorMessage(err instanceof Error ? err.message : 'Failed to save job.');
    }
  };

  const handleTrackSource = async (e: MouseEvent, result: SearchResult) => {
    e.stopPropagation();
    if (!result.company || !result.role) {
      setErrorMessage('This source is missing a company or job title, so it cannot be tracked yet.');
      return;
    }

    setTrackingSourceId(result.id);
    setErrorMessage(null);
    setStatusMessage(null);
    const sourceName = result.sourceLabel || (result.source ? providerLabel(result.source) : 'company source');
    try {
      await createResearchProfile({
        name: `${result.company} ${result.role} source`,
        objective: `Track ${result.role} opportunities at ${result.company} from ${sourceName}.`,
        selected_domains: [],
        selected_roles: [result.role],
        selected_companies: [result.company],
        keywords: [result.role],
        excluded_keywords: [],
        source_types: ['application'],
        mode: 'internal',
        frequency: 'weekly',
        depth: 'standard',
        notification_mode: 'in_app',
        minimum_score: 70,
        target_locations: result.location ? [result.location] : [],
        remote_types: [],
        seniority_levels: [],
        research_source_scopes: [],
        use_profile_context: true,
        include_public_web_research: false,
        max_search_queries: 8,
        max_sources_per_run: 20,
        active: true,
      });
      setStatusMessage(`Tracking ${result.company} source in Radar.`);
      setSelectedJob(null);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to track this source.');
    } finally {
      setTrackingSourceId(null);
    }
  };

  const fitBadge = (result: SearchResult) => {
    if (result.matchScore == null || !result.fitLabel) return null;
    const badgeStyles: Record<string, string> = {
      best_fit: 'bg-emerald-50 text-emerald-700 border-emerald-200',
      good_fit: 'bg-blue-50 text-blue-700 border-blue-200',
      stretch: 'bg-amber-50 text-amber-700 border-amber-200',
    };
    const labelMap: Record<string, string> = {
      best_fit: 'Best fit',
      good_fit: 'Good fit',
      stretch: 'Stretch',
    };
    return (
      <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${badgeStyles[result.fitLabel]}`}>
        {labelMap[result.fitLabel]}{typeof result.matchScore === 'number' ? ` • ${result.matchScore}` : ''}
      </span>
    );
  };

  const sourceBadges = (result: SearchResult) => {
    const labels = [
      result.sourceLabel || (result.source ? providerLabel(result.source) : null),
      result.freshness ? freshnessLabel(result.freshness) : null,
    ].filter(Boolean);
    if (!labels.length) return null;
    return (
      <div className="mt-2 flex flex-wrap gap-2">
        {labels.map((label) => (
          <span key={`${result.id}-${label}`} className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-semibold text-slate-600">
            {label}
          </span>
        ))}
      </div>
    );
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

        {(errorMessage || statusMessage) && (
          <div className={`mb-6 rounded-2xl border px-4 py-3 text-sm ${
            errorMessage ? 'border-red-200 bg-red-50 text-red-800' : 'border-emerald-200 bg-emerald-50 text-emerald-800'
          }`}>
            {errorMessage || statusMessage}
          </div>
        )}

        {sourceSummary && (
          <div className="mb-6 flex flex-wrap items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-xs text-slate-600">
            <span className="font-semibold text-slate-900">
              {sourceSummary.broad_provider_used ? 'Broad fallback' : sourceSummary.verified_source_count > 0 ? 'Company sources' : 'Source status'}
            </span>
            <span>{sourceSummary.verified_source_count} verified</span>
            <span>{sourceSummary.stale_source_count} stale</span>
            <span>{sourceSummary.blocked_source_count} blocked</span>
          </div>
        )}

        {searchResults.length === 0 && !isSearching && (
          <div className="text-center py-16 text-slate-400">
            <Search className="w-12 h-12 mx-auto mb-4 opacity-30" />
            <p className="text-lg font-serif">{hasSearched ? 'No jobs returned' : 'Search for jobs to get started'}</p>
            <p className="text-sm mt-1">
              {hasSearched
                ? 'Try a broader role query or check that a search provider is configured.'
                : 'Try "software engineer" or "product designer"'}
            </p>
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
              aria-label={`Open ${displayRole(result)} at ${displayCompany(result)}`}
              className="p-5 group cursor-pointer transition-all bg-white rounded-3xl border border-slate-100 hover:shadow-[0_8px_30px_rgb(0,0,0,0.04)] focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-300"
            >
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 flex items-center justify-center rounded-xl bg-slate-100">
                    {result.logoUrl ? (
                      <img src={result.logoUrl} alt={displayCompany(result)} className="w-10 h-10 rounded-xl" referrerPolicy="no-referrer" />
                    ) : (
                      <Building2 className="w-5 h-5 text-slate-400" />
                    )}
                  </div>
                  <div>
                    <h3 className="text-lg font-serif font-bold text-slate-900">{displayRole(result)}</h3>
                    <p className="text-sm text-slate-500 font-sans">{displayCompany(result)}</p>
                    {result.fitLabel && (
                      <div className="mt-2">
                        {fitBadge(result)}
                      </div>
                    )}
                    {sourceBadges(result)}
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

              {result.matchedSkills && result.matchedSkills.length > 0 && (
                <div className="mb-4 flex flex-wrap gap-2">
                  {result.matchedSkills.slice(0, 3).map((skill) => (
                    <span key={`${result.id}-${skill}`} className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-600">
                      {skill}
                    </span>
                  ))}
                </div>
              )}

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
                    <img src={selectedJob.logoUrl} alt={displayCompany(selectedJob)} className="w-16 h-16 rounded-2xl border border-slate-100 shrink-0 bg-white" referrerPolicy="no-referrer" />
                  ) : (
                    <div className="w-16 h-16 flex items-center justify-center rounded-2xl bg-white border border-slate-100 shrink-0">
                      <Building2 className="w-8 h-8 text-slate-400" />
                    </div>
                  )}
                  <div className="min-w-0 flex-1">
                    <h2 id={selectedJobTitleId} className="text-2xl tracking-tight font-serif font-bold text-slate-900 break-words">{displayRole(selectedJob)}</h2>
                    <p className="text-lg text-slate-500 font-sans truncate">{displayCompany(selectedJob)}</p>
                    {sourceBadges(selectedJob)}
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
                  {selectedJob.description ? (
                    <p className="text-slate-600 leading-relaxed whitespace-pre-line">{selectedJob.description}</p>
                  ) : (
                    <p className="text-slate-500 leading-relaxed">No detailed job description was returned for this search result.</p>
                  )}
                  {selectedJob.matchedSkills && selectedJob.matchedSkills.length > 0 && (
                    <>
                      <h3 className="text-xl font-serif font-bold text-slate-900 mt-6 mb-2">Matched skills</h3>
                      <div className="flex flex-wrap gap-2">
                        {selectedJob.matchedSkills.map((skill) => (
                          <span key={`modal-${selectedJob.id}-${skill}`} className="rounded-full bg-slate-100 px-3 py-1 text-sm font-medium text-slate-700">
                            {skill}
                          </span>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              </div>

              {/* Modal Footer */}
              <div className="p-6 border-t border-slate-100 bg-slate-50/50 shrink-0 flex flex-col sm:flex-row items-center gap-4">
                <button 
                  onClick={(e) => handleSave(e, selectedJob)}
                  disabled={
                    !selectedJob.company ||
                    !selectedJob.role ||
                    jobs.some(j => j.company === selectedJob.company && j.role === selectedJob.role)
                  }
                  className="w-full sm:flex-1 py-3 bg-slate-800 hover:bg-slate-900 text-white rounded-xl font-medium shadow-sm transition-colors disabled:bg-slate-200 disabled:text-slate-500"
                >
                  {!selectedJob.company || !selectedJob.role
                    ? 'Missing Required Details'
                    : jobs.some(j => j.company === selectedJob.company && j.role === selectedJob.role)
                      ? 'Saved to Pipeline'
                      : 'Save to Pipeline'}
                </button>
                <button
                  onClick={(e) => handleTrackSource(e, selectedJob)}
                  disabled={!selectedJob.company || !selectedJob.role || trackingSourceId === selectedJob.id}
                  className="w-full sm:flex-1 py-3 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 rounded-xl font-medium transition-colors disabled:bg-slate-50 disabled:text-slate-400"
                >
                  {trackingSourceId === selectedJob.id ? 'Tracking...' : 'Track this source'}
                </button>
                {selectedJob?.url ? (
                  <button
                    onClick={() => openExternal(selectedJob.url)}
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
