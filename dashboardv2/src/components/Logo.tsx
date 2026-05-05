import { motion } from 'motion/react';

interface LogoProps {
  className?: string;
  variant?: 'mark' | 'copilot';
}

export function Logo({ className }: LogoProps) {
  return (
    <motion.svg
      className={`opportunity-radar-logo block overflow-visible ${className || ''}`}
      viewBox="0 0 400 400"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="Opportunity Radar logo"
      whileHover={{ scale: 1.04 }}
      transition={{ type: 'spring', stiffness: 260, damping: 18 }}
    >
      <path d="M120,330 l-15,40 h190 l-15,-40 z" fill="#5C4033" stroke="#2C1E16" strokeWidth="8" strokeLinejoin="round" />
      <path d="M105,370 h190 v12 a12,12 0 0,1 -12,12 h-166 a12,12 0 0,1 -12,-12 z" fill="#2C1E16" />
      <circle cx="200" cy="200" r="160" fill="#BCA37F" stroke="#2C1E16" strokeWidth="10" />
      <circle cx="200" cy="200" r="140" fill="#3E2723" stroke="#2C1E16" strokeWidth="10" />
      <circle cx="200" cy="200" r="95" fill="none" stroke="#D7CCC8" strokeWidth="2" strokeDasharray="8 8" opacity="0.3" />
      <circle cx="200" cy="200" r="50" fill="none" stroke="#D7CCC8" strokeWidth="2" strokeDasharray="4 4" opacity="0.3" />
      <path d="M60,200 h280 M200,60 v280" stroke="#D7CCC8" strokeWidth="2" opacity="0.2" />
      <g className="radar-sweep-group">
        <path d="M200,200 L200,60 A140,140 0 0,1 340,200 Z" fill="#D7CCC8" opacity="0.25" />
        <line x1="200" y1="200" x2="340" y2="200" stroke="#D7CCC8" strokeWidth="5" strokeLinecap="round" />
      </g>
      <g className="blip blip-1">
        <circle cx="280" cy="130" r="22" fill="currentColor" stroke="#2C1E16" strokeWidth="4" />
        <circle cx="277" cy="127" r="6" fill="none" stroke="#FFFFFF" strokeWidth="2.5" />
        <line x1="281.5" y1="131.5" x2="288" y2="138" stroke="#FFFFFF" strokeWidth="3" strokeLinecap="round" />
        <path d="M270,120 Q270,116 266,116 Q270,116 270,112 Q270,116 274,116 Q270,116 270,120 Z" fill="#FFFFFF" />
      </g>
      <g className="blip blip-2">
        <circle cx="270" cy="270" r="22" fill="currentColor" stroke="#2C1E16" strokeWidth="4" />
        <line x1="264" y1="264" x2="276" y2="276" stroke="#FFFFFF" strokeWidth="2.5" />
        <line x1="276" y1="264" x2="264" y2="276" stroke="#FFFFFF" strokeWidth="2.5" />
        <circle cx="264" cy="264" r="3.5" fill="#FFFFFF" />
        <circle cx="276" cy="264" r="3.5" fill="#FFFFFF" />
        <circle cx="276" cy="276" r="3.5" fill="#FFFFFF" />
        <circle cx="264" cy="276" r="3.5" fill="#FFFFFF" />
      </g>
      <g className="blip blip-3">
        <circle cx="130" cy="270" r="22" fill="currentColor" stroke="#2C1E16" strokeWidth="4" />
        <rect x="120" y="261" width="20" height="18" rx="2" fill="none" stroke="#FFFFFF" strokeWidth="2.5" />
        <line x1="120" y1="267" x2="140" y2="267" stroke="#FFFFFF" strokeWidth="2" />
        <circle cx="125" cy="273" r="1.5" fill="#FFFFFF" />
        <circle cx="131" cy="273" r="1.5" fill="#FFFFFF" />
      </g>
      <g className="blip blip-4">
        <circle cx="120" cy="130" r="22" fill="currentColor" stroke="#2C1E16" strokeWidth="4" />
        <path d="M109,124 h22 v14 h-22 z" fill="none" stroke="#FFFFFF" strokeWidth="2.5" strokeLinejoin="round" />
        <path d="M109,124 l11,8 l11,-8" fill="none" stroke="#FFFFFF" strokeWidth="2.5" strokeLinejoin="round" />
        <path d="M125,135 l5,-5 m 3,-3 l2,-2" fill="none" stroke="#FFFFFF" strokeWidth="2.5" strokeLinecap="round" />
        <circle cx="135" cy="120" r="4" fill="#D97706" stroke="#FFFFFF" strokeWidth="1.5" />
      </g>
      <path d="M 60 200 A 140 140 0 0 1 340 200 Q 200 130 60 200 Z" fill="#FFFFFF" opacity="0.06" />
      <g className="center-hub">
        <circle cx="200" cy="200" r="12" fill="#2C1E16" stroke="#D7CCC8" strokeWidth="4" />
        <circle cx="200" cy="200" r="4" fill="#FFFFFF" />
      </g>
    </motion.svg>
  );
}
