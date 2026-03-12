import { type FormEvent, useEffect, useId, useMemo, useRef, useState } from 'react';
import { Contact, Job, JobStatus } from '../types';
import { checkJobDuplicates, createJob, fetchNetworkContacts, linkContactToApplication } from '../lib/api';
import { Link2, Search, X } from 'lucide-react';
import { DialogShell } from './DialogShell';

interface AddJobModalProps {
  isOpen: boolean;
  onClose: () => void;
  onJobAdded: (job: Job) => void;
  initialValues?: Partial<Job> | null;
}

export function AddJobModal({ isOpen, onClose, onJobAdded, initialValues }: AddJobModalProps) {
  const titleId = useId();
  const companyInputRef = useRef<HTMLInputElement>(null);
  const [company, setCompany] = useState('');
  const [role, setRole] = useState('');
  const [url, setUrl] = useState('');
  const [location, setLocation] = useState('');
  const [salary, setSalary] = useState('');
  const [status, setStatus] = useState<JobStatus>('saved');
  const [notes, setNotes] = useState('');
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [contactsQuery, setContactsQuery] = useState('');
  const [selectedContactIds, setSelectedContactIds] = useState<string[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [duplicateWarning, setDuplicateWarning] = useState<{ type: 'soft' | 'hard'; message: string; matches: any[] } | null>(null);

  const resetForm = () => {
    setCompany(initialValues?.company || '');
    setRole(initialValues?.role || '');
    setUrl(initialValues?.url || '');
    setLocation(initialValues?.location || '');
    setSalary(initialValues?.salary || '');
    setStatus(initialValues?.status || 'saved');
    setNotes(initialValues?.notes || '');
    setContactsQuery('');
    setSelectedContactIds([]);
    setError('');
    setDuplicateWarning(null);
  };

  useEffect(() => {
    if (!isOpen) return;
    fetchNetworkContacts()
      .then((items) => {
        setContacts(
          items
            .filter((item: any) => item.email)
            .map((item: any) => ({
              id: item.id,
              name: item.name || item.email || '',
              role: item.title || '',
              email: item.email || '',
              linkedin: item.linkedin_url || undefined,
            })),
        );
      })
      .catch(() => setContacts([]));
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    resetForm();
  }, [initialValues, isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const hasEnoughData = Boolean(url.trim()) || Boolean(company.trim() && role.trim());
    if (!hasEnoughData) {
      setDuplicateWarning(null);
      return;
    }

    const timeout = window.setTimeout(async () => {
      try {
        const result = await checkJobDuplicates({
          company: company.trim(),
          role_title: role.trim(),
          job_url: url.trim() || undefined,
          location: location.trim() || undefined,
        });
        if (result.duplicate_type === 'none') {
          setDuplicateWarning(null);
          return;
        }
        setDuplicateWarning({
          type: result.duplicate_type,
          message: result.message || 'Potential duplicate found.',
          matches: result.matches || [],
        });
      } catch {
        setDuplicateWarning(null);
      }
    }, 250);

    return () => window.clearTimeout(timeout);
  }, [company, role, url, location, isOpen]);

  const filteredContacts = useMemo(() => {
    const query = contactsQuery.trim().toLowerCase();
    if (!query) return contacts.slice(0, 8);
    return contacts
      .filter((contact) => `${contact.name} ${contact.role} ${contact.email}`.toLowerCase().includes(query))
      .slice(0, 8);
  }, [contacts, contactsQuery]);

  if (!isOpen) return null;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!company.trim() || !role.trim()) return;
    if (duplicateWarning?.type === 'hard') {
      setError(duplicateWarning.message);
      return;
    }

    setIsSubmitting(true);
    setError('');

    try {
      const newJob = await createJob({
        company: company.trim(),
        role: role.trim(),
        url: url.trim() || undefined,
        location: location.trim() || undefined,
        salary: salary.trim() || undefined,
        status,
        notes: notes.trim() || undefined,
      });
      if (selectedContactIds.length > 0) {
        await Promise.all(
          selectedContactIds.map((contactId) => linkContactToApplication(contactId, newJob.id)),
        );
      }
      onJobAdded(newJob);
      onClose();
      resetForm();
    } catch (err: any) {
      if (err.message?.includes('409')) {
        setError('This job is already in your pipeline.');
      } else {
        setError('Failed to add job. Please try again.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const toggleContact = (contactId: string) => {
    setSelectedContactIds((current) => (
      current.includes(contactId)
        ? current.filter((id) => id !== contactId)
        : [...current, contactId]
    ));
  };

  return (
    <DialogShell
      onClose={onClose}
      titleId={titleId}
      initialFocusRef={companyInputRef}
      panelClassName="fixed inset-4 md:inset-auto md:top-1/2 md:left-1/2 md:-translate-x-1/2 md:-translate-y-1/2 md:w-full md:max-w-lg bg-white rounded-3xl shadow-2xl z-50 flex flex-col overflow-hidden"
    >
        <div className="p-5 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
          <h2 id={titleId} className="text-xl font-serif font-bold text-slate-900">Add Job</h2>
          <button
            onClick={onClose}
            aria-label="Close add job dialog"
            className="p-2 text-slate-400 hover:text-slate-700 hover:bg-slate-200 rounded-full transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-5 space-y-4">
          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">
              {error}
            </div>
          )}

          {duplicateWarning && !error && (
            <div className={`rounded-xl border px-3 py-3 text-sm ${
              duplicateWarning.type === 'hard'
                ? 'border-red-200 bg-red-50 text-red-700'
                : 'border-amber-200 bg-amber-50 text-amber-800'
            }`}>
              <div className="font-medium">{duplicateWarning.message}</div>
              {duplicateWarning.matches.length > 0 && (
                <div className="mt-2 space-y-1 text-xs">
                  {duplicateWarning.matches.slice(0, 2).map((match) => (
                    <div key={match.id}>
                      {match.company} · {match.role_title}
                      {match.location ? ` · ${match.location}` : ''}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Company *</label>
            <input
              ref={companyInputRef}
              type="text"
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              required
              className="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
              placeholder="e.g. Google"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Role *</label>
            <input
              type="text"
              value={role}
              onChange={(e) => setRole(e.target.value)}
              required
              className="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
              placeholder="e.g. Software Engineer"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Job URL</label>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
              placeholder="https://..."
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Location</label>
              <input
                type="text"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                className="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                placeholder="e.g. Remote"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Salary</label>
              <input
                type="text"
                value={salary}
                onChange={(e) => setSalary(e.target.value)}
                className="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                placeholder="e.g. $150k-$200k"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Status</label>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as JobStatus)}
              className="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
            >
              <option value="saved">Saved</option>
              <option value="applied">Applied</option>
              <option value="interviewing">Interviewing</option>
              <option value="offer">Offer</option>
              <option value="rejected">Rejected</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Notes</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              className="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 resize-y"
              placeholder="Any notes about this opportunity..."
            />
          </div>

          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Link2 className="w-4 h-4 text-slate-400" />
              <label className="block text-sm font-medium text-slate-700">Link Existing Contacts</label>
            </div>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="text"
                value={contactsQuery}
                onChange={(e) => setContactsQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                placeholder="Search your network..."
              />
            </div>
            {selectedContactIds.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {selectedContactIds.map((contactId) => {
                  const contact = contacts.find((item) => item.id === contactId);
                  if (!contact) return null;
                  return (
                    <button
                      key={contactId}
                      type="button"
                      onClick={() => toggleContact(contactId)}
                      className="inline-flex items-center gap-2 rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700"
                    >
                      {contact.name || contact.email}
                      <X className="w-3 h-3" />
                    </button>
                  );
                })}
              </div>
            )}
            <div className="max-h-44 overflow-y-auto rounded-2xl border border-slate-200 bg-slate-50/60 p-2 space-y-2">
              {filteredContacts.length === 0 ? (
                <p className="px-2 py-4 text-center text-sm text-slate-400">No matching contacts found.</p>
              ) : (
                filteredContacts.map((contact) => {
                  const selected = selectedContactIds.includes(contact.id);
                  return (
                    <button
                      key={contact.id}
                      type="button"
                      onClick={() => toggleContact(contact.id)}
                      className={`w-full rounded-xl border px-3 py-2 text-left transition-colors ${
                        selected
                          ? 'border-indigo-200 bg-indigo-50 text-indigo-900'
                          : 'border-transparent bg-white hover:border-slate-200'
                      }`}
                    >
                      <div className="text-sm font-medium">{contact.name || contact.email}</div>
                      <div className="text-xs text-slate-500">
                        {[contact.role, contact.email].filter(Boolean).join(' • ')}
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2.5 bg-white border border-slate-200 text-slate-700 text-sm font-medium rounded-xl hover:bg-slate-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting || !company.trim() || !role.trim()}
              className="flex-1 py-2.5 bg-slate-800 text-white text-sm font-medium rounded-xl hover:bg-slate-900 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSubmitting ? 'Adding...' : 'Add Job'}
            </button>
          </div>
        </form>
    </DialogShell>
  );
}
