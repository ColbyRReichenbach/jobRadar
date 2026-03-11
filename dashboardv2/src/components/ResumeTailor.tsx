import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { FileText, Sparkles, Clock, Trash2, ChevronDown, ChevronUp, Loader2, Download } from 'lucide-react';
import { apiFetch, authHeaders, fetchResumeDraft, fetchResumeDrafts } from '../lib/api';

interface ResumeDraft {
  id: string;
  application_id: string;
  original_text?: string;
  tailored_text: string;
  changes_summary: string;
  match_improvements?: string;
  created_at: string;
}

interface ResumeTailorProps {
  applicationId: string;
  company: string;
  role: string;
  onClose?: () => void;
}

export function ResumeTailor({ applicationId, company, role, onClose }: ResumeTailorProps) {
  const [drafts, setDrafts] = useState<ResumeDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [selectedDraft, setSelectedDraft] = useState<ResumeDraft | null>(null);
  const [showDiff, setShowDiff] = useState(false);
  const [customResume, setCustomResume] = useState('');
  const [showCustomInput, setShowCustomInput] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  useEffect(() => {
    loadDrafts();
  }, [applicationId]);

  const loadDrafts = async () => {
    setErrorMessage(null);
    try {
      setDrafts(await fetchResumeDrafts(applicationId));
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to load resume drafts.');
    } finally {
      setLoading(false);
    }
  };

  const generateTailored = async () => {
    setGenerating(true);
    setErrorMessage(null);
    setStatusMessage(null);
    try {
      const body: Record<string, string> = {};
      if (customResume.trim()) {
        body.resume_text = customResume.trim();
      }
      const res = await apiFetch(`/api/resume/tailor/${applicationId}`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify(body),
      });
      if (res.ok) {
        const draft = await res.json();
        setDrafts(prev => [draft, ...prev]);
        setSelectedDraft(draft);
        setShowDiff(true);
        setStatusMessage('Tailored resume generated.');
      } else {
        const err = await res.json();
        setErrorMessage(err.detail || 'Failed to generate tailored resume');
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to generate tailored resume.');
    } finally {
      setGenerating(false);
    }
  };

  const deleteDraft = async (draftId: string) => {
    setErrorMessage(null);
    try {
      const res = await apiFetch(`/api/resume/drafts/${applicationId}/${draftId}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        setErrorMessage(err?.detail || 'Failed to delete draft.');
        return;
      }
      setDrafts(prev => prev.filter(d => d.id !== draftId));
      if (selectedDraft?.id === draftId) {
        setSelectedDraft(null);
        setShowDiff(false);
      }
      setStatusMessage('Draft deleted.');
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to delete draft.');
    }
  };

  const selectDraft = async (draft: ResumeDraft) => {
    setErrorMessage(null);
    try {
      const fullDraft = await fetchResumeDraft(applicationId, draft.id);
      setSelectedDraft(fullDraft);
      setShowDiff(true);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to load draft details.');
    }
  };

  const downloadText = (text: string, filename: string) => {
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-serif font-bold text-slate-900">Resume Tailoring</h3>
          <p className="text-xs text-slate-500 mt-0.5">
            AI-tailored for {role} at {company}
          </p>
        </div>
        {onClose && (
          <button onClick={onClose} className="text-xs text-slate-400 hover:text-slate-600">
            Close
          </button>
        )}
      </div>

      {/* Generate Section */}
      {(errorMessage || statusMessage) && (
        <div className={`rounded-2xl border px-4 py-3 text-sm ${
          errorMessage ? 'border-red-200 bg-red-50 text-red-800' : 'border-emerald-200 bg-emerald-50 text-emerald-800'
        }`}>
          {errorMessage || statusMessage}
        </div>
      )}

      <div className="bg-gradient-to-br from-indigo-50 to-blue-50 rounded-2xl border border-indigo-100 p-5">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-100 flex items-center justify-center shrink-0">
            <Sparkles className="w-5 h-5 text-indigo-600" />
          </div>
          <div className="flex-1">
            <h4 className="text-sm font-semibold text-slate-900">Generate Tailored Version</h4>
            <p className="text-xs text-slate-500 mt-0.5">
              AI will reframe your resume to match this job. It never invents experience.
            </p>

            <button
              onClick={() => setShowCustomInput(!showCustomInput)}
              className="flex items-center gap-1 text-xs text-indigo-600 mt-2 hover:text-indigo-800"
            >
              {showCustomInput ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              {showCustomInput ? 'Use saved profile' : 'Paste custom resume text'}
            </button>

            <AnimatePresence>
              {showCustomInput && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="mt-2"
                >
                  <textarea
                    value={customResume}
                    onChange={(e) => setCustomResume(e.target.value)}
                    placeholder="Paste your resume text here..."
                    className="w-full h-32 px-3 py-2 text-xs border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 resize-none font-mono"
                  />
                </motion.div>
              )}
            </AnimatePresence>

            <button
              onClick={generateTailored}
              disabled={generating}
              className="mt-3 flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-xs font-medium rounded-xl hover:bg-indigo-700 transition-colors disabled:opacity-50"
            >
              {generating ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  Tailoring...
                </>
              ) : (
                <>
                  <Sparkles className="w-3.5 h-3.5" />
                  Generate Tailored Resume
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Diff View */}
      <AnimatePresence>
        {showDiff && selectedDraft && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="bg-white rounded-2xl border border-slate-200/60 overflow-hidden"
          >
            {/* Changes Summary */}
            {selectedDraft.changes_summary && (
              <div className="px-5 py-3 bg-emerald-50 border-b border-emerald-100">
                <h4 className="text-xs font-semibold text-emerald-800 mb-1">Changes Made</h4>
                <p className="text-xs text-emerald-700 whitespace-pre-line">
                  {selectedDraft.changes_summary}
                </p>
              </div>
            )}

            {selectedDraft.match_improvements && (
              <div className="px-5 py-3 bg-blue-50 border-b border-blue-100">
                <h4 className="text-xs font-semibold text-blue-800 mb-1">Keyword Alignments</h4>
                <p className="text-xs text-blue-700">{selectedDraft.match_improvements}</p>
              </div>
            )}

            {/* Side-by-side diff */}
            <div className="grid grid-cols-2 divide-x divide-slate-200">
              <div className="p-4">
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Original</h4>
                  {selectedDraft.original_text && (
                    <button
                      onClick={() => downloadText(selectedDraft.original_text!, `resume-original-${company}.txt`)}
                      className="p-1 text-slate-400 hover:text-slate-600"
                    >
                      <Download className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
                <pre className="text-xs text-slate-600 whitespace-pre-wrap font-mono leading-relaxed max-h-96 overflow-auto">
                  {selectedDraft.original_text || 'Original text not available'}
                </pre>
              </div>
              <div className="p-4">
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-xs font-semibold text-indigo-600 uppercase tracking-wide">Tailored</h4>
                  <button
                    onClick={() => downloadText(selectedDraft.tailored_text, `resume-tailored-${company}.txt`)}
                    className="p-1 text-slate-400 hover:text-slate-600"
                  >
                    <Download className="w-3.5 h-3.5" />
                  </button>
                </div>
                <pre className="text-xs text-slate-800 whitespace-pre-wrap font-mono leading-relaxed max-h-96 overflow-auto">
                  {selectedDraft.tailored_text}
                </pre>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Draft History */}
      {drafts.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-slate-900 mb-3 flex items-center gap-2">
            <Clock className="w-4 h-4 text-slate-400" />
            Draft History ({drafts.length})
          </h4>
          <div className="space-y-2">
            {drafts.map((draft) => (
              <motion.div
                key={draft.id}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className={`flex items-center justify-between p-3 rounded-xl border transition-colors cursor-pointer ${
                  selectedDraft?.id === draft.id
                    ? 'border-indigo-200 bg-indigo-50/50'
                    : 'border-slate-200/60 bg-white hover:bg-slate-50'
                }`}
                onClick={() => selectDraft(draft)}
              >
                <div className="flex items-center gap-3">
                  <FileText className="w-4 h-4 text-slate-400" />
                  <div>
                    <p className="text-xs font-medium text-slate-700">
                      {new Date(draft.created_at).toLocaleDateString('en-US', {
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </p>
                    {draft.changes_summary && (
                      <p className="text-xs text-slate-500 mt-0.5 line-clamp-1">
                        {draft.changes_summary.split('\n')[0]}
                      </p>
                    )}
                  </div>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteDraft(draft.id);
                  }}
                  className="p-1.5 text-slate-300 hover:text-red-500 transition-colors"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </motion.div>
            ))}
          </div>
        </div>
      )}

      {/* Empty State */}
      {drafts.length === 0 && !generating && (
        <div className="text-center py-8">
          <FileText className="w-10 h-10 text-slate-300 mx-auto mb-3" />
          <p className="text-sm text-slate-500">No tailored versions yet</p>
          <p className="text-xs text-slate-400 mt-1">Generate one above to get started</p>
        </div>
      )}
    </div>
  );
}
