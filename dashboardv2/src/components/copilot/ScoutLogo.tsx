interface ScoutLogoProps {
  className?: string;
}

const scoutStyles = `
  @keyframes scout-float {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-8px); }
  }

  @keyframes scout-thruster {
    0%, 100% { opacity: 0.8; transform: scale(1); }
    50% { opacity: 1; transform: scale(1.2); }
  }

  .scout-logo {
    transition: transform 0.3s ease;
  }

  .scout-logo:hover {
    transform: scale(1.05);
  }

  .scout-logo .scout-float {
    animation: scout-float 4s ease-in-out infinite;
  }

  .scout-logo .scout-thruster {
    animation: scout-thruster 2s ease-in-out infinite;
    transform-origin: 200px 300px;
  }

  .scout-logo .scout-eye {
    transition: transform 0.28s ease, fill 0.28s ease;
    transform-origin: center;
  }

  .scout-logo:hover .scout-eye {
    transform: translateY(-3px) scale(1.12);
    fill: #A5D6A7;
  }

  .scout-logo .scout-cheek {
    transform: scale(0);
    transform-origin: center;
    transition: transform 0.2s ease;
  }

  .scout-logo:hover .scout-cheek {
    transform: scale(1);
  }

  .scout-logo .scout-left-arm,
  .scout-logo .scout-left-hand,
  .scout-logo .scout-right-arm,
  .scout-logo .scout-right-hand {
    transition: transform 0.45s cubic-bezier(0.22, 1, 0.36, 1);
  }

  .scout-logo:hover .scout-left-arm,
  .scout-logo:hover .scout-left-hand {
    transform: translateX(-44px);
  }

  .scout-logo:hover .scout-right-arm,
  .scout-logo:hover .scout-right-hand {
    transform: translateX(44px);
  }

  .scout-logo .scout-particles {
    opacity: 0;
    transform: translateY(90px) scale(0.5);
    transform-origin: 200px 180px;
    transition: opacity 0.24s ease, transform 0.42s cubic-bezier(0.22, 1, 0.36, 1);
  }

  .scout-logo:hover .scout-particles {
    opacity: 1;
    transform: translateY(0) scale(1);
  }

  .scout-logo .scout-spine,
  .scout-logo .scout-front-spine {
    opacity: 0;
    transition: opacity 0.2s ease;
  }

  .scout-logo:hover .scout-spine,
  .scout-logo:hover .scout-front-spine {
    opacity: 1;
  }

  .scout-logo .scout-page {
    transform: scaleX(0);
    transition: transform 0.45s cubic-bezier(0.22, 1, 0.36, 1);
  }

  .scout-logo .scout-left-page {
    transform-origin: 195px 240px;
  }

  .scout-logo .scout-right-page {
    transform-origin: 205px 240px;
  }

  .scout-logo:hover .scout-page {
    transform: scaleX(1);
  }

  .scout-logo .scout-cover {
    opacity: 1;
    transform: scaleX(1);
    transform-origin: 200px 240px;
    transition: opacity 0.22s ease, transform 0.34s cubic-bezier(0.22, 1, 0.36, 1);
  }

  .scout-logo:hover .scout-cover {
    opacity: 0;
    transform: scaleX(0);
  }
`;

export function ScoutLogo({ className = '' }: ScoutLogoProps) {
  return (
    <svg
      viewBox="0 0 400 400"
      className={`scout-logo block overflow-visible drop-shadow-xl ${className}`}
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      focusable="false"
    >
      <style>{scoutStyles}</style>
      <g stroke="#EFEBE9" fill="none" strokeWidth="4" strokeDasharray="10 15" strokeLinecap="round">
        <circle cx="200" cy="200" r="180" />
        <circle cx="200" cy="200" r="130" />
        <circle cx="200" cy="200" r="80" />
      </g>

      <ellipse cx="200" cy="365" rx="80" ry="12" fill="#D7CCC8" opacity="0.6" />

      <g className="scout-float">
        <path d="M 160 280 Q 200 330 240 280 Z" fill="#8D6E63" stroke="#3E2723" strokeWidth="8" strokeLinejoin="round" />
        <ellipse className="scout-thruster" cx="200" cy="300" rx="15" ry="6" fill="#FFB300" />

        <rect x="120" y="160" width="160" height="130" rx="45" fill="#FFF3E0" stroke="#3E2723" strokeWidth="8" />
        <path d="M 120 220 Q 200 240 280 220" fill="none" stroke="#D7CCC8" strokeWidth="4" />
        <circle cx="200" cy="250" r="12" fill="#FFFBEB" stroke="#3E2723" strokeWidth="6" />

        <rect x="140" y="145" width="120" height="40" rx="20" fill="#388E3C" stroke="#1B5E20" strokeWidth="8" />
        <path d="M 160 155 L 240 155" stroke="#81C784" strokeWidth="6" strokeLinecap="round" />

        <rect x="90" y="50" width="220" height="120" rx="45" fill="#FAFAFA" stroke="#3E2723" strokeWidth="8" />
        <path d="M 94 85 Q 200 -10 306 85 Z" fill="#F9A825" stroke="#3E2723" strokeWidth="8" />
        <circle cx="200" cy="15" r="16" fill="#FFF3E0" stroke="#3E2723" strokeWidth="6" />

        <rect x="110" y="70" width="180" height="85" rx="25" fill="#2D201C" stroke="#3E2723" strokeWidth="8" />
        <rect x="120" y="80" width="65" height="45" rx="12" fill="none" stroke="#F5F5F5" strokeWidth="6" />
        <rect x="215" y="80" width="65" height="45" rx="12" fill="none" stroke="#F5F5F5" strokeWidth="6" />
        <path d="M 185 102 L 215 102" stroke="#F5F5F5" strokeWidth="6" />

        <ellipse className="scout-eye" cx="152" cy="102" rx="12" ry="18" fill="#81C784" />
        <ellipse className="scout-eye" cx="248" cy="102" rx="12" ry="18" fill="#81C784" />
        <ellipse className="scout-cheek" cx="128" cy="115" rx="8" ry="4" fill="#FF8A65" opacity="0.8" />
        <ellipse className="scout-cheek" cx="272" cy="115" rx="8" ry="4" fill="#FF8A65" opacity="0.8" />

        <g className="scout-left-arm">
          <path d="M 130 200 Q 120 250 147 295" fill="none" stroke="#3E2723" strokeWidth="24" strokeLinecap="round" />
          <path d="M 130 200 Q 120 250 147 295" fill="none" stroke="#FFF3E0" strokeWidth="12" strokeLinecap="round" />
        </g>
        <g className="scout-right-arm">
          <path d="M 270 200 Q 280 250 252 295" fill="none" stroke="#3E2723" strokeWidth="24" strokeLinecap="round" />
          <path d="M 270 200 Q 280 250 252 295" fill="none" stroke="#FFF3E0" strokeWidth="12" strokeLinecap="round" />
        </g>

        <rect className="scout-left-hand" x="135" y="285" width="25" height="25" rx="10" fill="#FFF3E0" stroke="#3E2723" strokeWidth="6" />
        <rect className="scout-right-hand" x="240" y="285" width="25" height="25" rx="10" fill="#FFF3E0" stroke="#3E2723" strokeWidth="6" />

        <g className="scout-particles">
          <path d="M 200 150 L 206 165 L 222 168 L 208 176 L 214 190 L 200 182 L 186 190 L 192 176 L 178 168 L 194 165 Z" fill="#FFB300" stroke="#3E2723" strokeWidth="4" strokeLinejoin="round" />
          <circle cx="160" cy="140" r="9" fill="#FF8A65" stroke="#3E2723" strokeWidth="4" />
          <circle cx="240" cy="130" r="7" fill="#81C784" stroke="#3E2723" strokeWidth="3" />
        </g>

        <g>
          <rect className="scout-spine" x="185" y="170" width="30" height="140" rx="4" fill="#5D4037" stroke="#3E2723" strokeWidth="6" />
          <g className="scout-page scout-left-page">
            <rect x="100" y="170" width="100" height="140" rx="4" fill="#FFFBEB" stroke="#3E2723" strokeWidth="6" />
            <path d="M 115 190 L 180 190 M 115 210 L 170 210 M 115 230 L 180 230 M 115 250 L 160 250 M 115 270 L 180 270 M 115 290 L 150 290" stroke="#D7CCC8" strokeWidth="4" strokeLinecap="round" />
          </g>
          <g className="scout-page scout-right-page">
            <rect x="200" y="170" width="100" height="140" rx="4" fill="#FFFBEB" stroke="#3E2723" strokeWidth="6" />
            <path d="M 220 190 L 285 190 M 220 210 L 275 210 M 220 230 L 285 230 M 220 250 L 260 250 M 220 270 L 285 270 M 220 290 L 270 290" stroke="#D7CCC8" strokeWidth="4" strokeLinecap="round" />
          </g>
          <path className="scout-front-spine" d="M 200 170 L 200 310" stroke="#3E2723" strokeWidth="6" strokeLinecap="round" />
          <g className="scout-cover">
            <rect x="150" y="170" width="100" height="140" rx="6" fill="#8D6E63" stroke="#3E2723" strokeWidth="6" />
            <rect x="160" y="185" width="80" height="110" rx="3" fill="none" stroke="#A1887F" strokeWidth="3" />
            <path d="M 175 210 L 225 210 M 175 230 L 200 230" stroke="#FFF3E0" strokeWidth="6" strokeLinecap="round" />
          </g>
        </g>
      </g>
    </svg>
  );
}
