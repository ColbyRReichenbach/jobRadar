import { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import { CopilotPanel } from './CopilotPanel';
import { ScoutLogo } from './ScoutLogo';

interface CopilotLauncherProps {
  onNavigate?: (actionUrl: string) => void;
}

export function CopilotLauncher({ onNavigate }: CopilotLauncherProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [seedPrompt, setSeedPrompt] = useState<{ id: number; prompt: string; autoSubmit?: boolean } | null>(null);

  useEffect(() => {
    const handleOpenScout = (event: Event) => {
      const detail = (event as CustomEvent<{ prompt?: string; autoSubmit?: boolean }>).detail;
      setSeedPrompt({
        id: Date.now(),
        prompt: detail?.prompt || '',
        autoSubmit: detail?.autoSubmit,
      });
      setIsOpen(true);
    };

    window.addEventListener('apptrail:open-scout', handleOpenScout);
    return () => window.removeEventListener('apptrail:open-scout', handleOpenScout);
  }, []);

  return (
    <>
      <CopilotPanel
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        onNavigate={onNavigate}
        seedPrompt={seedPrompt}
      />
      {!isOpen && (
        <motion.button
          type="button"
          onClick={() => setIsOpen(true)}
          whileHover={{ width: 152 }}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="group fixed bottom-5 right-5 z-[64] inline-flex h-14 w-14 items-center justify-start overflow-hidden rounded-2xl border border-slate-200 bg-[#172033] text-white shadow-2xl transition-colors hover:bg-[#111827] md:bottom-6 md:right-6"
          aria-label="Ask Scout"
          title="Ask Scout"
        >
          <span className="inline-flex h-14 w-14 shrink-0 items-center justify-center">
            <ScoutLogo className="h-8 w-8 text-white" />
          </span>
          <span className="whitespace-nowrap pr-4 text-sm font-semibold opacity-0 transition-opacity duration-150 group-hover:opacity-100">
            Ask Scout
          </span>
        </motion.button>
      )}
    </>
  );
}
