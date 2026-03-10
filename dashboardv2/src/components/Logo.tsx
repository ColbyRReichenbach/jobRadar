import { motion } from 'motion/react';

export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
      {/* Main Trail (The 'A' shape) */}
      <motion.path
        d="M4 20L12 4L20 20"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        variants={{
          initial: { pathLength: 0 },
          animate: { pathLength: 1, transition: { duration: 1.2, ease: "easeInOut" } },
          hover: { pathLength: [1, 0, 1], transition: { duration: 1.5, ease: "easeInOut" } }
        }}
      />
      {/* The Trail Crossbar */}
      <motion.path
        d="M8 13H16"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeDasharray="4 4"
        variants={{
          initial: { pathLength: 0, opacity: 0 },
          animate: { pathLength: 1, opacity: 1, transition: { duration: 0.6, delay: 1.0, ease: "easeOut" } },
          hover: { pathLength: [1, 0, 1], opacity: [1, 0, 1], transition: { duration: 1.5, ease: "easeInOut" } }
        }}
      />
      {/* Waypoint Nodes */}
      <motion.circle
        cx="12" cy="4" r="2.5"
        fill="white"
        stroke="currentColor"
        strokeWidth="2"
        variants={{
          initial: { scale: 0 },
          animate: { scale: 1, transition: { delay: 0.6, type: "spring", stiffness: 300 } },
          hover: { scale: [1, 1.4, 1], transition: { duration: 0.5, delay: 0.75 } }
        }}
      />
      <motion.circle
        cx="4" cy="20" r="2.5"
        fill="white"
        stroke="currentColor"
        strokeWidth="2"
        variants={{
          initial: { scale: 0 },
          animate: { scale: 1, transition: { delay: 0.1, type: "spring", stiffness: 300 } },
          hover: { scale: [1, 1.4, 1], transition: { duration: 0.5, delay: 0 } }
        }}
      />
      <motion.circle
        cx="20" cy="20" r="2.5"
        fill="white"
        stroke="currentColor"
        strokeWidth="2"
        variants={{
          initial: { scale: 0 },
          animate: { scale: 1, transition: { delay: 1.2, type: "spring", stiffness: 300 } },
          hover: { scale: [1, 1.4, 1], transition: { duration: 0.5, delay: 1.5 } }
        }}
      />
    </svg>
  );
}
