import { useState } from 'react';
import { ThumbsDown, ThumbsUp } from 'lucide-react';
import { CopilotFeedbackRating, sendCopilotFeedback } from '../../lib/copilotApi';
import { cn } from '../../lib/utils';

interface CopilotFeedbackProps {
  messageId: string;
}

export function CopilotFeedback({ messageId }: CopilotFeedbackProps) {
  const [rating, setRating] = useState<CopilotFeedbackRating | null>(null);
  const [status, setStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');

  const handleFeedback = async (nextRating: CopilotFeedbackRating) => {
    setStatus('saving');
    try {
      await sendCopilotFeedback(messageId, nextRating);
      setRating(nextRating);
      setStatus('saved');
    } catch {
      setStatus('error');
    }
  };

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-400">
      <span>Was this useful?</span>
      <button
        type="button"
        onClick={() => void handleFeedback('thumbs_up')}
        disabled={status === 'saving'}
        aria-label="Mark answer as helpful"
        aria-pressed={rating === 'thumbs_up'}
        className={cn(
          'inline-flex h-8 w-8 items-center justify-center rounded-lg border transition-colors disabled:opacity-60',
          rating === 'thumbs_up'
            ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
            : 'border-slate-200 bg-white text-slate-500 hover:bg-slate-50'
        )}
      >
        <ThumbsUp className="h-3.5 w-3.5" />
      </button>
      <button
        type="button"
        onClick={() => void handleFeedback('thumbs_down')}
        disabled={status === 'saving'}
        aria-label="Mark answer as not helpful"
        aria-pressed={rating === 'thumbs_down'}
        className={cn(
          'inline-flex h-8 w-8 items-center justify-center rounded-lg border transition-colors disabled:opacity-60',
          rating === 'thumbs_down'
            ? 'border-red-200 bg-red-50 text-red-700'
            : 'border-slate-200 bg-white text-slate-500 hover:bg-slate-50'
        )}
      >
        <ThumbsDown className="h-3.5 w-3.5" />
      </button>
      {status === 'saved' && <span className="text-emerald-600">Feedback saved</span>}
      {status === 'error' && <span className="text-red-600">Feedback failed</span>}
    </div>
  );
}
