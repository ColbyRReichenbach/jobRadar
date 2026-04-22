import { useState } from 'react';

interface RadarProfileFormProps {
  creating: boolean;
  onCreate: (payload: { name: string; objective: string }) => Promise<void>;
}

export function RadarProfileForm({ creating, onCreate }: RadarProfileFormProps) {
  const [name, setName] = useState('');
  const [objective, setObjective] = useState('');

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 space-y-2">
      <h2 className="font-semibold text-slate-800">New tracker</h2>
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Tracker name" className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
      <textarea value={objective} onChange={(e) => setObjective(e.target.value)} placeholder="Objective" className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
      <button
        onClick={async () => {
          if (!name.trim()) return;
          await onCreate({ name: name.trim(), objective: objective.trim() });
          setName('');
          setObjective('');
        }}
        disabled={creating}
        className="w-full px-3 py-2 rounded-xl bg-slate-800 text-white text-sm disabled:opacity-50"
      >
        {creating ? 'Creating...' : 'Create Tracker'}
      </button>
    </div>
  );
}
