import { RecommendedAction } from '../types';

interface RecommendedActionsProps {
  actions: RecommendedAction[];
  busyActionId?: string | null;
  onAccept: (actionId: string) => Promise<void>;
  onDismiss: (actionId: string) => Promise<void>;
  onComplete: (actionId: string) => Promise<void>;
}

function canAccept(status: RecommendedAction['status']) {
  return status === 'open';
}

function canDismiss(status: RecommendedAction['status']) {
  return status === 'open' || status === 'accepted';
}

function canComplete(status: RecommendedAction['status']) {
  return status === 'open' || status === 'accepted';
}

export function RecommendedActions({ actions, busyActionId, onAccept, onDismiss, onComplete }: RecommendedActionsProps) {
  if (!actions.length) return <div className="text-sm text-slate-500">No actions tied to this selection yet.</div>;

  return (
    <div className="space-y-3">
      {actions.map((action) => {
        const busy = busyActionId === action.id;
        return (
          <div key={action.id} className="rounded-xl border border-slate-200 p-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-slate-900">{action.title}</div>
                <div className="mt-1 text-xs text-slate-500">
                  {action.action_type.replaceAll('_', ' ')} · priority {action.priority} · {action.status}
                </div>
              </div>
              <div className="rounded-full bg-slate-100 px-2 py-1 text-[11px] text-slate-700">
                {action.status}
              </div>
            </div>

            {action.body ? <p className="mt-2 text-sm leading-6 text-slate-600">{action.body}</p> : null}

            {action.payload ? (
              <pre className="mt-2 overflow-auto rounded-lg bg-slate-50 p-2 text-[11px] leading-5 text-slate-500">
                {JSON.stringify(action.payload, null, 2)}
              </pre>
            ) : null}

            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                disabled={busy || !canAccept(action.status)}
                className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs text-slate-700 disabled:opacity-40"
                onClick={() => onAccept(action.id)}
              >
                Accept
              </button>
              <button
                type="button"
                disabled={busy || !canComplete(action.status)}
                className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs text-slate-700 disabled:opacity-40"
                onClick={() => onComplete(action.id)}
              >
                Complete
              </button>
              <button
                type="button"
                disabled={busy || !canDismiss(action.status)}
                className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs text-slate-700 disabled:opacity-40"
                onClick={() => onDismiss(action.id)}
              >
                Dismiss
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
