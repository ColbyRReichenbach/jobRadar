import { useEffect, useId, useMemo, useRef, useState } from 'react';
import {
  Search,
  Building2,
  Mail,
  Linkedin,
  User,
  X,
  Plus,
  Pencil,
  Phone,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import {
  checkContactDuplicates,
  createContact,
  deleteContact,
  deleteNetworkContact,
  fetchNetworkContact,
  fetchNetworkContacts,
  keepContactsSeparate,
  mergeContacts,
  sendEmail,
  updateContact,
} from '../lib/api';
import { DialogShell } from './DialogShell';

interface NetworkContact {
  id: string;
  name: string | null;
  email: string | null;
  title: string | null;
  company: string | null;
  company_id?: string | null;
  source: string;
  reached_out: boolean;
  response_received: boolean;
  linkedin_url: string | null;
  phone_number?: string | null;
  email_count?: number;
  last_interaction_at?: string;
}

interface ContactDetailEmail {
  id: string;
  thread_id?: string;
  email_type?: string;
  sender?: string;
  sender_email?: string;
  subject?: string;
  snippet?: string;
  received_at?: string;
  is_from_user?: boolean;
}

interface ContactDetailPayload {
  contact: {
    id?: string;
    application_id?: string | null;
    name?: string | null;
    title?: string | null;
    email?: string | null;
    company?: string | null;
    company_id?: string | null;
    phone_number?: string | null;
    linkedin_url?: string | null;
    source?: string | null;
  };
  emails: ContactDetailEmail[];
  applications: Array<{
    id: string;
    company: string;
    role_title: string;
  }>;
}

interface NetworkPageProps {
  onOpenEmail?: (email: any) => void;
  onRefreshData?: () => Promise<void> | void;
  focusRequest?: {
    email: string;
    token: number;
  } | null;
}

interface ContactFormState {
  name: string;
  title: string;
  email: string;
  company_name: string;
  phone_number: string;
  linkedin_url: string;
}

type MergeFieldKey = keyof ContactFormState;

interface DuplicateMatch {
  id: string;
  name?: string | null;
  email?: string | null;
  title?: string | null;
  company?: string | null;
  phone_number?: string | null;
  linkedin_url?: string | null;
}

interface MergeReviewState {
  target: DuplicateMatch;
  choices: Record<MergeFieldKey, 'current' | 'existing'>;
}

interface ComposeState {
  to: string;
  subject: string;
  body: string;
}

const EMPTY_CONTACT_FORM: ContactFormState = {
  name: '',
  title: '',
  email: '',
  company_name: '',
  phone_number: '',
  linkedin_url: '',
};

const EMPTY_COMPOSE: ComposeState = {
  to: '',
  subject: '',
  body: '',
};

export function NetworkPage({ onOpenEmail, onRefreshData, focusRequest }: NetworkPageProps) {
  const contactDialogTitleId = useId();
  const contactFormTitleId = useId();
  const composeDialogTitleId = useId();
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const contactFormCloseRef = useRef<HTMLButtonElement>(null);
  const composeCloseRef = useRef<HTMLButtonElement>(null);
  const mergeCloseRef = useRef<HTMLButtonElement>(null);
  const contactNameInputRef = useRef<HTMLInputElement>(null);
  const composeToInputRef = useRef<HTMLInputElement>(null);
  const [contacts, setContacts] = useState<NetworkContact[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [selectedContact, setSelectedContact] = useState<NetworkContact | null>(null);
  const [contactDetail, setContactDetail] = useState<ContactDetailPayload | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [showComposeModal, setShowComposeModal] = useState(false);
  const [composeState, setComposeState] = useState<ComposeState>(EMPTY_COMPOSE);
  const [sendingEmail, setSendingEmail] = useState(false);
  const [showContactForm, setShowContactForm] = useState(false);
  const [contactFormMode, setContactFormMode] = useState<'create' | 'edit'>('create');
  const [contactFormState, setContactFormState] = useState<ContactFormState>(EMPTY_CONTACT_FORM);
  const [savingContact, setSavingContact] = useState(false);
  const [contactDuplicateWarning, setContactDuplicateWarning] = useState<{ type: 'soft' | 'hard'; message: string; matches: DuplicateMatch[] } | null>(null);
  const [mergeReview, setMergeReview] = useState<MergeReviewState | null>(null);
  const [keepSeparatePending, setKeepSeparatePending] = useState(false);
  const [showAllEmails, setShowAllEmails] = useState(false);

  useEffect(() => {
    loadContacts();
  }, []);

  useEffect(() => {
    if (!focusRequest?.email) return;
    const emailValue = focusRequest.email.toLowerCase();
    const existing = contacts.find((contact) => (contact.email || '').toLowerCase() === emailValue);
    if (existing) {
      void openDetail(existing);
      return;
    }

    void (async () => {
      try {
        const detail = await fetchNetworkContact(focusRequest.email);
        setContactDetail(detail);
        setSelectedContact({
          id: detail.contact.id || focusRequest.email,
          name: detail.contact.name || focusRequest.email,
          email: detail.contact.email || focusRequest.email,
          title: detail.contact.title || null,
          company: detail.contact.company || null,
          company_id: detail.contact.company_id || null,
          source: detail.contact.source || 'email',
          reached_out: false,
          response_received: false,
          linkedin_url: detail.contact.linkedin_url || null,
          phone_number: detail.contact.phone_number || null,
        });
      } catch (err) {
        setErrorMessage(err instanceof Error ? err.message : 'Failed to load contact detail.');
      }
    })();
  }, [contacts, focusRequest]);

  const loadContacts = async (query?: string) => {
    setLoading(true);
    setErrorMessage(null);
    try {
      setContacts(await fetchNetworkContacts(query || ''));
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
        contact.phone_number,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [contacts, searchQuery]);

  const sourceColors: Record<string, string> = {
    hunter: 'bg-blue-50 text-blue-600',
    email: 'bg-purple-50 text-purple-600',
    warm_path: 'bg-emerald-50 text-emerald-600',
    outbound: 'bg-amber-50 text-amber-600',
    manual: 'bg-slate-100 text-slate-600',
  };

  const openDetail = async (contact: NetworkContact) => {
    setSelectedContact(contact);
    setContactDetail(null);
    setErrorMessage(null);
    setStatusMessage(null);
    setShowAllEmails(false);
    if (!contact.email) return;
    try {
      const detail = await fetchNetworkContact(contact.email);
      setContactDetail(detail);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to load contact detail.');
    }
  };

  const openCompose = (contact: Partial<NetworkContact>, email?: ContactDetailEmail) => {
    setComposeState({
      to: contact.email || '',
      subject: email ? `Re: ${email.subject || ''}` : '',
      body: '',
    });
    setShowComposeModal(true);
  };

  const openContactForm = (mode: 'create' | 'edit', contact?: Partial<NetworkContact>) => {
    setContactFormMode(mode);
    setKeepSeparatePending(false);
    setContactFormState({
      name: contact?.name || '',
      title: contact?.title || '',
      email: contact?.email || '',
      company_name: contact?.company || '',
      phone_number: contact?.phone_number || '',
      linkedin_url: contact?.linkedin_url || '',
    });
    setContactDuplicateWarning(null);
    setShowContactForm(true);
  };

  useEffect(() => {
    if (!showContactForm) return;
    const hasEnoughData = Boolean(contactFormState.email.trim()) || Boolean(contactFormState.name.trim());
    if (!hasEnoughData) {
      setContactDuplicateWarning(null);
      return;
    }

    const timeout = window.setTimeout(async () => {
      try {
        const result = await checkContactDuplicates({
          contact_id:
            contactFormMode === 'edit' && selectedContact && !selectedContact.id.startsWith('email-')
              ? selectedContact.id
              : undefined,
          name: contactFormState.name.trim() || undefined,
          email: contactFormState.email.trim() || undefined,
        });
        if (result.duplicate_type === 'none') {
          setContactDuplicateWarning(null);
          return;
        }
        setContactDuplicateWarning({
          type: result.duplicate_type,
          message: result.message || 'Potential duplicate contact found.',
          matches: result.matches || [],
        });
      } catch {
        setContactDuplicateWarning(null);
      }
    }, 250);

    return () => window.clearTimeout(timeout);
  }, [showContactForm, contactFormMode, contactFormState.name, contactFormState.email, selectedContact]);

  const openMergeReview = (match: DuplicateMatch) => {
    const choices = (['name', 'title', 'email', 'company_name', 'phone_number', 'linkedin_url'] as MergeFieldKey[]).reduce(
      (acc, field) => {
        const currentValue = (contactFormState[field] || '').trim();
        const existingValue = (
          field === 'company_name'
            ? match.company
            : match[field as keyof DuplicateMatch]
        ) || '';
        acc[field] = currentValue && (!existingValue || currentValue !== existingValue) ? 'current' : 'existing';
        return acc;
      },
      {} as Record<MergeFieldKey, 'current' | 'existing'>,
    );
    setMergeReview({ target: match, choices });
  };

  const resolveMergeValue = (field: MergeFieldKey, match: DuplicateMatch, choice: 'current' | 'existing') => {
    if (choice === 'current') {
      return contactFormState[field].trim() || undefined;
    }
    if (field === 'company_name') {
      return match.company || undefined;
    }
    return (match[field as keyof DuplicateMatch] as string | null | undefined) || undefined;
  };

  const handleSaveContact = async () => {
    if (contactDuplicateWarning?.type === 'hard') {
      setErrorMessage(contactDuplicateWarning.message);
      return;
    }
    setSavingContact(true);
    setErrorMessage(null);
    try {
      const payload = {
        name: contactFormState.name || undefined,
        title: contactFormState.title || undefined,
        email: contactFormState.email || undefined,
        company_name: contactFormState.company_name || undefined,
        phone_number: contactFormState.phone_number || undefined,
        linkedin_url: contactFormState.linkedin_url || undefined,
      };

      let savedContact: any;
      if (contactFormMode === 'edit' && selectedContact && !selectedContact.id.startsWith('email-')) {
        savedContact = await updateContact(selectedContact.id, payload);
        setStatusMessage(keepSeparatePending ? 'Contact updated and kept separate from the existing match.' : 'Contact updated.');
      } else {
        savedContact = await createContact(payload);
        setStatusMessage(keepSeparatePending ? 'Contact added and marked as a separate person.' : 'Contact added.');
      }

      setShowContactForm(false);
      setKeepSeparatePending(false);
      await loadContacts(searchQuery);
      if (savedContact?.email) {
        await openDetail({
          id: savedContact.id,
          name: savedContact.name,
          email: savedContact.email,
          title: savedContact.title,
          company: savedContact.company,
          phone_number: savedContact.phone_number,
          linkedin_url: savedContact.linkedin_url,
          source: savedContact.source || 'manual',
          reached_out: savedContact.reached_out || false,
          response_received: savedContact.response_received || false,
        });
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to save contact.');
    } finally {
      setSavingContact(false);
    }
  };

  const handleKeepSeparate = async (match: DuplicateMatch) => {
    if (!contactFormState.email.trim() || !match.email) {
      setContactDuplicateWarning(null);
      setStatusMessage('We will keep these contacts separate for now.');
      return;
    }

    try {
      await keepContactsSeparate({
        name: contactFormState.name.trim() || match.name || undefined,
        email: contactFormState.email.trim(),
        match_email: match.email,
      });
      setKeepSeparatePending(true);
      setContactDuplicateWarning(null);
      window.setTimeout(() => {
        void handleSaveContact();
      }, 0);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to save duplicate decision.');
    }
  };

  const handleConfirmMerge = async () => {
    if (!mergeReview) return;
    setSavingContact(true);
    setErrorMessage(null);
    try {
      const merged = await mergeContacts({
        target_contact_id: mergeReview.target.id,
        source_contact_id:
          contactFormMode === 'edit' && selectedContact && !selectedContact.id.startsWith('email-')
            ? selectedContact.id
            : undefined,
        name: resolveMergeValue('name', mergeReview.target, mergeReview.choices.name),
        title: resolveMergeValue('title', mergeReview.target, mergeReview.choices.title),
        email: resolveMergeValue('email', mergeReview.target, mergeReview.choices.email),
        company_name: resolveMergeValue('company_name', mergeReview.target, mergeReview.choices.company_name),
        phone_number: resolveMergeValue('phone_number', mergeReview.target, mergeReview.choices.phone_number),
        linkedin_url: resolveMergeValue('linkedin_url', mergeReview.target, mergeReview.choices.linkedin_url),
      });
      setMergeReview(null);
      setContactDuplicateWarning(null);
      setShowContactForm(false);
      setStatusMessage('Contacts merged.');
      await loadContacts(searchQuery);
      if (merged?.email) {
        await openDetail({
          id: merged.id,
          name: merged.name,
          email: merged.email,
          title: merged.title,
          company: merged.company,
          phone_number: merged.phone_number,
          linkedin_url: merged.linkedin_url,
          source: merged.source || 'manual',
          reached_out: merged.reached_out || false,
          response_received: merged.response_received || false,
        });
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to merge contacts.');
    } finally {
      setSavingContact(false);
    }
  };

  const handleDeleteContact = async () => {
    if (!selectedContact?.email) return;
    setErrorMessage(null);
    try {
      if (selectedContact.id.startsWith('email-')) {
        await deleteNetworkContact(selectedContact.email);
      } else {
        await deleteContact(selectedContact.id);
      }
      setStatusMessage('Contact removed from your network.');
      setSelectedContact(null);
      setContactDetail(null);
      await loadContacts(searchQuery);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to delete contact.');
    }
  };

  const handleSendEmail = async () => {
    if (!composeState.to.trim() || !composeState.subject.trim() || !composeState.body.trim()) {
      setErrorMessage('Recipient, subject, and message are required.');
      return;
    }

    setSendingEmail(true);
    setErrorMessage(null);
    try {
      const result = await sendEmail({
        to: composeState.to.trim(),
        subject: composeState.subject.trim(),
        body: composeState.body.trim(),
        application_id: contactDetail?.applications?.[0]?.id,
      });
      await onRefreshData?.();
      setShowComposeModal(false);
      setComposeState(EMPTY_COMPOSE);
      setStatusMessage('Email sent. It will appear in Conversations.');
      if (selectedContact?.email) {
        await openDetail(selectedContact);
      }
      if (result?.id) {
        onOpenEmail?.({
          id: result.id,
          thread_id: result.threadId,
          type: 'conversation',
        });
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to send email.');
    } finally {
      setSendingEmail(false);
    }
  };

  const visibleEmails = showAllEmails
    ? contactDetail?.emails || []
    : (contactDetail?.emails || []).slice(0, 2);
  const selectedCompany = contactDetail?.contact?.company || selectedContact?.company || null;

  return (
    <div className="flex-1 h-full overflow-y-auto p-4 md:p-8 bg-[#F5F5F0]">
      <div className="w-full">
        <div className="mb-8">
          <h1 className="text-3xl tracking-tight font-serif font-bold text-slate-900">Network</h1>
          <p className="mt-1 text-slate-500 font-serif italic">
            Your professional connections across all sources.
          </p>
        </div>

        <div className="p-4 mb-8 flex flex-col gap-4 bg-white rounded-3xl shadow-sm border border-slate-100 lg:flex-row lg:items-center">
          <div className="flex-1 flex items-center gap-3 px-4 py-2 bg-slate-50 rounded-xl border border-slate-100 focus-within:border-indigo-300 focus-within:ring-2 focus-within:ring-indigo-100">
            <Search className="w-5 h-5 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Search by name, company, email, or title..."
              className="bg-transparent border-none outline-none w-full text-sm text-slate-900 placeholder:text-slate-400"
            />
          </div>
          <div className="flex items-center justify-between gap-3">
            <div className="px-2 text-xs font-medium uppercase tracking-[0.18em] text-slate-400">
              {filteredContacts.length} results
            </div>
            <button
              onClick={() => openContactForm('create')}
              className="inline-flex items-center gap-2 px-4 py-2 bg-slate-800 text-white text-sm font-medium rounded-xl hover:bg-slate-900 transition-colors"
            >
              <Plus className="w-4 h-4" />
              Add Contact
            </button>
          </div>
        </div>

        {(errorMessage || statusMessage) && (
          <div
            className={`mb-6 rounded-2xl border px-4 py-3 text-sm ${
              errorMessage
                ? 'border-red-200 bg-red-50 text-red-800'
                : 'border-emerald-200 bg-emerald-50 text-emerald-800'
            }`}
          >
            {errorMessage || statusMessage}
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
              {searchQuery
                ? 'Try a different search term.'
                : 'Contacts will appear as you track jobs and sync emails.'}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {filteredContacts.map((contact, index) => (
              <motion.div
                key={contact.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.03 }}
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
                    <h3 className="font-serif font-bold text-slate-900 truncate">
                      {contact.name || contact.email}
                    </h3>
                    {contact.title && <p className="text-xs text-slate-500 truncate">{contact.title}</p>}
                    {contact.company && (
                      <p className="text-xs text-slate-400 flex items-center gap-1 mt-0.5">
                        <Building2 className="w-3 h-3" /> {contact.company}
                      </p>
                    )}
                  </div>
                  <span
                    className={`px-2 py-0.5 text-[10px] font-medium rounded-full ${
                      sourceColors[contact.source] || 'bg-slate-50 text-slate-500'
                    }`}
                  >
                    {contact.source}
                  </span>
                </div>
                {contact.email && (
                  <div className="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between gap-3">
                    <span className="text-xs text-slate-400 truncate">{contact.email}</span>
                    <button
                      onClick={(event) => {
                        event.stopPropagation();
                        openCompose(contact);
                      }}
                      className="text-[11px] font-medium text-indigo-600 hover:text-indigo-700 opacity-100 transition-opacity md:opacity-0 md:group-hover:opacity-100"
                    >
                      Email
                    </button>
                  </div>
                )}
              </motion.div>
            ))}
          </div>
        )}
      </div>

      <AnimatePresence>
        {selectedContact && (
          <DialogShell
            onClose={() => {
              setSelectedContact(null);
              setContactDetail(null);
            }}
            titleId={contactDialogTitleId}
            initialFocusRef={closeButtonRef}
            wrapperClassName="fixed inset-0 z-50 flex items-end justify-center p-0 md:items-center md:p-4"
            overlayClassName="absolute inset-0 bg-slate-900/20 backdrop-blur-sm"
            panelClassName="bg-white w-full max-w-2xl h-[92dvh] md:h-auto max-h-[92dvh] md:max-h-[82vh] flex flex-col rounded-t-[2rem] md:rounded-3xl shadow-2xl overflow-hidden"
          >
            <div className="p-4 md:p-6 border-b border-slate-100 bg-slate-50/50">
              <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                <div className="flex min-w-0 items-center gap-4">
                  <div className="w-14 h-14 flex items-center justify-center rounded-full bg-slate-200 text-slate-700 font-bold text-xl">
                    {(selectedContact.name || selectedContact.email || '?')[0].toUpperCase()}
                  </div>
                  <div className="min-w-0">
                    <h2 id={contactDialogTitleId} className="truncate text-xl font-serif font-bold text-slate-900">
                      {selectedContact.name || selectedContact.email || 'Unknown'}
                    </h2>
                    {selectedContact.title && <p className="truncate text-sm text-slate-500">{selectedContact.title}</p>}
                    {selectedContact.company && <p className="truncate text-sm text-slate-400">{selectedContact.company}</p>}
                  </div>
                </div>
                <div className="flex w-full flex-wrap items-center gap-2 md:w-auto md:justify-end">
                  <button
                    onClick={() =>
                      openContactForm(
                        selectedContact.id.startsWith('email-') ? 'create' : 'edit',
                        selectedContact,
                      )
                    }
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                    >
                      <Pencil className="w-3.5 h-3.5" />
                      Edit Contact
                    </button>
                  {selectedContact.email && (
                    <button
                      onClick={handleDeleteContact}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50"
                    >
                      <X className="w-3.5 h-3.5" />
                      Delete Contact
                    </button>
                  )}
                  <button
                    ref={closeButtonRef}
                    onClick={() => {
                      setSelectedContact(null);
                      setContactDetail(null);
                    }}
                    aria-label="Close contact details"
                    className="p-1 hover:bg-slate-200 rounded-lg shrink-0"
                  >
                    <X className="w-5 h-5 text-slate-500" />
                  </button>
                </div>
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                {selectedContact.email && (
                  <button
                    onClick={() => openCompose(selectedContact)}
                    className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                  >
                    <Mail className="w-3.5 h-3.5" /> Email
                  </button>
                )}
                {selectedContact.linkedin_url && (
                  <a
                    href={selectedContact.linkedin_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                  >
                    <Linkedin className="w-3.5 h-3.5" /> LinkedIn
                  </a>
                )}
                {selectedContact.phone_number && (
                  <a
                    href={`tel:${selectedContact.phone_number}`}
                    className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                  >
                    <Phone className="w-3.5 h-3.5" /> {selectedContact.phone_number}
                  </a>
                )}
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6">
              {(selectedContact.email || selectedContact.phone_number || selectedContact.linkedin_url || selectedCompany) && (
                <div>
                  <h3 className="text-sm font-bold text-slate-900 mb-3">Contact Info</h3>
                  <div className="grid gap-3 md:grid-cols-2">
                    {selectedCompany && (
                      <div className="p-4 bg-slate-50 rounded-2xl">
                        <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400 mb-1">Company</div>
                        <div className="break-words text-sm font-medium text-slate-900">{selectedCompany}</div>
                      </div>
                    )}
                    {selectedContact.email && (
                      <div className="p-4 bg-slate-50 rounded-2xl">
                        <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400 mb-1">Email</div>
                        <div className="text-sm font-medium text-slate-900 break-all">{selectedContact.email}</div>
                      </div>
                    )}
                    {selectedContact.phone_number && (
                      <div className="p-4 bg-slate-50 rounded-2xl">
                        <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400 mb-1">Phone</div>
                        <div className="break-words text-sm font-medium text-slate-900">{selectedContact.phone_number}</div>
                      </div>
                    )}
                    {selectedContact.linkedin_url && (
                      <div className="p-4 bg-slate-50 rounded-2xl sm:col-span-2">
                        <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400 mb-1">LinkedIn</div>
                        <a
                          href={selectedContact.linkedin_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm font-medium text-indigo-600 hover:underline break-all"
                        >
                          {selectedContact.linkedin_url}
                        </a>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {contactDetail?.applications?.length ? (
                <div>
                  <h3 className="text-sm font-bold text-slate-900 mb-3">Linked Application</h3>
                  <div className="space-y-2">
                    {contactDetail.applications.map((application) => (
                      <div key={application.id} className="p-4 bg-slate-50 rounded-2xl">
                        <div className="text-sm font-medium text-slate-900">{application.company}</div>
                        <div className="text-xs text-slate-500 mt-1">{application.role_title}</div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              <div>
                <div className="flex items-center justify-between gap-3 mb-3">
                  <h3 className="text-sm font-bold text-slate-900">Email History</h3>
                  {contactDetail && contactDetail.emails.length > 2 && (
                    <button
                      onClick={() => setShowAllEmails((prev) => !prev)}
                      className="inline-flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-slate-700"
                    >
                      {showAllEmails ? (
                        <>
                          <ChevronUp className="w-3.5 h-3.5" />
                          Show Less
                        </>
                      ) : (
                        <>
                          <ChevronDown className="w-3.5 h-3.5" />
                          Show All
                        </>
                      )}
                    </button>
                  )}
                </div>

                {visibleEmails.length > 0 ? (
                  <div className="space-y-2">
                    {visibleEmails.map((email) => (
                      <button
                        key={email.id}
                        onClick={() => {
                          onOpenEmail?.({
                            id: email.id,
                            thread_id: email.thread_id,
                            email_type: email.email_type,
                          });
                          setSelectedContact(null);
                          setContactDetail(null);
                        }}
                        className="w-full text-left p-4 bg-slate-50 hover:bg-slate-100 rounded-2xl transition-colors"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="text-sm font-medium text-slate-900 truncate">
                              {email.subject || 'Untitled email'}
                            </div>
                            <div className="text-xs text-slate-500 mt-1 line-clamp-2">
                              {email.is_from_user ? 'You: ' : ''}
                              {email.snippet || 'Open this message to view the full thread.'}
                            </div>
                          </div>
                          {email.received_at && (
                            <div className="text-[11px] text-slate-400 shrink-0">
                              {new Date(email.received_at).toLocaleDateString()}
                            </div>
                          )}
                        </div>
                      </button>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-slate-400 text-center py-8">No email history available.</p>
                )}
              </div>
            </div>
          </DialogShell>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {showComposeModal && (
          <DialogShell
            onClose={() => setShowComposeModal(false)}
            titleId={composeDialogTitleId}
            initialFocusRef={composeToInputRef}
            wrapperClassName="fixed inset-0 z-50 flex items-end justify-center p-0 md:items-center md:p-4"
            overlayClassName="absolute inset-0 bg-slate-900/20 backdrop-blur-sm"
            panelClassName="bg-white w-full max-w-xl rounded-t-[2rem] md:rounded-3xl shadow-2xl overflow-hidden"
          >
            <div className="p-4 md:p-6 border-b border-slate-100 flex items-center justify-between">
              <h2 id={composeDialogTitleId} className="text-xl font-serif font-bold text-slate-900">
                Compose Email
              </h2>
              <button
                ref={composeCloseRef}
                onClick={() => setShowComposeModal(false)}
                className="p-1 hover:bg-slate-200 rounded-lg"
              >
                <X className="w-5 h-5 text-slate-500" />
              </button>
            </div>
            <div className="p-4 md:p-6 space-y-4">
              <div>
                <label className="block text-xs font-medium uppercase tracking-[0.18em] text-slate-400 mb-2">
                  To
                </label>
                <input
                  ref={composeToInputRef}
                  value={composeState.to}
                  onChange={(event) => setComposeState((prev) => ({ ...prev, to: event.target.value }))}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-medium uppercase tracking-[0.18em] text-slate-400 mb-2">
                  Subject
                </label>
                <input
                  value={composeState.subject}
                  onChange={(event) =>
                    setComposeState((prev) => ({ ...prev, subject: event.target.value }))
                  }
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-medium uppercase tracking-[0.18em] text-slate-400 mb-2">
                  Message
                </label>
                <textarea
                  value={composeState.body}
                  onChange={(event) => setComposeState((prev) => ({ ...prev, body: event.target.value }))}
                  rows={8}
                  className="w-full px-3 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm resize-y"
                />
              </div>
            </div>
            <div className="px-4 pb-4 md:px-6 md:pb-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <button
                onClick={() => setShowComposeModal(false)}
                className="px-4 py-2 bg-white border border-slate-200 text-slate-700 text-sm font-medium rounded-xl"
              >
                Cancel
              </button>
              <button
                onClick={handleSendEmail}
                disabled={sendingEmail}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-900 text-white text-sm font-medium rounded-xl disabled:opacity-50"
              >
                {sendingEmail ? 'Sending...' : 'Send Email'}
              </button>
            </div>
          </DialogShell>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {showContactForm && (
          <DialogShell
            onClose={() => setShowContactForm(false)}
            titleId={contactFormTitleId}
            initialFocusRef={contactNameInputRef}
            wrapperClassName="fixed inset-0 z-50 flex items-end justify-center p-0 md:items-center md:p-4"
            overlayClassName="absolute inset-0 bg-slate-900/20 backdrop-blur-sm"
            panelClassName="bg-white w-full max-w-xl rounded-t-[2rem] md:rounded-3xl shadow-2xl overflow-hidden"
          >
            <div className="p-4 md:p-6 border-b border-slate-100 flex items-center justify-between">
              <h2 id={contactFormTitleId} className="text-xl font-serif font-bold text-slate-900">
                {contactFormMode === 'edit' ? 'Edit Contact' : 'Add Contact'}
              </h2>
              <button
                ref={contactFormCloseRef}
                onClick={() => setShowContactForm(false)}
                className="p-1 hover:bg-slate-200 rounded-lg"
              >
                <X className="w-5 h-5 text-slate-500" />
              </button>
            </div>
            <div className="p-4 md:p-6 grid gap-4 sm:grid-cols-2">
              {contactDuplicateWarning && (
                <div className={`sm:col-span-2 rounded-xl border px-3 py-3 text-sm ${
                  contactDuplicateWarning.type === 'hard'
                    ? 'border-red-200 bg-red-50 text-red-700'
                    : 'border-amber-200 bg-amber-50 text-amber-800'
                }`}>
                  <div className="font-medium">{contactDuplicateWarning.message}</div>
                  {contactDuplicateWarning.matches.length > 0 && (
                    <div className="mt-3 space-y-2">
                      {contactDuplicateWarning.matches.slice(0, 2).map((match) => (
                        <div key={match.id} className="rounded-lg border border-white/70 bg-white/70 px-3 py-2 text-xs text-slate-700">
                          <div className="font-semibold text-slate-900">{match.name || match.email}</div>
                          <div className="mt-0.5 text-slate-500">
                            {[match.title, match.company, match.email].filter(Boolean).join(' · ')}
                          </div>
                          {contactDuplicateWarning.type === 'soft' && (
                            <div className="mt-2 flex flex-wrap gap-2">
                              <button
                                type="button"
                                onClick={() => openMergeReview(match)}
                                className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
                              >
                                Merge with this
                              </button>
                              <button
                                type="button"
                                onClick={() => void handleKeepSeparate(match)}
                                className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
                              >
                                Keep separate
                              </button>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
              <div className="sm:col-span-2">
                <label htmlFor="contact-form-name" className="block text-xs font-medium uppercase tracking-[0.18em] text-slate-400 mb-2">
                  Name
                </label>
                <input
                  id="contact-form-name"
                  ref={contactNameInputRef}
                  value={contactFormState.name}
                  onChange={(event) => setContactFormState((prev) => ({ ...prev, name: event.target.value }))}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm"
                />
              </div>
              <div className="sm:col-span-2">
                <label htmlFor="contact-form-email" className="block text-xs font-medium uppercase tracking-[0.18em] text-slate-400 mb-2">
                  Email
                </label>
                <input
                  id="contact-form-email"
                  type="email"
                  value={contactFormState.email}
                  onChange={(event) => setContactFormState((prev) => ({ ...prev, email: event.target.value }))}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm"
                />
              </div>
              <div>
                <label htmlFor="contact-form-title" className="block text-xs font-medium uppercase tracking-[0.18em] text-slate-400 mb-2">
                  Title
                </label>
                <input
                  id="contact-form-title"
                  value={contactFormState.title}
                  onChange={(event) => setContactFormState((prev) => ({ ...prev, title: event.target.value }))}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm"
                />
              </div>
              <div>
                <label htmlFor="contact-form-company" className="block text-xs font-medium uppercase tracking-[0.18em] text-slate-400 mb-2">
                  Company
                </label>
                <input
                  id="contact-form-company"
                  value={contactFormState.company_name}
                  onChange={(event) => setContactFormState((prev) => ({ ...prev, company_name: event.target.value }))}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm"
                />
              </div>
              <div>
                <label htmlFor="contact-form-phone" className="block text-xs font-medium uppercase tracking-[0.18em] text-slate-400 mb-2">
                  Phone
                </label>
                <input
                  id="contact-form-phone"
                  value={contactFormState.phone_number}
                  onChange={(event) =>
                    setContactFormState((prev) => ({ ...prev, phone_number: event.target.value }))
                  }
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm"
                />
              </div>
              <div className="sm:col-span-2">
                <label htmlFor="contact-form-linkedin" className="block text-xs font-medium uppercase tracking-[0.18em] text-slate-400 mb-2">
                  LinkedIn
                </label>
                <input
                  id="contact-form-linkedin"
                  value={contactFormState.linkedin_url}
                  onChange={(event) =>
                    setContactFormState((prev) => ({ ...prev, linkedin_url: event.target.value }))
                  }
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm"
                />
              </div>
            </div>
            <div className="px-4 pb-4 md:px-6 md:pb-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <button
                onClick={() => setShowContactForm(false)}
                className="px-4 py-2 bg-white border border-slate-200 text-slate-700 text-sm font-medium rounded-xl"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveContact}
                disabled={savingContact}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-900 text-white text-sm font-medium rounded-xl disabled:opacity-50"
              >
                {savingContact ? 'Saving...' : contactFormMode === 'edit' ? 'Save Changes' : 'Add Contact'}
              </button>
            </div>
          </DialogShell>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {mergeReview && (
          <DialogShell
            onClose={() => setMergeReview(null)}
            titleId={`${contactFormTitleId}-merge`}
            initialFocusRef={mergeCloseRef}
            wrapperClassName="fixed inset-0 z-[60] flex items-end justify-center p-0 md:items-center md:p-4"
            overlayClassName="absolute inset-0 bg-slate-900/25 backdrop-blur-sm"
            panelClassName="bg-white w-full max-w-2xl rounded-t-[2rem] md:rounded-3xl shadow-2xl overflow-hidden"
          >
            <div className="p-4 md:p-6 border-b border-slate-100 flex items-center justify-between">
              <div>
                <h2 id={`${contactFormTitleId}-merge`} className="text-xl font-serif font-bold text-slate-900">
                  Merge Contacts
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  Choose which details to keep on the merged contact.
                </p>
              </div>
              <button
                ref={mergeCloseRef}
                onClick={() => setMergeReview(null)}
                className="p-1 hover:bg-slate-200 rounded-lg"
              >
                <X className="w-5 h-5 text-slate-500" />
              </button>
            </div>
            <div className="max-h-[70vh] overflow-y-auto p-4 md:p-6 space-y-4">
              {([
                ['name', 'Name'],
                ['title', 'Title'],
                ['email', 'Email'],
                ['company_name', 'Company'],
                ['phone_number', 'Phone'],
                ['linkedin_url', 'LinkedIn'],
              ] as Array<[MergeFieldKey, string]>).map(([field, label]) => {
                const currentValue = contactFormState[field].trim() || 'Empty';
                const existingValue = (
                  field === 'company_name'
                    ? mergeReview.target.company
                    : mergeReview.target[field as keyof DuplicateMatch]
                ) || 'Empty';
                return (
                  <div key={field} className="rounded-2xl border border-slate-200 p-4">
                    <div className="text-xs font-medium uppercase tracking-[0.18em] text-slate-400">{label}</div>
                    <div className="mt-3 grid gap-3 md:grid-cols-2">
                      <label className="rounded-xl border border-slate-200 px-3 py-3 text-sm text-slate-700">
                        <div className="flex items-center gap-2">
                          <input
                            type="radio"
                            name={`merge-${field}`}
                            checked={mergeReview.choices[field] === 'current'}
                            onChange={() => setMergeReview((current) => current ? {
                              ...current,
                              choices: { ...current.choices, [field]: 'current' },
                            } : current)}
                          />
                          <span className="font-medium text-slate-900">Current form</span>
                        </div>
                        <div className="mt-2 break-words text-slate-600">{currentValue}</div>
                      </label>
                      <label className="rounded-xl border border-slate-200 px-3 py-3 text-sm text-slate-700">
                        <div className="flex items-center gap-2">
                          <input
                            type="radio"
                            name={`merge-${field}`}
                            checked={mergeReview.choices[field] === 'existing'}
                            onChange={() => setMergeReview((current) => current ? {
                              ...current,
                              choices: { ...current.choices, [field]: 'existing' },
                            } : current)}
                          />
                          <span className="font-medium text-slate-900">Existing contact</span>
                        </div>
                        <div className="mt-2 break-words text-slate-600">{existingValue}</div>
                      </label>
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="px-4 pb-4 md:px-6 md:pb-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <button
                onClick={() => setMergeReview(null)}
                className="px-4 py-2 bg-white border border-slate-200 text-slate-700 text-sm font-medium rounded-xl"
              >
                Cancel
              </button>
              <button
                onClick={() => void handleConfirmMerge()}
                disabled={savingContact}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-900 text-white text-sm font-medium rounded-xl disabled:opacity-50"
              >
                {savingContact ? 'Merging...' : 'Confirm Merge'}
              </button>
            </div>
          </DialogShell>
        )}
      </AnimatePresence>
    </div>
  );
}
