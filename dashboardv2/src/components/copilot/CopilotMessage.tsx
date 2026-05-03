import { Bot, User } from 'lucide-react';
import { CopilotMessage as CopilotMessageType } from '../../lib/copilotApi';
import { cn } from '../../lib/utils';
import { CopilotCitations } from './CopilotCitations';
import { CopilotFeedback } from './CopilotFeedback';
import { CopilotSuggestedActions } from './CopilotSuggestedActions';

interface CopilotMessageProps {
  message: CopilotMessageType;
  onNavigate?: (actionUrl: string) => void;
}

function modeLabel(mode?: string | null): string | null {
  if (!mode) return null;
  if (mode === 'search_fallback') return 'Search fallback';
  if (mode === 'model') return 'Model answer';
  return mode.replaceAll('_', ' ');
}

export function CopilotMessage({ message, onNavigate }: CopilotMessageProps) {
  const isUser = message.role === 'user';
  const ModeIcon = isUser ? User : Bot;
  const renderedMode = modeLabel(message.metadata?.mode);

  return (
    <div className={cn('flex gap-3', isUser ? 'justify-end' : 'justify-start')}>
      {!isUser && (
        <div className="mt-1 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-slate-800 text-white shadow-sm">
          <ModeIcon className="h-4 w-4" />
        </div>
      )}

      <div className={cn('max-w-[86%] md:max-w-[82%]', isUser && 'order-first')}>
        <div
          className={cn(
            'rounded-2xl border px-4 py-3 text-sm leading-6 shadow-sm [overflow-wrap:anywhere]',
            isUser
              ? 'border-slate-800 bg-slate-800 text-white'
              : 'border-slate-200 bg-white text-slate-700'
          )}
        >
          <div className="whitespace-pre-wrap">{message.content}</div>
        </div>

        {!isUser && renderedMode ? (
          <div className="mt-2 inline-flex rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            {renderedMode}
          </div>
        ) : null}

        {!isUser && (
          <>
            <CopilotCitations citations={message.citations || []} onNavigate={onNavigate} />
            <CopilotSuggestedActions actions={message.suggested_actions || []} />
            <CopilotFeedback messageId={message.id} />
          </>
        )}
      </div>

      {isUser && (
        <div className="mt-1 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-500 shadow-sm">
          <ModeIcon className="h-4 w-4" />
        </div>
      )}
    </div>
  );
}
