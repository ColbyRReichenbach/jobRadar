import { RecommendedAction } from '../types';

interface RecommendedActionsProps {
  actions: RecommendedAction[];
  onAccept: (actionId: string) => Promise<void>;
  onDismiss: (actionId: string) => Promise<void>;
}

export function RecommendedActions({ actions, onAccept, onDismiss }: RecommendedActionsProps) {
  if (!actions.length) return <div className="text-sm text-slate-500">No actions yet.</div>;

  return (
    <div className="space-y-2">
      {actions.map((action) => (
        <div key={action.id} className="rounded-lg border border-slate-200 p-2">
          <div className="text-sm font-medium text-slate-900">{action.title}</div>
          <div className="text-xs text-slate-500">{action.action_type} · {action.status}</div>
          <div className="mt-2 flex gap-2">
            <button className="text-xs px-2 py-1 border rounded" onClick={() => onAccept(action.id)}>Accept</button>
            <button className="text-xs px-2 py-1 border rounded" onClick={() => onDismiss(action.id)}>Dismiss</button>
          </div>
        </div>
      ))}
    </div>
  );
}
