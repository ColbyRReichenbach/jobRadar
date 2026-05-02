import { useState } from 'react';
import { motion } from 'motion/react';
import { Sparkles } from 'lucide-react';
import { CopilotPanel } from './CopilotPanel';

interface CopilotLauncherProps {
  onNavigate?: (actionUrl: string) => void;
}

export function CopilotLauncher({ onNavigate }: CopilotLauncherProps) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <CopilotPanel
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        onNavigate={onNavigate}
      />
      {!isOpen && (
        <motion.button
          type="button"
          onClick={() => setIsOpen(true)}
          whileHover={{ width: 152 }}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="group fixed bottom-5 right-5 z-[64] inline-flex h-14 w-14 items-center justify-start overflow-hidden rounded-2xl border border-slate-200 bg-slate-900 text-white shadow-2xl transition-colors hover:bg-slate-800 md:bottom-6 md:right-6"
          aria-label="Ask AppTrail"
          title="Ask AppTrail"
        >
          <span className="inline-flex h-14 w-14 shrink-0 items-center justify-center">
            <Sparkles className="h-5 w-5" />
          </span>
          <span className="whitespace-nowrap pr-4 text-sm font-semibold opacity-0 transition-opacity duration-150 group-hover:opacity-100">
            Ask AppTrail
          </span>
        </motion.button>
      )}
    </>
  );
}
