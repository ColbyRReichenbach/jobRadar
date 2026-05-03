import { motion } from 'motion/react';

interface ScoutLogoProps {
  className?: string;
}

const cream = '#F7F1E7';
const sage = '#95AA98';
const brass = '#C89B52';
const draw = { duration: 0.9, ease: 'easeInOut' } as const;
const pop = { type: 'spring', stiffness: 340, damping: 18 } as const;

export function ScoutLogo({ className }: ScoutLogoProps) {
  return (
    <motion.svg
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      initial="initial"
      animate="animate"
      whileHover="hover"
    >
      <motion.circle
        cx="32"
        cy="21"
        r="11"
        stroke={cream}
        strokeWidth="4"
        variants={{
          initial: { pathLength: 0, opacity: 0 },
          animate: { pathLength: 1, opacity: 1, transition: draw },
          hover: { pathLength: [1, 0.28, 1], transition: { duration: 1.2, ease: 'easeInOut' } },
        }}
      />
      <motion.path
        d="M14 45C21 40.8 27 40.8 32 45C37 40.8 43 40.8 50 45V55C43 50.8 37 50.8 32 55C27 50.8 21 50.8 14 55Z"
        stroke={cream}
        strokeWidth="4"
        strokeLinecap="round"
        strokeLinejoin="round"
        variants={{
          initial: { pathLength: 0, opacity: 0 },
          animate: { pathLength: 1, opacity: 1, transition: { ...draw, delay: 0.28 } },
          hover: { pathLength: [1, 0.22, 1], transition: { duration: 1.15, ease: 'easeInOut' } },
        }}
      />
      <motion.path
        d="M32 45V55M20 47H27M37 47H44"
        stroke={cream}
        strokeWidth="3"
        strokeLinecap="round"
        opacity="0.55"
        variants={{
          initial: { pathLength: 0, opacity: 0 },
          animate: { pathLength: 1, opacity: 0.55, transition: { duration: 0.65, delay: 0.58, ease: 'easeOut' } },
          hover: { opacity: [0.55, 0.9, 0.55], transition: { duration: 0.8 } },
        }}
      />
      <motion.path
        d="M39 17C42.2 16.4 44.6 17.2 46.4 19.5"
        stroke={sage}
        strokeWidth="3.5"
        strokeLinecap="round"
        variants={{
          initial: { pathLength: 0, opacity: 0 },
          animate: { pathLength: 1, opacity: 1, transition: { duration: 0.65, delay: 0.78, ease: 'easeOut' } },
          hover: { pathLength: [1, 0, 1], transition: { duration: 0.9, ease: 'easeInOut' } },
        }}
      />
      <motion.circle
        cx="42.5"
        cy="16.2"
        r="3.2"
        fill={brass}
        variants={{
          initial: { scale: 0 },
          animate: { scale: 1, transition: { ...pop, delay: 0.96 } },
          hover: { scale: [1, 1.22, 1], transition: { duration: 0.45 } },
        }}
        style={{ transformBox: 'fill-box', transformOrigin: 'center' }}
      />
    </motion.svg>
  );
}
