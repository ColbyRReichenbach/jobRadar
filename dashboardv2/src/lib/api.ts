import { Job, Email, Contact, ResearchProfile, OpportunitySignal, OpportunityBrief, RecommendedAction } from '../types';

function normalizeApiBase(rawBase: string): string {
  return rawBase.replace(/\/+$/, '').replace(/\/api$/, '');
}

const API_BASE = normalizeApiBase(import.meta.env.VITE_API_URL || 'http://localhost:8000');
const PAGE_SIZE = 100;

let _accessToken: string | null = null;
let _unauthorizedHandler: (() => void) | null = null;

function getToken(): string {
  return _accessToken || '';
}

export function authHeaders(): Record<string, string> {
  const token = getToken();
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) {
    h['Authorization'] = `Bearer ${token}`;
  }
  return h;
}

function resolveUrl(pathOrUrl: string): string {
  if (pathOrUrl.startsWith('http://') || pathOrUrl.startsWith('https://')) {
    return pathOrUrl;
  }
  return `${API_BASE}${pathOrUrl}`;
}

async function readErrorDetail(res: Response, fallback: string): Promise<string> {
  const payload = await res.json().catch(() => null);
  if (typeof payload?.detail === 'string') return payload.detail;
  if (typeof payload?.message === 'string') return payload.message;
  if (typeof payload?.detail?.message === 'string') return payload.detail.message;
  return fallback;
}

async function fetchPaginatedArray<T>(buildPath: (limit: number, offset: number) => string): Promise<T[]> {
  const items: T[] = [];
  let offset = 0;

  while (true) {
    const res = await apiFetch(buildPath(PAGE_SIZE, offset), { headers: authHeaders() });
    if (!res.ok) {
      throw new Error(await readErrorDetail(res, 'Failed to load data.'));
    }

    const batch = await res.json();
    if (!Array.isArray(batch)) {
      throw new Error('Expected a list response from the API.');
    }

    items.push(...batch);
    if (batch.length < PAGE_SIZE) {
      break;
    }
    offset += PAGE_SIZE;
  }

  return items;
}

function notifyUnauthorized() {
  _accessToken = null;
  _unauthorizedHandler?.();
  fetch(`${API_BASE}/api/auth/logout`, {
    method: 'POST',
    credentials: 'include',
  }).catch(() => {});
}

/**
 * Wrapper around fetch that auto-refreshes on 401.
 */
export async function apiFetch(pathOrUrl: string, options: RequestInit = {}): Promise<Response> {
  const url = resolveUrl(pathOrUrl);
  let res = await fetch(url, { ...options, credentials: 'include' });

  if (res.status === 401) {
    // Try to refresh
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      // Retry with new token
      const retryHeaders = { ...options.headers as Record<string, string> };
      retryHeaders['Authorization'] = `Bearer ${_accessToken}`;
      res = await fetch(url, { ...options, headers: retryHeaders, credentials: 'include' });
    }

    if (res.status === 401) {
      notifyUnauthorized();
    }
  }

  return res;
}

async function refreshAccessToken(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
    });
    if (!res.ok) return false;
    const data = await res.json();
    _accessToken = data.access_token;
    return true;
  } catch {
    return false;
  }
}

// --- Auth API ---

export interface UserProfile {
  id: string;
  email: string;
  name: string;
  picture: string;
  gmail_connected: boolean;
  calendar_connected: boolean;
}

export interface NotificationPrefs {
  sms_enabled: boolean;
  sms_phone: string | null;
  weekly_digest_enabled: boolean;
}

export interface ApiKeyStatus {
  has_api_key: boolean;
  last4: string | null;
  created_at: string | null;
  last_used_at: string | null;
}

export interface ApiKeyCreateResponse {
  api_key: string;
  last4: string;
  created_at: string;
}

export interface GoogleAuthOptions {
  connectGmail?: boolean;
  connectCalendar?: boolean;
}

export function buildGoogleAuthStartUrl(options: GoogleAuthOptions = {}): string {
  const params = new URLSearchParams();
  if (options.connectGmail) params.set('connect_gmail', 'true');
  if (options.connectCalendar) params.set('connect_calendar', 'true');
  params.set('redirect', 'true');
  params.set('frontend_origin', window.location.origin);
  const query = params.toString();
  return `${API_BASE}/api/auth/google${query ? `?${query}` : ''}`;
}

export async function getGoogleAuthUrl(options: GoogleAuthOptions = {}): Promise<string> {
  const params = new URLSearchParams();
  if (options.connectGmail) params.set('connect_gmail', 'true');
  if (options.connectCalendar) params.set('connect_calendar', 'true');
  const query = params.toString();
  const res = await fetch(`${API_BASE}/api/auth/google${query ? `?${query}` : ''}`, { credentials: 'include' });
  if (!res.ok) throw new Error('Failed to get auth URL');
  const data = await res.json();
  return data.auth_url;
}

export async function fetchMe(): Promise<UserProfile | null> {
  const token = getToken();
  if (!token) {
    // Try refreshing first (page reload scenario)
    const refreshed = await refreshAccessToken();
    if (!refreshed) return null;
  }
  try {
    const res = await apiFetch(`${API_BASE}/api/auth/me`, { headers: authHeaders() });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function syncGmail(): Promise<{ new_emails: number; total_found: number }> {
  const res = await apiFetch(`${API_BASE}/api/gmail/sync`, {
    method: 'POST',
    headers: authHeaders(),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Sync failed' }));
    throw new Error(err.detail || 'Gmail sync failed');
  }
  return await res.json();
}

export async function syncCalendar(): Promise<{ created: number; updated: number; skipped: number; total_events: number }> {
  const res = await apiFetch(`${API_BASE}/api/calendar/sync`, {
    method: 'POST',
    headers: authHeaders(),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Calendar sync failed' }));
    throw new Error(err.detail || 'Calendar sync failed');
  }
  return await res.json();
}

export async function fetchNotificationPreferences(): Promise<NotificationPrefs> {
  const res = await apiFetch(`${API_BASE}/api/notifications/preferences`, { headers: authHeaders() });
  if (!res.ok) throw new Error(await readErrorDetail(res, 'Failed to load notification preferences'));
  return await res.json();
}

export async function updateNotificationPreferences(payload: NotificationPrefs): Promise<NotificationPrefs> {
  const res = await apiFetch(`${API_BASE}/api/notifications/preferences`, {
    method: 'PUT',
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await readErrorDetail(res, 'Failed to save notification preferences'));
  return await res.json();
}

export async function fetchApiKeyStatus(): Promise<ApiKeyStatus> {
  const res = await apiFetch(`${API_BASE}/api/auth/api-key`, { headers: authHeaders() });
  if (!res.ok) throw new Error(await readErrorDetail(res, 'Failed to load API key status'));
  return await res.json();
}

export async function generateApiKey(): Promise<ApiKeyCreateResponse> {
  const res = await apiFetch(`${API_BASE}/api/auth/api-key`, {
    method: 'POST',
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await readErrorDetail(res, 'Failed to generate API key'));
  return await res.json();
}

export function setAuthToken(token: string) {
  _accessToken = token;
}

export function setUnauthorizedHandler(handler: (() => void) | null) {
  _unauthorizedHandler = handler;
}

export function clearAuthToken() {
  const token = _accessToken;
  _accessToken = null;
  _unauthorizedHandler?.();
  // Also call logout to clear refresh cookie
  fetch(`${API_BASE}/api/auth/logout`, {
    method: 'POST',
    credentials: 'include',
    headers: token ? { 'Authorization': `Bearer ${token}` } : {},
  }).catch(() => {});
}

export function hasAuthToken(): boolean {
  return !!_accessToken;
}

// --- Mappers: backend → frontend types ---

function mapJob(raw: any): Job {
  return {
    id: raw.id,
    company: raw.company,
    role: raw.role_title,
    location: raw.location || '',
    salary: raw.salary || undefined,
    status: raw.status,
    dateAdded: raw.applied_at || new Date().toISOString(),
    logoUrl: raw.logo_url || `https://logo.clearbit.com/${raw.company?.toLowerCase().replace(/\s+/g, '')}.com`,
    source: raw.source || undefined,
    contacts: raw.contacts?.map(mapContact) || [],
    description: raw.description_text || undefined,
    notes: raw.notes || undefined,
    url: raw.job_url || undefined,
    techStack: raw.tech_stack || [],
    umbrellaId: raw.umbrella_id || undefined,
    umbrellaName: raw.umbrella_name || undefined,
    companyId: raw.company_id || undefined,
    matchScore: raw.match_score ?? undefined,
    listingAlive: raw.listing_alive ?? true,
    listingDiedAt: raw.listing_died_at || undefined,
  };
}

function mapContact(raw: any): Contact {
  return {
    id: raw.id,
    name: raw.name || '',
    role: raw.title || '',
    email: raw.email || '',
    phoneNumber: raw.phone_number || undefined,
    linkedin: raw.linkedin_url || undefined,
  };
}

function mapEmail(raw: any): Email {
  // Map backend classification to frontend EmailClassification
  const classificationMap: Record<string, string> = {
    interview_request: 'interview',
    rejection: 'rejection',
    offer: 'action_item',
    action_item: 'action_item',
    job_update: 'update',
    conversation: 'update',
    not_relevant: 'update',
    // Legacy values pass through
    interview: 'interview',
    update: 'update',
  };

  return {
    id: raw.id,
    gmailMessageId: raw.gmail_message_id || undefined,
    threadId: raw.thread_id || undefined,
    jobId: raw.application_id || '',
    sender: raw.sender || '',
    senderEmail: raw.sender_email || undefined,
    subject: raw.subject || raw.summary || '',
    snippet: raw.snippet || raw.key_sentence || '',
    body: raw.body || undefined,
    date: raw.received_at || new Date().toISOString(),
    classification: (classificationMap[raw.classification] || raw.classification || 'update') as Email['classification'],
    read: raw.read || false,
    type: raw.email_type || 'decision',
    requiresFollowUp: raw.action_needed || false,
    lastResponseAt: raw.received_at || undefined,
    isFromUser: raw.is_from_user || false,
    companyName: raw.company_name || undefined,
    companyLogoUrl: raw.company_logo_url || undefined,
    senderDomain: raw.sender_domain || undefined,
    confidence: raw.confidence || undefined,
    summary: raw.summary || undefined,
    category: raw.classification || undefined,
    colorCode: raw.color_code || undefined,
    inPipeline: raw.application_id ? true : false,
    resolved: raw.resolved || false,
    hidden: raw.hidden || false,
    collapsed: raw.collapsed || false,
    actionUrl: raw.action_url || undefined,
  };
}

// --- Jobs API ---

export async function fetchJobs(): Promise<Job[]> {
  const data = await fetchPaginatedArray<any>((limit, offset) => `${API_BASE}/api/jobs?limit=${limit}&offset=${offset}`);
  return data.map(mapJob);
}

export async function createJob(job: Partial<Job>): Promise<Job> {
  const body: any = {
    company: job.company,
    role_title: job.role,
    job_url: job.url || undefined,
    source: job.source || undefined,
    description_text: job.description || undefined,
    salary: job.salary || undefined,
    logo_url: job.logoUrl || undefined,
    location: job.location || undefined,
    status: job.status || 'saved',
    notes: job.notes || undefined,
  };
  const res = await apiFetch(`${API_BASE}/api/jobs`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await readErrorDetail(res, `Failed to create job: ${res.status}`));
  return mapJob(await res.json());
}

export async function updateJob(id: string, updates: Partial<Job>): Promise<Job> {
  const body: any = {};
  if (updates.status !== undefined) body.status = updates.status;
  if (updates.notes !== undefined) body.notes = updates.notes;
  if (updates.salary !== undefined) body.salary = updates.salary;
  if (updates.location !== undefined) body.location = updates.location;
  if (updates.description !== undefined) body.description_text = updates.description;
  if (updates.company !== undefined) body.company = updates.company;
  if (updates.role !== undefined) body.role_title = updates.role;
  if (updates.source !== undefined) body.source = updates.source;
  if (updates.url !== undefined) body.job_url = updates.url;
  if (updates.logoUrl !== undefined) body.logo_url = updates.logoUrl;

  const res = await apiFetch(`${API_BASE}/api/jobs/${id}`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await readErrorDetail(res, `Failed to update job: ${res.status}`));
  return mapJob(await res.json());
}

// --- Emails API ---

export async function fetchEmails(): Promise<Email[]> {
  const data = await fetchPaginatedArray<any>((limit, offset) => `${API_BASE}/api/emails?limit=${limit}&offset=${offset}`);
  return data.map(mapEmail);
}

export async function markEmailRead(id: string): Promise<void> {
  await apiFetch(`${API_BASE}/api/emails/${id}`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify({ read: true }),
  });
}

export async function submitEmailFeedback(emailId: string, isJobRelated: boolean): Promise<void> {
  await apiFetch(`${API_BASE}/api/emails/feedback`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ email_id: emailId, is_job_related: isJobRelated }),
  });
}

export async function checkEmailPipeline(emailId: string): Promise<{
  in_pipeline: boolean;
  application_id?: string;
  company_name?: string;
  suggestion?: string;
}> {
  const res = await apiFetch(`${API_BASE}/api/emails/${emailId}/pipeline-check`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`Failed to check pipeline: ${res.status}`);
  return await res.json();
}

export async function markEmailResolved(id: string): Promise<void> {
  await apiFetch(`${API_BASE}/api/emails/${id}`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify({ resolved: true }),
  });
}

export async function updateEmail(id: string, payload: {
  read?: boolean;
  collapsed?: boolean;
  application_id?: string;
  classification?: string;
  resolved?: boolean;
  hidden?: boolean;
}): Promise<Email> {
  const res = await apiFetch(`${API_BASE}/api/emails/${id}`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await readErrorDetail(res, 'Failed to update email'));
  return mapEmail(await res.json());
}

// --- Search API ---

export async function searchJobs(query: string, location: string = ''): Promise<any[]> {
  const params = new URLSearchParams({ q: query, location });
  const res = await apiFetch(`${API_BASE}/api/search?${params}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(await readErrorDetail(res, `Failed to search: ${res.status}`));
  const data = await res.json();
  return data.results || [];
}

// --- Resume / Match API ---

export async function parseResume(text: string): Promise<any> {
  const res = await apiFetch(`${API_BASE}/api/resume/parse`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error(`Failed to parse resume: ${res.status}`);
  return await res.json();
}

export async function getProfile(): Promise<any | null> {
  const res = await apiFetch(`${API_BASE}/api/profile`, { headers: authHeaders() });
  if (!res.ok) return null;
  return await res.json();
}

export async function getJobMatch(jobId: string): Promise<any> {
  const res = await apiFetch(`${API_BASE}/api/jobs/${jobId}/match`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`Failed to get match: ${res.status}`);
  return await res.json();
}

// --- ATS Intelligence API ---

export async function getAtsIntelligence(platform: string): Promise<any> {
  const res = await apiFetch(`${API_BASE}/api/intelligence/ats/${platform}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`Failed to get ATS intelligence: ${res.status}`);
  return await res.json();
}

// --- Warm Paths API ---

export async function getWarmPaths(jobId: string): Promise<any> {
  const res = await apiFetch(`${API_BASE}/api/jobs/${jobId}/warm-paths`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`Failed to get warm paths: ${res.status}`);
  return await res.json();
}

// --- Alerts API ---

export async function fetchAlerts(unread = false): Promise<any[]> {
  const params = unread ? '?unread=true' : '';
  const res = await apiFetch(`${API_BASE}/api/alerts${params}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`Failed to fetch alerts: ${res.status}`);
  return await res.json();
}

export async function markAlertRead(id: string): Promise<void> {
  await apiFetch(`${API_BASE}/api/alerts/${id}`, {
    method: 'PATCH',
    headers: authHeaders(),
  });
}

export async function getUnreadAlertCount(): Promise<number> {
  const res = await apiFetch(`${API_BASE}/api/alerts/count`, { headers: authHeaders() });
  if (!res.ok) return 0;
  const data = await res.json();
  return data.unread || 0;
}

// --- Send Email API ---

export async function sendEmail(payload: {
  to: string;
  cc?: string[];
  subject: string;
  body: string;
  application_id?: string;
  reply_to_email_id?: string;
  reply_to_message_id?: string;
  thread_id?: string;
}): Promise<Email> {
  const res = await apiFetch(`${API_BASE}/api/emails/send`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await readErrorDetail(res, `Failed to send email: ${res.status}`));
  return mapEmail(await res.json());
}

export async function fetchReplyContext(
  emailId: string,
  replyAll = false,
): Promise<{
  to: string;
  cc: string[];
  subject: string;
  thread_id?: string;
  reply_to_email_id: string;
}> {
  const params = new URLSearchParams();
  if (replyAll) params.set('reply_all', 'true');
  const res = await apiFetch(`${API_BASE}/api/emails/${emailId}/reply-context?${params.toString()}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await readErrorDetail(res, 'Failed to prepare reply.'));
  return await res.json();
}

// --- Draft API ---

export async function generateDraft(payload: {
  application_id?: string;
  contact_email?: string;
  draft_type: string;
  additional_context?: string;
}): Promise<{ subject: string; body: string; tone: string; draft_type: string }> {
  const res = await apiFetch(`${API_BASE}/api/drafts/generate`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Failed to generate draft: ${res.status}`);
  return await res.json();
}

// --- Company Context API ---

export async function getCompanyContext(domain: string): Promise<any> {
  const res = await apiFetch(`${API_BASE}/api/companies/${encodeURIComponent(domain)}/context`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`Failed to get company context: ${res.status}`);
  return await res.json();
}

// --- Interview API ---

export async function fetchInterviews(applicationId?: string): Promise<any[]> {
  return await fetchPaginatedArray<any>((limit, offset) => {
    const params = new URLSearchParams();
    params.set('limit', String(limit));
    params.set('offset', String(offset));
    if (applicationId) params.set('application_id', applicationId);
    return `${API_BASE}/api/interviews?${params.toString()}`;
  });
}

export async function createInterview(data: any): Promise<any> {
  const res = await apiFetch(`${API_BASE}/api/interviews`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(await readErrorDetail(res, `Failed to create interview: ${res.status}`));
  return await res.json();
}

export async function fetchNetworkContacts(query = ''): Promise<any[]> {
  return await fetchPaginatedArray<any>((limit, offset) => {
    const params = new URLSearchParams();
    params.set('limit', String(limit));
    params.set('offset', String(offset));
    if (query) params.set('q', query);
    return `${API_BASE}/api/network?${params.toString()}`;
  });
}

export async function fetchNetworkContact(email: string): Promise<any> {
  const res = await apiFetch(`${API_BASE}/api/network/${encodeURIComponent(email)}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await readErrorDetail(res, 'Failed to load contact detail'));
  return await res.json();
}

export async function deleteNetworkContact(email: string): Promise<void> {
  const res = await apiFetch(`${API_BASE}/api/network/${encodeURIComponent(email)}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await readErrorDetail(res, 'Failed to delete contact'));
}

export async function deleteContact(contactId: string): Promise<void> {
  const res = await apiFetch(`${API_BASE}/api/contacts/${contactId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await readErrorDetail(res, 'Failed to delete contact'));
}

export async function createContact(payload: {
  name?: string;
  title?: string;
  email?: string;
  company_name?: string;
  phone_number?: string;
  linkedin_url?: string;
  application_id?: string;
}): Promise<any> {
  const res = await apiFetch(`${API_BASE}/api/contacts`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await readErrorDetail(res, 'Failed to create contact'));
  return await res.json();
}

export async function updateContact(contactId: string, payload: {
  name?: string;
  title?: string;
  email?: string;
  company_name?: string;
  phone_number?: string;
  linkedin_url?: string;
  application_id?: string | null;
  reached_out?: boolean;
  reached_out_at?: string;
  response_received?: boolean;
}): Promise<any> {
  const body = { ...payload, application_id: payload.application_id ?? undefined };
  const res = await apiFetch(`${API_BASE}/api/contacts/${contactId}`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await readErrorDetail(res, 'Failed to update contact'));
  return await res.json();
}

export async function linkContactToApplication(contactId: string, applicationId: string | null): Promise<void> {
  const res = await apiFetch(`${API_BASE}/api/contacts/${contactId}`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify({ application_id: applicationId ?? '' }),
  });
  if (!res.ok) throw new Error(await readErrorDetail(res, 'Failed to link contact to application'));
}

export async function fetchResumeDrafts(applicationId: string): Promise<any[]> {
  return await fetchPaginatedArray<any>((limit, offset) => (
    `${API_BASE}/api/resume/drafts/${applicationId}?limit=${limit}&offset=${offset}`
  ));
}

export async function fetchResumeDraft(applicationId: string, draftId: string): Promise<any> {
  const res = await apiFetch(`${API_BASE}/api/resume/drafts/${applicationId}/${draftId}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(await readErrorDetail(res, 'Failed to load resume draft'));
  return await res.json();
}

// --- Export API ---

export function getExportUrl(): string {
  return `${API_BASE}/api/export/csv`;
}

export async function exportCsv(): Promise<void> {
  const res = await apiFetch(`${API_BASE}/api/export/csv`, { headers: authHeaders() });
  if (!res.ok) throw new Error(await readErrorDetail(res, `Failed to export: ${res.status}`));
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'apptrail_export.csv';
  a.click();
  URL.revokeObjectURL(url);
}


export async function fetchResearchProfiles(): Promise<ResearchProfile[]> {
  const res = await apiFetch(`${API_BASE}/api/research/profiles`, { headers: authHeaders() });
  if (!res.ok) throw new Error(await readErrorDetail(res, 'Failed to fetch research profiles'));
  return await res.json();
}

export async function createResearchProfile(payload: Partial<ResearchProfile>): Promise<ResearchProfile> {
  const res = await apiFetch(`${API_BASE}/api/research/profiles`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await readErrorDetail(res, 'Failed to create research profile'));
  return await res.json();
}

export async function updateResearchProfile(id: string, payload: Partial<ResearchProfile>): Promise<ResearchProfile> {
  const res = await apiFetch(`${API_BASE}/api/research/profiles/${id}`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await readErrorDetail(res, 'Failed to update research profile'));
  return await res.json();
}

export async function deleteResearchProfile(id: string): Promise<void> {
  const res = await apiFetch(`${API_BASE}/api/research/profiles/${id}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await readErrorDetail(res, 'Failed to delete research profile'));
}

export async function runResearchProfile(id: string): Promise<any> {
  const res = await apiFetch(`${API_BASE}/api/research/profiles/${id}/run`, {
    method: 'POST',
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await readErrorDetail(res, 'Failed to run research profile'));
  return await res.json();
}

export async function fetchResearchRuns(profileId?: string): Promise<any[]> {
  const query = profileId ? `?profile_id=${encodeURIComponent(profileId)}` : '';
  const res = await apiFetch(`${API_BASE}/api/research/runs${query}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(await readErrorDetail(res, 'Failed to fetch research runs'));
  return await res.json();
}

export async function fetchOpportunitySignals(profileId?: string): Promise<OpportunitySignal[]> {
  const query = profileId ? `?profile_id=${encodeURIComponent(profileId)}` : '';
  const res = await apiFetch(`${API_BASE}/api/research/signals${query}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(await readErrorDetail(res, 'Failed to fetch opportunity signals'));
  return await res.json();
}

export async function fetchOpportunityBriefs(profileId?: string): Promise<OpportunityBrief[]> {
  const query = profileId ? `?profile_id=${encodeURIComponent(profileId)}` : '';
  const res = await apiFetch(`${API_BASE}/api/research/briefs${query}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(await readErrorDetail(res, 'Failed to fetch opportunity briefs'));
  return await res.json();
}

export async function fetchRecommendedActions(profileId?: string): Promise<RecommendedAction[]> {
  const query = profileId ? `?profile_id=${encodeURIComponent(profileId)}` : '';
  const res = await apiFetch(`${API_BASE}/api/research/actions${query}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(await readErrorDetail(res, 'Failed to fetch recommended actions'));
  return await res.json();
}

export async function updateRecommendedAction(id: string, payload: { status: string }): Promise<RecommendedAction> {
  const res = await apiFetch(`${API_BASE}/api/research/actions/${id}`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await readErrorDetail(res, 'Failed to update recommended action'));
  return await res.json();
}

export async function acceptRecommendedAction(id: string): Promise<RecommendedAction> {
  const res = await apiFetch(`${API_BASE}/api/research/actions/${id}/accept`, {
    method: 'POST',
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await readErrorDetail(res, 'Failed to accept recommended action'));
  return await res.json();
}

export async function sendResearchFeedback(payload: { signal_id?: string; brief_id?: string; action_id?: string; rating: string; notes?: string }): Promise<any> {
  const res = await apiFetch(`${API_BASE}/api/research/feedback`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await readErrorDetail(res, 'Failed to save research feedback'));
  return await res.json();
}
