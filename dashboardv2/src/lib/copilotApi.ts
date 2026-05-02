import { apiFetch, authHeaders } from './api';

export type CopilotRole = 'user' | 'assistant';
export type CopilotFeedbackRating = 'thumbs_up' | 'thumbs_down';

export interface CopilotConversation {
  id: string;
  title: string;
  status: string;
  created_at: string | null;
  updated_at: string | null;
  last_message_at: string | null;
}

export interface CopilotCitation {
  document_id: string;
  source_type: string;
  source_id: string;
  title: string;
  snippet?: string | null;
}

export interface CopilotSuggestedAction {
  title: string;
  description?: string | null;
  action_type: string;
  requires_confirmation: boolean;
  read_only?: boolean;
}

export interface CopilotMessageMetadata {
  mode?: string | null;
  model?: string | null;
  prompt_version?: string | null;
}

export interface CopilotMessage {
  id: string;
  conversation_id: string;
  role: CopilotRole;
  content: string;
  citations: CopilotCitation[];
  suggested_actions: CopilotSuggestedAction[];
  metadata: CopilotMessageMetadata;
  model_call_id: string | null;
  created_at: string | null;
}

export interface CopilotSearchResult {
  document_id: string;
  source_type: string;
  source_id: string;
  title: string;
  subtitle?: string | null;
  snippet?: string | null;
  score: number;
  metadata: Record<string, unknown>;
}

export interface CopilotFeedback {
  id: string;
  message_id: string;
  rating: CopilotFeedbackRating;
  notes?: string | null;
  created_at: string | null;
}

export class CopilotApiError extends Error {
  status: number;
  detail: string;

  constructor(message: string, status: number, detail: string) {
    super(message);
    this.name = 'CopilotApiError';
    this.status = status;
    this.detail = detail;
  }
}

async function readErrorDetail(res: Response, fallback: string): Promise<string> {
  const payload = await res.json().catch(() => null);
  if (typeof payload?.detail === 'string') return payload.detail;
  if (typeof payload?.message === 'string') return payload.message;
  if (typeof payload?.detail?.message === 'string') return payload.detail.message;
  return fallback;
}

function jsonHeaders(extraHeaders?: HeadersInit): Record<string, string> {
  return {
    ...authHeaders(),
    ...(extraHeaders as Record<string, string> | undefined),
  };
}

async function requestJson<T>(path: string, options: RequestInit = {}, fallbackError = 'Copilot request failed.'): Promise<T> {
  const res = await apiFetch(path, {
    ...options,
    headers: jsonHeaders(options.headers),
  });

  if (!res.ok) {
    const detail = await readErrorDetail(res, fallbackError);
    throw new CopilotApiError(detail, res.status, detail);
  }

  return res.json() as Promise<T>;
}

export async function createCopilotConversation(title?: string): Promise<CopilotConversation> {
  const payload = await requestJson<{ conversation: CopilotConversation }>(
    '/api/copilot/conversations',
    {
      method: 'POST',
      body: JSON.stringify({ title }),
    },
    'Failed to create Copilot conversation.'
  );
  return payload.conversation;
}

export async function listCopilotConversations(limit = 20): Promise<CopilotConversation[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  const payload = await requestJson<{ conversations: CopilotConversation[] }>(
    `/api/copilot/conversations?${params.toString()}`,
    {},
    'Failed to load Copilot conversations.'
  );
  return payload.conversations;
}

export async function getCopilotConversation(conversationId: string): Promise<{
  conversation: CopilotConversation;
  messages: CopilotMessage[];
}> {
  return requestJson(
    `/api/copilot/conversations/${encodeURIComponent(conversationId)}`,
    {},
    'Failed to load Copilot conversation.'
  );
}

export async function sendCopilotMessage(
  conversationId: string,
  content: string,
  sourceTypes?: string[]
): Promise<{
  conversation: CopilotConversation;
  user_message: CopilotMessage;
  assistant_message: CopilotMessage;
}> {
  return requestJson(
    `/api/copilot/conversations/${encodeURIComponent(conversationId)}/messages`,
    {
      method: 'POST',
      body: JSON.stringify({
        content,
        source_types: sourceTypes?.length ? sourceTypes : undefined,
      }),
    },
    'Failed to send Copilot message.'
  );
}

export async function searchCopilot(
  query: string,
  options: { sourceTypes?: string[]; limit?: number } = {}
): Promise<CopilotSearchResult[]> {
  const payload = await requestJson<{ results: CopilotSearchResult[] }>(
    '/api/copilot/search',
    {
      method: 'POST',
      body: JSON.stringify({
        query,
        source_types: options.sourceTypes?.length ? options.sourceTypes : undefined,
        limit: options.limit ?? 8,
      }),
    },
    'Failed to search Copilot documents.'
  );
  return payload.results;
}

export async function sendCopilotFeedback(
  messageId: string,
  rating: CopilotFeedbackRating,
  notes?: string
): Promise<CopilotFeedback> {
  const payload = await requestJson<{ feedback: CopilotFeedback }>(
    `/api/copilot/messages/${encodeURIComponent(messageId)}/feedback`,
    {
      method: 'POST',
      body: JSON.stringify({ rating, notes }),
    },
    'Failed to save Copilot feedback.'
  );
  return payload.feedback;
}
