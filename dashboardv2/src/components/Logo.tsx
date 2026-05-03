import { motion } from 'motion/react';

interface LogoProps {
  className?: string;
  variant?: 'mark' | 'copilot';
}

const drawTransition = { duration: 1.05, ease: 'easeInOut' } as const;
const nodeSpring = { type: 'spring', stiffness: 320, damping: 18 } as const;
const sage = '#95AA98';
const brass = '#C89B52';
const cream = '#F7F1E7';

export function Logo({ className, variant = 'mark' }: LogoProps) {
  const showCopilotSpark = variant === 'copilot';

  return (
    <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
      <motion.path
        d="M19.55 11.8C19.8 16.45 16.35 19.6 12.1 19.75C7.55 19.9 4.25 16.55 4.3 12.25C4.35 7.85 7.65 4.55 11.95 4.35C14.85 4.2 17.25 5.45 18.75 7.55"
        stroke="currentColor"
        strokeWidth="1.65"
        strokeLinecap="round"
        strokeLinejoin="round"
        variants={{
          initial: { pathLength: 0, opacity: 0 },
          animate: { pathLength: 1, opacity: 1, transition: drawTransition },
          hover: { pathLength: [1, 0.18, 1], transition: { duration: 1.45, ease: 'easeInOut' } },
        }}
      />
      <motion.path
        d="M7.7 14.65C6.85 12.25 7.7 9.55 9.95 8.1C12.15 6.7 15.25 7.35 16.45 9.9"
        stroke="currentColor"
        strokeWidth="1"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.32"
        variants={{
          initial: { pathLength: 0, opacity: 0 },
          animate: { pathLength: 1, opacity: 0.34, transition: { duration: 0.7, delay: 0.3, ease: 'easeOut' } },
          hover: { opacity: [0.34, 0.58, 0.34], transition: { duration: 0.9 } },
        }}
      />
      <motion.path
        d="M11.75 12.15C14.35 10.45 16.55 8.45 18.75 5.7"
        stroke={sage}
        strokeWidth="2"
        strokeLinecap="round"
        variants={{
          initial: { pathLength: 0, opacity: 0 },
          animate: { pathLength: 1, opacity: 1, transition: { ...drawTransition, delay: 0.22 } },
          hover: { pathLength: [1, 0, 1], opacity: [1, 0.45, 1], transition: { duration: 1.1, ease: 'easeInOut' } },
        }}
      />
      <motion.path
        d="M6.55 15.55C8 13.55 9.45 12.25 11.35 12.05C13.05 11.85 14.15 12.8 15.45 12.25C16.6 11.8 17.35 10.35 18.45 8.25"
        stroke="currentColor"
        strokeWidth="1.45"
        strokeLinecap="round"
        strokeLinejoin="round"
        variants={{
          initial: { pathLength: 0, opacity: 0 },
          animate: { pathLength: 1, opacity: 1, transition: { duration: 0.95, delay: 0.58, ease: 'easeOut' } },
          hover: { pathLength: [1, 0.2, 1], transition: { duration: 1.2, ease: 'easeInOut' } },
        }}
      />
      <motion.circle
        cx="6.55"
        cy="15.55"
        r="0.95"
        fill={cream}
        variants={{
          initial: { scale: 0 },
          animate: { scale: 1, transition: { ...nodeSpring, delay: 0.74 } },
          hover: { scale: [1, 1.25, 1], transition: { duration: 0.45 } },
        }}
        style={{ transformBox: 'fill-box', transformOrigin: 'center' }}
      />
      <motion.circle
        cx="11.35"
        cy="12.05"
        r="0.95"
        fill={cream}
        variants={{
          initial: { scale: 0 },
          animate: { scale: 1, transition: { ...nodeSpring, delay: 0.88 } },
          hover: { scale: [1, 1.25, 1], transition: { duration: 0.45, delay: 0.08 } },
        }}
        style={{ transformBox: 'fill-box', transformOrigin: 'center' }}
      />
      <motion.circle
        cx="15.45"
        cy="12.25"
        r="0.95"
        fill={cream}
        variants={{
          initial: { scale: 0 },
          animate: { scale: 1, transition: { ...nodeSpring, delay: 1.02 } },
          hover: { scale: [1, 1.25, 1], transition: { duration: 0.45, delay: 0.16 } },
        }}
        style={{ transformBox: 'fill-box', transformOrigin: 'center' }}
      />
      <motion.circle
        cx="18.45"
        cy="8.25"
        r="1.45"
        fill={brass}
        variants={{
          initial: { scale: 0 },
          animate: { scale: 1, transition: { ...nodeSpring, delay: 1.18 } },
          hover: { scale: [1, 1.34, 1], transition: { duration: 0.48, delay: 0.24 } },
        }}
        style={{ transformBox: 'fill-box', transformOrigin: 'center' }}
      />
      {showCopilotSpark ? (
        <motion.path
          d="M18.6 2.75L19.2 4.5L20.95 5.1L19.2 5.7L18.6 7.45L18 5.7L16.25 5.1L18 4.5Z"
          fill={brass}
          variants={{
            initial: { scale: 0, rotate: -20 },
            animate: { scale: 1, rotate: 0, transition: { delay: 1.35, duration: 0.28 } },
            hover: { scale: [1, 1.18, 1], rotate: [0, 12, 0], transition: { duration: 0.7 } },
          }}
          style={{ transformBox: 'fill-box', transformOrigin: 'center' }}
        />
      ) : null}
    </svg>
  );
}
