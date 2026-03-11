import { type ReactNode, useEffect, useRef } from 'react';
import { motion } from 'motion/react';

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

interface DialogShellProps {
  onClose: () => void;
  titleId: string;
  children: ReactNode;
  panelClassName: string;
  wrapperClassName?: string;
  overlayClassName?: string;
  initialFocusRef?: React.RefObject<HTMLElement | null>;
  describedById?: string;
  layoutId?: string;
}

export function DialogShell({
  onClose,
  titleId,
  children,
  panelClassName,
  wrapperClassName = 'fixed inset-0 z-50',
  overlayClassName = 'absolute inset-0 bg-slate-900/40 backdrop-blur-sm',
  initialFocusRef,
  describedById,
  layoutId,
}: DialogShellProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previousActive = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;

    document.body.style.overflow = 'hidden';

    const frame = window.requestAnimationFrame(() => {
      const focusTarget =
        initialFocusRef?.current ||
        panelRef.current?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR) ||
        panelRef.current;

      focusTarget?.focus();
    });

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        return;
      }

      if (event.key !== 'Tab' || !panelRef.current) return;

      const focusable = Array.from(
        panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      ).filter((element) => !element.hasAttribute('disabled') && element.tabIndex !== -1);

      if (focusable.length === 0) {
        event.preventDefault();
        panelRef.current.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;

      if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);

    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = previousOverflow;
      previousActive?.focus();
    };
  }, [initialFocusRef, onClose]);

  return (
    <div className={wrapperClassName}>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className={overlayClassName}
      />
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        layoutId={layoutId}
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={describedById}
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
        className={`${panelClassName} relative z-10`}
      >
        {children}
      </motion.div>
    </div>
  );
}
