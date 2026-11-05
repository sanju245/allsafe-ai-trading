"use client";

import { memo } from "react";

/**
 * Institutional Bull vs Bear Animated Hero Arena.
 *
 * Engineered with pure inline SVG + GPU-accelerated CSS transforms (`transform`, `opacity`)
 * for zero external asset weight, zero CLS, and 60fps smoothness on mid-range Android devices.
 * Strictly discloses zero proprietary indicator names.
 */
function BullBearHeroArena() {
  return (
    <div
      role="img"
      aria-label="Animated quantitative market battle between a bullish emerald bull and a bearish crimson bear across a live candlestick depth grid"
      data-testid="bull-bear-hero-arena"
      className="relative w-full overflow-hidden rounded-2xl border border-white/10 bg-[#070b11] p-4 shadow-[0_24px_80px_rgba(0,0,0,0.75)] sm:p-6"
    >
      {/* Subtle Dual-Side Atmospheric Lighting */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-24 -left-24 h-72 w-72 rounded-full bg-emerald-500/15 blur-3xl"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-24 -bottom-24 h-72 w-72 rounded-full bg-rose-500/15 blur-3xl"
      />

      {/* Top Arena Telemetry Header */}
      <div className="relative z-10 mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-white/10 pb-3 text-[11px]">
        <div className="flex items-center gap-2">
          <span className="inline-flex h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.8)]" />
          <span className="font-mono font-semibold uppercase tracking-wider text-emerald-300">
            BULL REGIME FORCE &middot; BUY DEMAND VECTOR
          </span>
        </div>

        <div className="hidden rounded-full border border-white/10 bg-white/[0.03] px-3 py-0.5 font-mono text-[10px] text-slate-300 sm:inline-block">
          5 AI AGENTS EQUILIBRIUM NEXUS &middot; 5M IST FEED
        </div>

        <div className="flex items-center gap-2">
          <span className="font-mono font-semibold uppercase tracking-wider text-rose-300">
            SELL SUPPLY VECTOR &middot; BEAR REGIME FORCE
          </span>
          <span className="inline-flex h-2 w-2 rounded-full bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.8)]" />
        </div>
      </div>

      {/* Main SVG Battle Stage */}
      <div className="relative z-10 aspect-[16/8] min-h-[220px] w-full sm:min-h-[270px]">
        <svg
          viewBox="0 0 960 440"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className="h-full w-full select-none"
          aria-hidden="true"
        >
          <defs>
            <pattern
              id="quant-grid"
              width="40"
              height="40"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M 40 0 L 0 0 0 40"
                fill="none"
                stroke="rgba(255,255,255,0.035)"
                strokeWidth="1"
              />
            </pattern>

            <linearGradient id="bull-body-grad" x1="60" y1="120" x2="430" y2="360" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#059669" stopOpacity="0.92" />
              <stop offset="55%" stopColor="#10b981" stopOpacity="0.78" />
              <stop offset="100%" stopColor="#047857" stopOpacity="0.35" />
            </linearGradient>

            <linearGradient id="bull-edge-grad" x1="80" y1="90" x2="440" y2="340" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#6ee7b7" />
              <stop offset="60%" stopColor="#10b981" />
              <stop offset="100%" stopColor="#065f46" />
            </linearGradient>

            <radialGradient id="bull-aura" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#10b981" stopOpacity="0.32" />
              <stop offset="100%" stopColor="#10b981" stopOpacity="0" />
            </radialGradient>

            <linearGradient id="bear-body-grad" x1="900" y1="100" x2="520" y2="360" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#e11d48" stopOpacity="0.92" />
              <stop offset="55%" stopColor="#f43f5e" stopOpacity="0.78" />
              <stop offset="100%" stopColor="#881337" stopOpacity="0.35" />
            </linearGradient>

            <linearGradient id="bear-edge-grad" x1="880" y1="80" x2="520" y2="340" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#fda4af" />
              <stop offset="60%" stopColor="#f43f5e" />
              <stop offset="100%" stopColor="#9f1239" />
            </linearGradient>

            <radialGradient id="bear-aura" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#f43f5e" stopOpacity="0.32" />
              <stop offset="100%" stopColor="#f43f5e" stopOpacity="0" />
            </radialGradient>

            <radialGradient id="impact-core" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#f8fafc" stopOpacity="0.95" />
              <stop offset="35%" stopColor="#34d399" stopOpacity="0.55" />
              <stop offset="68%" stopColor="#f43f5e" stopOpacity="0.35" />
              <stop offset="100%" stopColor="#0f172a" stopOpacity="0" />
            </radialGradient>
          </defs>

          <rect width="960" height="440" fill="url(#quant-grid)" />

          <line
            x1="20"
            y1="370"
            x2="940"
            y2="370"
            stroke="rgba(255,255,255,0.12)"
            strokeWidth="1.5"
          />
          <line
            x1="80"
            y1="395"
            x2="880"
            y2="395"
            stroke="rgba(255,255,255,0.05)"
            strokeWidth="1"
            strokeDasharray="6 8"
          />

          <g opacity="0.45">
            <g stroke="#10b981" strokeWidth="1.5">
              <line x1="70" y1="310" x2="70" y2="355" />
              <rect x="64" y="322" width="12" height="22" fill="#059669" rx="1.5" />

              <line x1="105" y1="285" x2="105" y2="335" />
              <rect x="99" y="295" width="12" height="28" fill="#10b981" rx="1.5" />

              <line x1="140" y1="260" x2="140" y2="312" />
              <rect x="134" y="270" width="12" height="30" fill="#10b981" rx="1.5" />

              <line x1="175" y1="230" x2="175" y2="285" />
              <rect x="169" y="242" width="12" height="28" fill="#34d399" rx="1.5" />
            </g>

            <g stroke="#f43f5e" strokeWidth="1.5">
              <line x1="890" y1="305" x2="890" y2="352" />
              <rect x="884" y="318" width="12" height="24" fill="#be123c" rx="1.5" />

              <line x1="855" y1="278" x2="855" y2="332" />
              <rect x="849" y="290" width="12" height="28" fill="#e11d48" rx="1.5" />

              <line x1="820" y1="252" x2="820" y2="306" />
              <rect x="814" y="262" width="12" height="30" fill="#f43f5e" rx="1.5" />

              <line x1="785" y1="224" x2="785" y2="280" />
              <rect x="779" y="236" width="12" height="28" fill="#fb7185" rx="1.5" />
            </g>

            <path
              d="M 40 340 Q 160 280, 270 250 T 480 225 T 690 250 T 920 340"
              stroke="rgba(148,163,184,0.28)"
              strokeWidth="1.5"
              strokeDasharray="4 6"
              fill="none"
            />
          </g>

          <circle cx="275" cy="245" r="165" fill="url(#bull-aura)" className="arena-aura-pulse" />
          <circle cx="685" cy="245" r="165" fill="url(#bear-aura)" className="arena-aura-pulse" />

          {/* LEFT: POWERFUL QUANTITATIVE BULL */}
          <g className="bull-fighter-group">
            <ellipse cx="220" cy="370" rx="145" ry="12" fill="rgba(16,185,129,0.18)" />
            <path
              d="M 55 362 Q 130 348, 205 366"
              stroke="#34d399"
              strokeWidth="2"
              strokeLinecap="round"
              opacity="0.55"
              className="arena-shockwave-left"
            />

            <path
              d="M 88 225 Q 52 200, 44 162 Q 56 172, 68 192"
              stroke="#34d399"
              strokeWidth="3"
              strokeLinecap="round"
              fill="none"
            />

            <polygon
              points="92,218 168,184 195,264 134,306 96,366 78,366 105,292"
              fill="url(#bull-body-grad)"
              stroke="url(#bull-edge-grad)"
              strokeWidth="2"
              strokeLinejoin="round"
            />
            <polygon
              points="134,306 162,286 156,366 138,366"
              fill="#065f46"
              stroke="#34d399"
              strokeWidth="1.5"
            />

            <polygon
              points="158,184 268,136 356,168 342,272 238,288 175,264"
              fill="url(#bull-body-grad)"
              stroke="url(#bull-edge-grad)"
              strokeWidth="2.2"
              strokeLinejoin="round"
            />

            <polyline
              points="168,184 238,225 268,136 312,218 356,168"
              stroke="rgba(167,243,208,0.45)"
              strokeWidth="1.4"
              fill="none"
            />
            <polyline
              points="175,264 238,225 312,218 342,272 238,288 238,225"
              stroke="rgba(167,243,208,0.35)"
              strokeWidth="1.2"
              fill="none"
            />

            <polygon
              points="286,268 326,258 368,318 338,366 318,366 342,320"
              fill="#059669"
              stroke="#6ee7b7"
              strokeWidth="2"
              strokeLinejoin="round"
            />
            <polygon
              points="324,254 358,248 412,306 392,352 372,344 388,308"
              fill="url(#bull-body-grad)"
              stroke="#6ee7b7"
              strokeWidth="2"
              strokeLinejoin="round"
            />

            <polygon
              points="348,162 418,176 446,228 412,256 342,244"
              fill="url(#bull-body-grad)"
              stroke="#6ee7b7"
              strokeWidth="2.4"
              strokeLinejoin="round"
            />
            <polyline
              points="348,162 392,208 446,228"
              stroke="rgba(167,243,208,0.5)"
              strokeWidth="1.4"
              fill="none"
            />

            <polygon
              points="398,196 414,198 408,208 394,204"
              fill="#ecfdf5"
              stroke="#34d399"
              strokeWidth="1.5"
            />

            <polygon
              points="376,168 412,132 468,116 432,158 396,176"
              fill="#a7f3d0"
              stroke="#ecfdf5"
              strokeWidth="1.8"
              strokeLinejoin="round"
            />
            <polygon
              points="362,176 392,148 442,138 412,166"
              fill="#34d399"
              stroke="#a7f3d0"
              strokeWidth="1.4"
              opacity="0.85"
            />

            <path
              d="M 444 234 Q 465 230, 474 216"
              stroke="#6ee7b7"
              strokeWidth="2.2"
              strokeLinecap="round"
              opacity="0.85"
            />
          </g>

          {/* RIGHT: FORMIDABLE QUANTITATIVE BEAR */}
          <g className="bear-fighter-group">
            <ellipse cx="740" cy="370" rx="145" ry="12" fill="rgba(244,63,94,0.18)" />
            <path
              d="M 905 362 Q 830 348, 755 366"
              stroke="#fb7185"
              strokeWidth="2"
              strokeLinecap="round"
              opacity="0.55"
              className="arena-shockwave-right"
            />

            <polygon
              points="872,226 798,166 756,262 818,308 858,366 882,366 854,292"
              fill="url(#bear-body-grad)"
              stroke="url(#bear-edge-grad)"
              strokeWidth="2"
              strokeLinejoin="round"
            />
            <polygon
              points="818,308 784,286 792,366 814,366"
              fill="#881337"
              stroke="#fb7185"
              strokeWidth="1.5"
            />

            <polygon
              points="804,166 686,118 598,154 612,268 724,288 786,262"
              fill="url(#bear-body-grad)"
              stroke="url(#bear-edge-grad)"
              strokeWidth="2.2"
              strokeLinejoin="round"
            />

            <polyline
              points="798,166 720,218 686,118 642,212 598,154"
              stroke="rgba(254,205,211,0.45)"
              strokeWidth="1.4"
              fill="none"
            />
            <polyline
              points="786,262 720,218 642,212 612,268 724,288 720,218"
              stroke="rgba(254,205,211,0.35)"
              strokeWidth="1.2"
              fill="none"
            />

            <polygon
              points="664,262 628,254 596,366 624,366 648,304"
              fill="#be123c"
              stroke="#fda4af"
              strokeWidth="2"
              strokeLinejoin="round"
            />

            <polygon
              points="622,216 564,196 518,228 538,266 598,258"
              fill="url(#bear-body-grad)"
              stroke="#fda4af"
              strokeWidth="2.2"
              strokeLinejoin="round"
            />
            <g stroke="#ffe4e6" strokeWidth="2.4" strokeLinecap="round">
              <line x1="518" y1="222" x2="494" y2="214" />
              <line x1="516" y1="234" x2="490" y2="230" />
              <line x1="520" y1="246" x2="496" y2="246" />
            </g>

            <polygon
              points="612,138 588,114 568,128 576,148"
              fill="#9f1239"
              stroke="#fda4af"
              strokeWidth="1.8"
            />
            <polygon
              points="608,144 536,154 508,188 534,212 562,210 532,226 576,236 614,214"
              fill="url(#bear-body-grad)"
              stroke="#fda4af"
              strokeWidth="2.4"
              strokeLinejoin="round"
            />

            <polygon
              points="564,168 548,172 554,180 568,176"
              fill="#fff1f2"
              stroke="#fb7185"
              strokeWidth="1.5"
            />

            <polygon points="518,192 524,204 530,194" fill="#fff1f2" />
            <polygon points="536,222 542,212 548,224" fill="#fff1f2" />
          </g>

          {/* CENTER: MARKET CLASH NEXUS */}
          <g className="clash-core-group">
            <line
              x1="480"
              y1="65"
              x2="480"
              y2="370"
              stroke="rgba(255,255,255,0.16)"
              strokeWidth="1.5"
              strokeDasharray="3 6"
            />

            <circle
              cx="480"
              cy="205"
              r="34"
              stroke="#34d399"
              strokeWidth="1.8"
              opacity="0.6"
              className="clash-ring-outer"
            />
            <circle
              cx="480"
              cy="205"
              r="22"
              stroke="#fb7185"
              strokeWidth="1.8"
              opacity="0.7"
              className="clash-ring-inner"
            />

            <circle cx="480" cy="205" r="28" fill="url(#impact-core)" />

            <path
              d="M 454 162 L 478 202 L 462 214 L 504 252"
              stroke="#e2e8f0"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity="0.85"
            />
            <path
              d="M 502 158 L 482 202 L 496 212 L 456 254"
              stroke="#6ee7b7"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity="0.75"
            />
          </g>

          <g className="arena-particles">
            <circle cx="430" cy="140" r="2.5" fill="#34d399" opacity="0.8" />
            <circle cx="450" cy="285" r="2" fill="#6ee7b7" opacity="0.7" />
            <circle cx="380" cy="120" r="1.8" fill="#10b981" opacity="0.6" />
            <circle cx="530" cy="135" r="2.5" fill="#fb7185" opacity="0.8" />
            <circle cx="515" cy="280" r="2" fill="#fda4af" opacity="0.7" />
            <circle cx="585" cy="118" r="1.8" fill="#f43f5e" opacity="0.6" />
            <circle cx="480" cy="112" r="2.2" fill="#f8fafc" opacity="0.75" />
            <circle cx="480" cy="312" r="2.2" fill="#f8fafc" opacity="0.65" />
          </g>
        </svg>
      </div>

      {/* Bottom 5-Agent Consensus Strip (Zero Indicator Names Disclosed) */}
      <div className="relative z-10 mt-3 grid grid-cols-3 gap-2 border-t border-white/10 pt-3 text-[11px] tabular-nums">
        <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/[0.06] px-3 py-2">
          <div className="text-[10px] font-medium uppercase tracking-wider text-emerald-300">
            Bullish Buy Consensus
          </div>
          <div className="mt-0.5 font-mono text-xs font-bold text-white sm:text-sm">
            5 / 5 AI Agents Bullish
          </div>
        </div>

        <div className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-center">
          <div className="text-[10px] font-medium uppercase tracking-wider text-slate-400">
            Decision Gate
          </div>
          <div className="mt-0.5 font-mono text-xs font-bold text-slate-200 sm:text-sm">
            Unanimous 5-Agent Lock
          </div>
        </div>

        <div className="rounded-lg border border-rose-500/20 bg-rose-500/[0.06] px-3 py-2 text-right">
          <div className="text-[10px] font-medium uppercase tracking-wider text-rose-300">
            Bearish Sell Consensus
          </div>
          <div className="mt-0.5 font-mono text-xs font-bold text-white sm:text-sm">
            5 / 5 AI Agents Bearish
          </div>
        </div>
      </div>
    </div>
  );
}

export default memo(BullBearHeroArena);
