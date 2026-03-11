import { useState, useEffect, useId, useMemo, useRef } from 'react';
import { Search, Building2, Mail, Linkedin, User, X } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { apiFetch, authHeaders, fetchNetworkContacts } from '../lib/api';
import { DialogShell } from './DialogShell';

interface NetworkContact {
  id: string;
  name: string | null;
  email: string | null;
  title: string | null;
  company: string | null;
  source: string;
  reached_out: boolean;
  response_received: boolean;
  linkedin_url: string | null;
  email_count?: number;
  last_interaction_at?: string;
}

export function NetworkPage() {
  const contactDialogTitleId = useId();
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const [contacts, setContacts] = useState<NetworkContact[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [selectedContact, setSelectedContact] = useState<NetworkContact | null>(null);
  const [contactDetail, setContactDetail] = useState<any>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    loadContacts();
  }, []);

  const loadContacts = async (q?: string) => {
    setLoading(true);
    setErrorMessage(null);
    try {
      setContacts(await fetchNetworkContacts(q || ''));
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to load network.');
    } finally {
      setLoading(false);
    }
  };

  const filteredContacts = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return contacts;
    return contacts.filter((contact) => {
      const haystack = [
        contact.name,
        contact.email,
        contact.title,
        contact.company,
        contact.source,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [contacts, searchQuery]);

  const openDetail = async (contact: NetworkContact) => {
    setSelectedContact(contact);
    setContactDetail(null);
    setErrorMessage(null);
    if (contact.email) {
      try {
        const res = await apiFetch(`/api/network/${encodeURIComponent(contact.email)}`, { headers: authHeaders() });
        if (res.ok) {
          setContactDetail(await res.json());
        } else {
          const err = await res.json().catch(() => null);
          setErrorMessage(err?.detail || 'Failed to load contact detail.');
        }
      } catch (err) {
        setErrorMessage(err instanceof Error ? err.message : 'Failed to load contact detail.');
      }
    }
  };

  const sourceColors: Record<string, string> = {
    hunter: 'bg-blue-50 text-blue-600',
    email: 'bg-purple-50 text-purple-600',
    warm_path: 'bg-emerald-50 text-emerald-600',
    outbound: 'bg-amber-50 text-amber-600',
  };

  return (
    <div className="flex-1 h-full overflow-y-auto p-4 md:p-8 bg-[#F5F5F0]">
      <div className="w-full">
        <div className="mb-8">
          <h1 className="text-3xl tracking-tight font-serif font-bold text-slate-900">Network</h1>
          <p className="mt-1 text-slate-500 font-serif italic">
            Your professional connections across all sources.
          </p>
        </div>

        <div className="p-4 mb-8 flex items-center gap-4 bg-white rounded-3xl shadow-sm border border-slate-100">
          <div className="flex-1 flex items-center gap-3 px-4 py-2 bg-slate-50 rounded-xl border border-slate-100 focus-within:border-indigo-300 focus-within:ring-2 focus-within:ring-indigo-100">
            <Search className="w-5 h-5 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
              placeholder="Search by name or company..."
              className="bg-transparent border-none outline-none w-full text-sm text-slate-900 placeholder:text-slate-400"
            />
          </div>
          <div className="px-4 py-3 text-xs font-medium uppercase tracking-[0.18em] text-slate-400">
            {filteredContacts.length} results
          </div>
        </div>

        {errorMessage && (
          <div className="mb-6 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
            {errorMessage}
          </div>
        )}

        {loading ? (
          <div className="text-center py-16 text-slate-400">
            <div className="w-8 h-8 border-2 rounded-full border-slate-300 border-t-slate-600 animate-spin mx-auto mb-4" />
            <p className="font-serif">Loading your network...</p>
          </div>
        ) : filteredContacts.length === 0 ? (
          <div className="text-center py-16 text-slate-400">
            <User className="w-12 h-12 mx-auto mb-4 opacity-30" />
            <p className="text-lg font-serif">No contacts found</p>
            <p className="text-sm mt-1">
              {searchQuery ? 'Try a different search term.' : 'Contacts will appear as you track jobs and sync emails.'}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {filteredContacts.map((contact, i) => (
              <motion.div
                key={contact.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.03 }}
                onClick={() => openDetail(contact)}
                onKeyDown={(event) => {
                  if (event.target !== event.currentTarget) return;
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    openDetail(contact);
                  }
                }}
                role="button"
                tabIndex={0}
                aria-label={`Open contact details for ${contact.name || contact.email || 'contact'}`}
                className="p-5 group cursor-pointer transition-all bg-white rounded-2xl border border-slate-100 hover:shadow-[0_8px_30px_rgb(0,0,0,0.04)] focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-300"
              >
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 flex items-center justify-center rounded-full bg-slate-100 text-slate-600 font-bold text-sm shrink-0">
                    {(contact.name || contact.email || '?')[0].toUpperCase()}
                  </div>
                  <div className="min-w-0 flex-1">
                    <h3 className="font-serif font-bold text-slate-900 truncate">{contact.name || contact.email}</h3>
                    {contact.title && <p className="text-xs text-slate-500 truncate">{contact.title}</p>}
                    {contact.company && (
                      <p className="text-xs text-slate-400 flex items-center gap-1 mt-0.5">
                        <Building2 className="w-3 h-3" /> {contact.company}
                      </p>
                    )}
                  </div>
                  <span className={`px-2 py-0.5 text-[10px] font-medium rounded-full ${sourceColors[contact.source] || 'bg-slate-50 text-slate-500'}`}>
                    {contact.source}
                  </span>
                </div>
                {contact.email && (
                  <div className="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between">
                    <span className="text-xs text-slate-400 truncate">{contact.email}</span>
                    <a
                      href={`mailto:${contact.email}`}
                      onClick={(e) => e.stopPropagation()}
                      className="text-xs font-medium text-indigo-600 hover:text-indigo-700 opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      Email
                    </a>
                  </div>
                )}
              </motion.div>
            ))}
          </div>
        )}
      </div>

      {/* Contact Detail Modal */}
      <AnimatePresence>
        {selectedContact && (
          <DialogShell
            onClose={() => { setSelectedContact(null); setContactDetail(null); }}
            titleId={contactDialogTitleId}
            initialFocusRef={closeButtonRef}
            wrapperClassName="fixed inset-0 z-50 flex items-center justify-center p-4"
            overlayClassName="absolute inset-0 bg-slate-900/20 backdrop-blur-sm"
            panelClassName="bg-white w-full max-w-lg max-h-[80vh] flex flex-col rounded-3xl shadow-2xl overflow-hidden"
          >
              <div className="p-6 border-b border-slate-100 bg-slate-50/50">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-center gap-4">
                  <div className="w-14 h-14 flex items-center justify-center rounded-full bg-slate-200 text-slate-700 font-bold text-xl">
                    {(selectedContact.name || selectedContact.email || '?')[0].toUpperCase()}
                  </div>
                  <div>
                    <h2 id={contactDialogTitleId} className="text-xl font-serif font-bold text-slate-900">{selectedContact.name || 'Unknown'}</h2>
                    {selectedContact.title && <p className="text-sm text-slate-500">{selectedContact.title}</p>}
                    {selectedContact.company && <p className="text-sm text-slate-400">{selectedContact.company}</p>}
                  </div>
                  </div>
                  <button
                    ref={closeButtonRef}
                    onClick={() => { setSelectedContact(null); setContactDetail(null); }}
                    aria-label="Close contact details"
                    className="p-1 hover:bg-slate-200 rounded-lg shrink-0"
                  >
                    <X className="w-5 h-5 text-slate-500" />
                  </button>
                </div>
                <div className="flex gap-2 mt-4">
                  {selectedContact.email && (
                    <a
                      href={`mailto:${selectedContact.email}`}
                      className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-white border border-slate-200 rounded-lg text-slate-700 hover:bg-slate-50"
                    >
                      <Mail className="w-3.5 h-3.5" /> Email
                    </a>
                  )}
                  {selectedContact.linkedin_url && (
                    <a
                      href={selectedContact.linkedin_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-white border border-slate-200 rounded-lg text-slate-700 hover:bg-slate-50"
                    >
                      <Linkedin className="w-3.5 h-3.5" /> LinkedIn
                    </a>
                  )}
                </div>
              </div>
              <div className="flex-1 overflow-y-auto p-6">
                {contactDetail?.emails?.length > 0 ? (
                  <div>
                    <h3 className="text-sm font-bold text-slate-900 mb-3">Email History</h3>
                    <div className="space-y-2">
                      {contactDetail.emails.slice(0, 10).map((email: any) => (
                        <div key={email.id} className="p-3 bg-slate-50 rounded-xl text-sm">
                          <p className="font-medium text-slate-900 truncate">{email.subject}</p>
                          <p className="text-xs text-slate-400 mt-1">{email.date ? new Date(email.date).toLocaleDateString() : ''}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-slate-400 text-center py-8">No email history available.</p>
                )}
              </div>
          </DialogShell>
        )}
      </AnimatePresence>
    </div>
  );
}
