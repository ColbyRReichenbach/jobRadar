import { OpportunitySignal } from '../types';
import { SignalCard } from './SignalCard';

interface SignalFeedProps {
  loading: boolean;
  signals: OpportunitySignal[];
  selectedSignalId?: string;
  onSelectSignal: (signal: OpportunitySignal) => void;
}

export function SignalFeed({ loading, signals, selectedSignalId, onSelectSignal }: SignalFeedProps) {
  if (loading) return <div className="text-sm text-slate-500">Loading signals...</div>;
  if (!signals.length) return <div className="text-sm text-slate-500">No signals yet. Run a tracker to generate internal-source signals.</div>;

  return (
    <div className="space-y-3">
      {signals.map((signal) => (
        <SignalCard
          key={signal.id}
          signal={signal}
          selected={selectedSignalId === signal.id}
          onSelect={onSelectSignal}
        />
      ))}
    </div>
  );
}
