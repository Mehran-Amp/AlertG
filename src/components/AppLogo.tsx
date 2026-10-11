import React from 'react';

interface AppLogoProps {
  className?: string;
  size?: number | string;
  withBackground?: boolean;
  withGlow?: boolean;
}

export const AppLogo: React.FC<AppLogoProps> = ({
  className = 'h-10 w-10',
  size,
  withBackground = true,
  withGlow = true,
}) => {
  const style = size ? { width: size, height: size } : undefined;

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 1000 1000"
      className={`shrink-0 select-none ${className}`}
      style={style}
      aria-label="Market Alarmer Logo"
    >
      <defs>
        {/* Background Gradient */}
        <linearGradient id="appLogoBg" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#181d28" />
          <stop offset="50%" stopColor="#10131a" />
          <stop offset="100%" stopColor="#0a0c10" />
        </linearGradient>

        {/* Neon Green Gradient */}
        <linearGradient id="neonGreenGrad" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#4ade80" />
          <stop offset="50%" stopColor="#00e676" />
          <stop offset="100%" stopColor="#16a34a" />
        </linearGradient>

        {/* Neon Red Gradient */}
        <linearGradient id="neonRedGrad" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#ff4d6d" />
          <stop offset="50%" stopColor="#ff1744" />
          <stop offset="100%" stopColor="#dc2626" />
        </linearGradient>

        {/* Radar Arcs Gradients */}
        <linearGradient id="arc1GradReact" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#fb7185" />
          <stop offset="100%" stopColor="#f43f5e" />
        </linearGradient>

        <linearGradient id="arc2GradReact" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#fdba74" />
          <stop offset="100%" stopColor="#ea580c" />
        </linearGradient>

        <linearGradient id="arc3GradReact" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#fde047" />
          <stop offset="100%" stopColor="#d97706" />
        </linearGradient>

        <linearGradient id="arc4GradReact" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#fef08a" />
          <stop offset="100%" stopColor="#ca8a04" />
        </linearGradient>

        {/* Center Orb Gradient */}
        <radialGradient id="orbGradReact" cx="35%" cy="35%" r="65%">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="30%" stopColor="#fde047" />
          <stop offset="70%" stopColor="#f59e0b" />
          <stop offset="100%" stopColor="#c2410c" />
        </radialGradient>

        {withGlow && (
          <>
            <filter id="glowGreenFilter" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="8" result="blur1" />
              <feGaussianBlur stdDeviation="18" result="blur2" />
              <feMerge>
                <feMergeNode in="blur2" />
                <feMergeNode in="blur1" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>

            <filter id="glowRedFilter" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="8" result="blur1" />
              <feGaussianBlur stdDeviation="18" result="blur2" />
              <feMerge>
                <feMergeNode in="blur2" />
                <feMergeNode in="blur1" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>

            <filter id="glowWarmFilter" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="10" result="blur1" />
              <feGaussianBlur stdDeviation="22" result="blur2" />
              <feMerge>
                <feMergeNode in="blur2" />
                <feMergeNode in="blur1" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </>
        )}
      </defs>

      {/* Dark Slate Rounded Backdrop */}
      {withBackground && (
        <>
          <rect width="1000" height="1000" rx="200" fill="url(#appLogoBg)" />
          <rect
            width="992"
            height="992"
            x="4"
            y="4"
            rx="196"
            fill="none"
            stroke="#ffffff"
            strokeOpacity="0.08"
            strokeWidth="4"
          />
        </>
      )}

      {/* Radar / Alert Arcs */}
      <g filter={withGlow ? 'url(#glowWarmFilter)' : undefined}>
        {/* Arc 4 (Outer Gold) */}
        <path
          d="M 595 144 A 304 304 0 0 1 899 448"
          fill="none"
          stroke="url(#arc4GradReact)"
          strokeWidth="26"
          strokeLinecap="round"
        />
        <path
          d="M 595 144 A 304 304 0 0 1 899 448"
          fill="none"
          stroke="#ffffff"
          strokeOpacity="0.35"
          strokeWidth="6"
          strokeLinecap="round"
        />

        {/* Arc 3 (Amber) */}
        <path
          d="M 595 220 A 228 228 0 0 1 823 448"
          fill="none"
          stroke="url(#arc3GradReact)"
          strokeWidth="26"
          strokeLinecap="round"
        />
        <path
          d="M 595 220 A 228 228 0 0 1 823 448"
          fill="none"
          stroke="#ffffff"
          strokeOpacity="0.35"
          strokeWidth="6"
          strokeLinecap="round"
        />

        {/* Arc 2 (Orange) */}
        <path
          d="M 595 296 A 152 152 0 0 1 747 448"
          fill="none"
          stroke="url(#arc2GradReact)"
          strokeWidth="26"
          strokeLinecap="round"
        />
        <path
          d="M 595 296 A 152 152 0 0 1 747 448"
          fill="none"
          stroke="#ffffff"
          strokeOpacity="0.35"
          strokeWidth="6"
          strokeLinecap="round"
        />

        {/* Arc 1 (Coral) */}
        <path
          d="M 595 370 A 78 78 0 0 1 673 448"
          fill="none"
          stroke="url(#arc1GradReact)"
          strokeWidth="26"
          strokeLinecap="round"
        />
        <path
          d="M 595 370 A 78 78 0 0 1 673 448"
          fill="none"
          stroke="#ffffff"
          strokeOpacity="0.35"
          strokeWidth="6"
          strokeLinecap="round"
        />

        {/* Glowing Central Orb */}
        <circle cx="595" cy="448" r="30" fill="url(#orbGradReact)" />
        <circle cx="586" cy="439" r="8" fill="#ffffff" fillOpacity="0.75" />
      </g>

      {/* Candlesticks */}
      {/* Candle 1: Red */}
      <g filter={withGlow ? 'url(#glowRedFilter)' : undefined}>
        <line x1="135" y1="490" x2="135" y2="545" stroke="url(#neonRedGrad)" strokeWidth="14" strokeLinecap="round" />
        <line x1="135" y1="715" x2="135" y2="770" stroke="url(#neonRedGrad)" strokeWidth="14" strokeLinecap="round" />
        <rect
          x="103"
          y="545"
          width="64"
          height="170"
          rx="30"
          fill="#ff1744"
          fillOpacity="0.12"
          stroke="url(#neonRedGrad)"
          strokeWidth="14"
        />
        <rect
          x="107"
          y="549"
          width="56"
          height="162"
          rx="26"
          fill="none"
          stroke="#ffffff"
          strokeOpacity="0.25"
          strokeWidth="3"
        />
      </g>

      {/* Candle 2: Green */}
      <g filter={withGlow ? 'url(#glowGreenFilter)' : undefined}>
        <line x1="232" y1="370" x2="232" y2="460" stroke="url(#neonGreenGrad)" strokeWidth="14" strokeLinecap="round" />
        <line x1="232" y1="670" x2="232" y2="750" stroke="url(#neonGreenGrad)" strokeWidth="14" strokeLinecap="round" />
        <rect
          x="200"
          y="460"
          width="64"
          height="210"
          rx="30"
          fill="#00e676"
          fillOpacity="0.12"
          stroke="url(#neonGreenGrad)"
          strokeWidth="14"
        />
        <rect
          x="204"
          y="464"
          width="56"
          height="202"
          rx="26"
          fill="none"
          stroke="#ffffff"
          strokeOpacity="0.25"
          strokeWidth="3"
        />
      </g>

      {/* Candle 3: Green */}
      <g filter={withGlow ? 'url(#glowGreenFilter)' : undefined}>
        <line x1="328" y1="370" x2="328" y2="445" stroke="url(#neonGreenGrad)" strokeWidth="14" strokeLinecap="round" />
        <line x1="328" y1="605" x2="328" y2="660" stroke="url(#neonGreenGrad)" strokeWidth="14" strokeLinecap="round" />
        <rect
          x="296"
          y="445"
          width="64"
          height="160"
          rx="30"
          fill="#00e676"
          fillOpacity="0.12"
          stroke="url(#neonGreenGrad)"
          strokeWidth="14"
        />
        <rect
          x="300"
          y="449"
          width="56"
          height="152"
          rx="26"
          fill="none"
          stroke="#ffffff"
          strokeOpacity="0.25"
          strokeWidth="3"
        />
      </g>

      {/* Candle 4: Peak Green */}
      <g filter={withGlow ? 'url(#glowGreenFilter)' : undefined}>
        <line x1="425" y1="210" x2="425" y2="310" stroke="url(#neonGreenGrad)" strokeWidth="14" strokeLinecap="round" />
        <line x1="425" y1="550" x2="425" y2="615" stroke="url(#neonGreenGrad)" strokeWidth="14" strokeLinecap="round" />
        <rect
          x="393"
          y="310"
          width="64"
          height="240"
          rx="30"
          fill="#00e676"
          fillOpacity="0.12"
          stroke="url(#neonGreenGrad)"
          strokeWidth="14"
        />
        <rect
          x="397"
          y="314"
          width="56"
          height="232"
          rx="26"
          fill="none"
          stroke="#ffffff"
          strokeOpacity="0.25"
          strokeWidth="3"
        />
      </g>

      {/* Candle 5: Red */}
      <g filter={withGlow ? 'url(#glowRedFilter)' : undefined}>
        <line x1="518" y1="425" x2="518" y2="542" stroke="url(#neonRedGrad)" strokeWidth="14" strokeLinecap="round" />
        <line x1="518" y1="767" x2="518" y2="820" stroke="url(#neonRedGrad)" strokeWidth="14" strokeLinecap="round" />
        <rect
          x="486"
          y="542"
          width="64"
          height="225"
          rx="30"
          fill="#ff1744"
          fillOpacity="0.12"
          stroke="url(#neonRedGrad)"
          strokeWidth="14"
        />
        <rect
          x="490"
          y="546"
          width="56"
          height="217"
          rx="26"
          fill="none"
          stroke="#ffffff"
          strokeOpacity="0.25"
          strokeWidth="3"
        />
      </g>

      {/* Candle 6: Red */}
      <g filter={withGlow ? 'url(#glowRedFilter)' : undefined}>
        <line x1="612" y1="550" x2="612" y2="620" stroke="url(#neonRedGrad)" strokeWidth="14" strokeLinecap="round" />
        <line x1="612" y1="710" x2="612" y2="780" stroke="url(#neonRedGrad)" strokeWidth="14" strokeLinecap="round" />
        <rect
          x="580"
          y="620"
          width="64"
          height="90"
          rx="30"
          fill="#ff1744"
          fillOpacity="0.12"
          stroke="url(#neonRedGrad)"
          strokeWidth="14"
        />
        <rect
          x="584"
          y="624"
          width="56"
          height="82"
          rx="26"
          fill="none"
          stroke="#ffffff"
          strokeOpacity="0.25"
          strokeWidth="3"
        />
      </g>
    </svg>
  );
};
