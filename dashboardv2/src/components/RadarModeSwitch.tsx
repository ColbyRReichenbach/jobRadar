import { ResearchProfile } from '../types';

type RadarSurface = 'signals' | 'reports';

interface RadarModeSwitchProps {
  trackerMode?: ResearchProfile['mode'] | null;
  surface: RadarSurface;
  onChange: (surface: RadarSurface) => void;
}

const SURFACE_COPY: Record<RadarSurface, { title: string; body: string }> = {
  signals: {
    title: 'Signals',
    body: 'Ranked opportunities from your AppTrail activity, briefs, and action suggestions.',
  },
  reports: {
    title: 'Reports',
    body: 'Saved research runs with evidence, dated findings, and change tracking.',
  },
};

export function RadarModeSwitch({ trackerMode, surface, onChange }: RadarModeSwitchProps) {
  const supportsSignals = trackerMode !== 'research';
  const supportsReports = trackerMode === 'research' || trackerMode === 'hybrid';
  const options = (['signals', 'reports'] as RadarSurface[]).filter((entry) =>
    entry === 'signals' ? supportsSignals : supportsReports
  );

  if (options.length <= 1) {
    const onlyOption = options[0] || 'signals';
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-4">
        <div className="text-sm font-semibold text-slate-900">{SURFACE_COPY[onlyOption].title}</div>
        <p className="mt-1 text-xs leading-5 text-slate-500">{SURFACE_COPY[onlyOption].body}</p>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap gap-2">
        {options.map((option) => {
          const active = option === surface;
          return (
            <button
              key={option}
              type="button"
              onClick={() => onChange(option)}
              className={`rounded-xl px-3 py-2 text-sm ${
                active ? 'bg-slate-900 text-white' : 'border border-slate-300 text-slate-700'
              }`}
            >
              {SURFACE_COPY[option].title}
            </button>
          );
        })}
      </div>
      <p className="mt-3 text-xs leading-5 text-slate-500">{SURFACE_COPY[surface].body}</p>
    </div>
  );
}
