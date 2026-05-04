import { FormEvent, KeyboardEvent, useEffect, useId, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Loader2, MessageSquarePlus, Send, X } from 'lucide-react';
import {
  CopilotApiError,
  CopilotConversation,
  CopilotMessage as CopilotMessageType,
  createCopilotConversation,
  sendCopilotMessage,
} from '../../lib/copilotApi';
import { cn } from '../../lib/utils';
import { CopilotMessage } from './CopilotMessage';
import { ScoutLogo } from './ScoutLogo';

interface CopilotPanelProps {
  isOpen: boolean;
  onClose: () => void;
  onNavigate?: (actionUrl: string) => void;
  seedPrompt?: {
    id: number;
    prompt: string;
    autoSubmit?: boolean;
  } | null;
}

const STARTER_PROMPTS = [
  'Help me set up a Radar tracker.',
  'Which applications need follow-up?',
  'Summarize my latest recruiter conversations.',
  'What opportunity signals should I act on first?',
];

function emptyMessage(conversationId: string, role: 'user' | 'assistant', content: string): CopilotMessageType {
  return {
    id: `pending-${role}-${Date.now()}`,
    conversation_id: conversationId,
    role,
    content,
    citations: [],
    suggested_actions: [],
    metadata: {},
    model_call_id: null,
    created_at: new Date().toISOString(),
  };
}

function errorMessage(error: unknown): string {
  if (error instanceof CopilotApiError) {
    if (error.status === 401) return 'Your session expired. Sign in again to use Copilot.';
    if (error.status === 403) return 'Copilot is disabled for this environment.';
    if (error.status === 413) return 'That message is too long for Copilot.';
    if (error.status === 422) return error.detail;
    if (error.status === 429) return 'Copilot is paused by request or budget limits. Try again later.';
    if (error.status >= 500) return 'Copilot is temporarily unavailable.';
    return error.detail || 'Copilot request failed.';
  }
  return 'Copilot request failed.';
}

export function CopilotPanel({ isOpen, onClose, onNavigate, seedPrompt }: CopilotPanelProps) {
  const titleId = useId();
  const descriptionId = useId();
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const handledSeedPromptId = useRef<number | null>(null);
  const [conversation, setConversation] = useState<CopilotConversation | null>(null);
  const [messages, setMessages] = useState<CopilotMessageType[]>([]);
  const [input, setInput] = useState('');
  const [status, setStatus] = useState<'idle' | 'sending'>('idle');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    const frame = window.requestAnimationFrame(() => {
      inputRef.current?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    });
  }, [messages, status]);

  const submitMessage = async (content: string) => {
    const clean = content.trim();
    if (!clean || status === 'sending') return;

    setStatus('sending');
    setError(null);
    setInput('');

    const pendingConversationId = conversation?.id || 'pending-conversation';
    const pending = emptyMessage(pendingConversationId, 'user', clean);
    setMessages((current) => [...current, pending]);

    try {
      const activeConversation = conversation || await createCopilotConversation(clean.slice(0, 80));
      if (!conversation) {
        setConversation(activeConversation);
      }
      const response = await sendCopilotMessage(activeConversation.id, clean);
      setConversation(response.conversation);
      setMessages((current) => [
        ...current.filter((message) => message.id !== pending.id),
        response.user_message,
        response.assistant_message,
      ]);
    } catch (err) {
      setInput(clean);
      setMessages((current) => current.filter((message) => message.id !== pending.id));
      setError(errorMessage(err));
    } finally {
      setStatus('idle');
    }
  };

  useEffect(() => {
    if (!isOpen || !seedPrompt?.prompt || handledSeedPromptId.current === seedPrompt.id) return;
    handledSeedPromptId.current = seedPrompt.id;
    if (seedPrompt.autoSubmit) {
      void submitMessage(seedPrompt.prompt);
      return;
    }
    setInput(seedPrompt.prompt);
    window.requestAnimationFrame(() => inputRef.current?.focus());
  }, [isOpen, seedPrompt?.id]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void submitMessage(input);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void submitMessage(input);
    }
  };

  const resetConversation = () => {
    setConversation(null);
    setMessages([]);
    setInput('');
    setError(null);
    window.requestAnimationFrame(() => inputRef.current?.focus());
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.section
          role="dialog"
          aria-modal="false"
          aria-labelledby={titleId}
          aria-describedby={descriptionId}
          initial={{ opacity: 0, y: 18, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 18, scale: 0.98 }}
          transition={{ duration: 0.18 }}
          className="fixed inset-x-0 bottom-0 z-[65] flex max-h-[86vh] min-h-[70vh] flex-col overflow-hidden rounded-t-3xl border border-slate-200 bg-white shadow-2xl md:inset-auto md:bottom-6 md:right-6 md:h-[min(720px,calc(100vh-3rem))] md:min-h-0 md:w-[440px] md:max-w-[calc(100vw-2rem)] md:rounded-3xl"
        >
          <div className="shrink-0 border-b border-slate-100 bg-slate-50/80 px-4 py-4 md:px-5">
            <div className="flex items-start justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <div className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-[#172033] text-white shadow-sm">
                  <ScoutLogo className="h-7 w-7 text-white" />
                </div>
                <div className="min-w-0">
                  <h2 id={titleId} className="text-lg font-serif font-bold tracking-tight text-slate-900">
                    Ask Scout
                  </h2>
                  <p id={descriptionId} className="text-xs text-slate-500">
                    {conversation?.title || 'Copilot'}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={resetConversation}
                  className="inline-flex h-9 w-9 items-center justify-center rounded-xl text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-900"
                  aria-label="Start new Copilot chat"
                  title="New chat"
                >
                  <MessageSquarePlus className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={onClose}
                  className="inline-flex h-9 w-9 items-center justify-center rounded-xl text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-900"
                  aria-label="Close Copilot"
                  title="Close"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>

          <div ref={scrollRef} className="flex-1 overflow-y-auto bg-[#F5F5F0] px-4 py-4 md:px-5">
            {messages.length === 0 ? (
              <div className="flex min-h-full flex-col justify-end gap-4">
                <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="mb-3 inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-[#172033] text-white shadow-sm">
                    <ScoutLogo className="h-7 w-7 text-white" />
                  </div>
                  <h3 className="text-xl font-serif font-bold tracking-tight text-slate-900">
                    Where should you focus next?
                  </h3>
                </div>
                <div className="grid gap-2">
                  {STARTER_PROMPTS.map((prompt) => (
                    <button
                      key={prompt}
                      type="button"
                      onClick={() => void submitMessage(prompt)}
                      className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-left text-sm font-medium text-slate-700 shadow-sm transition-colors hover:border-slate-300 hover:bg-slate-50"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="space-y-5">
                {messages.map((message) => (
                  <CopilotMessage key={message.id} message={message} onNavigate={onNavigate} />
                ))}
                {status === 'sending' ? (
                  <div className="flex items-center gap-3 text-sm text-slate-500">
                    <div className="inline-flex h-8 w-8 items-center justify-center rounded-xl bg-slate-800 text-white">
                      <Loader2 className="h-4 w-4 animate-spin" />
                    </div>
                    <span>Thinking...</span>
                  </div>
                ) : null}
              </div>
            )}
          </div>

          <form onSubmit={handleSubmit} className="shrink-0 border-t border-slate-100 bg-white p-3 md:p-4">
            {error ? (
              <div className="mb-3 rounded-2xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 [overflow-wrap:anywhere]">
                {error}
              </div>
            ) : null}
            <div className="flex items-end gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-2 focus-within:border-indigo-300 focus-within:ring-2 focus-within:ring-indigo-500/10">
              <label htmlFor="copilot-message" className="sr-only">
                Ask Scout a question
              </label>
              <textarea
                ref={inputRef}
                id="copilot-message"
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={handleKeyDown}
                rows={1}
                placeholder="Ask Scout about your pipeline..."
                className="max-h-32 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-5 text-slate-900 outline-none placeholder:text-slate-400"
              />
              <button
                type="submit"
                disabled={!input.trim() || status === 'sending'}
                aria-label="Send message"
                className={cn(
                  'inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-colors',
                  input.trim() && status !== 'sending'
                    ? 'bg-slate-800 text-white hover:bg-slate-700'
                    : 'bg-slate-200 text-slate-400'
                )}
              >
                {status === 'sending' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </button>
            </div>
          </form>
        </motion.section>
      )}
    </AnimatePresence>
  );
}
