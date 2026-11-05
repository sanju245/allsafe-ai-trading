"use client";

import { memo, useEffect, useState } from "react";
import {
  getIstClockSnapshot,
  type IstClockSnapshot,
} from "@/lib/indianMarketStatus";

export interface LiveIstClockProps {
  /** Optional server-clock offset in milliseconds (serverUtcMs - clientUtcMs) */
  serverTimeOffsetMs?: number;
  /** Optional initial epoch timestamp (ms) for deterministic SSR / test hydration */
  initialEpochMs?: number;
  /** Visual variant: "hero" (prominent terminal card) or "compact" (navbar pill) */
  variant?: "hero" | "compact";
  /** Optional CSS class names */
  className?: string;
}

/**
 * Isolated, lightweight Live Indian Standard Time (IST / Asia/Kolkata) Digital Clock.
 * Updates once per second inside its own leaf component state so ticking never
 * causes rerenders of the parent landing page or sibling sections.
 */
function LiveIstClock({
  serverTimeOffsetMs = 0,
  initialEpochMs,
  variant = "hero",
  className = "",
}: LiveIstClockProps) {
  const [snapshot, setSnapshot] = useState<IstClockSnapshot | null>(() =>
    initialEpochMs !== undefined
      ? getIstClockSnapshot(initialEpochMs, serverTimeOffsetMs)
      : null,
  );

  useEffect(() => {
    const updateClock = () => {
      setSnapshot(getIstClockSnapshot(Date.now(), serverTimeOffsetMs));
    };

    updateClock();
    const intervalId = window.setInterval(updateClock, 1000);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [serverTimeOffsetMs]);

  if (variant === "compact") {
    return (
      <div
        role="timer"
        aria-label="Live Indian Standard Time (Asia/Kolkata)"
        className={`inline-flex items-center gap-2 rounded-lg border border-white/10 bg-slate-950/80 px-2.5 py-1 text-[11px] text-slate-300 tabular-nums ${className}`}
      >
        <span className="font-mono font-semibold text-emerald-300">
          {snapshot ? snapshot.time12hWithZone : "—:—:— IST"}
        </span>
      </div>
    );
  }

  return (
    <div
      role="timer"
      aria-label="Live Indian Standard Time (IST - Asia/Kolkata)"
      className={`flex flex-col justify-between rounded-xl border border-white/10 bg-[#0b1018]/90 px-4 py-3 shadow-inner backdrop-blur-md ${className}`}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">
          Indian Standard Time &middot; Asia/Kolkata
        </span>
        <span className="rounded border border-emerald-500/25 bg-emerald-500/10 px-1.5 py-0.5 font-mono text-[10px] font-medium text-emerald-300">
          UTC+05:30
        </span>
      </div>

      <div
        data-testid="ist-clock-time"
        className="mt-1.5 font-mono text-xl font-bold tracking-wider text-white tabular-nums sm:text-2xl"
      >
        {snapshot ? snapshot.time12hWithZone : "05:30:00 AM IST"}
      </div>

      <div
        data-testid="ist-clock-date"
        className="mt-1 font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-slate-300 tabular-nums"
      >
        {snapshot ? snapshot.dateHeadingUppercase : "SYNCHRONIZING ASIA/KOLKATA CLOCK..."}
      </div>
    </div>
  );
}

export default memo(LiveIstClock);
