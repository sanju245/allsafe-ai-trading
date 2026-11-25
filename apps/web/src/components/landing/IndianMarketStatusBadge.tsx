"use client";

import { memo, useEffect, useState } from "react";
import {
  evaluateIndianMarketStatus,
  type IndianMarketStatusResult,
  type MarketCalendar,
} from "@/lib/indianMarketStatus";

export interface IndianMarketStatusBadgeProps {
  calendar?: MarketCalendar;
  /** Optional server-clock offset in milliseconds (serverUtcMs - clientUtcMs) */
  serverTimeOffsetMs?: number;
  /** Optional initial epoch timestamp (ms) for deterministic SSR / test hydration */
  initialEpochMs?: number;
  /** Optional flag if market status source is unavailable */
  forceUnavailable?: boolean;
  /** Show next opening/closing countdown */
  showCountdown?: boolean;
  /** Visual variant: "hero" (full status card) or "compact" (navbar pill) */
  variant?: "hero" | "compact";
  /** Optional CSS class names */
  className?: string;
}

/**
 * Reusable NSE Equity Market Live Status Indicator.
 * Separated from the clock component and driven by the published NSE calendar,
 * regular hours, and announced special Muhurat sessions.
 */
function IndianMarketStatusBadge({
  calendar,
  serverTimeOffsetMs = 0,
  initialEpochMs,
  forceUnavailable = false,
  showCountdown = true,
  variant = "hero",
  className = "",
}: IndianMarketStatusBadgeProps) {
  const [status, setStatus] = useState<IndianMarketStatusResult>(() =>
    initialEpochMs !== undefined
      ? evaluateIndianMarketStatus(initialEpochMs, { forceUnavailable, calendar })
      : evaluateIndianMarketStatus(0, { forceUnavailable: true }),
  );

  useEffect(() => {
    const updateStatus = () => {
      setStatus(
        evaluateIndianMarketStatus(Date.now(), {
          serverTimeOffsetMs,
          forceUnavailable,
          calendar,
        }),
      );
    };

    updateStatus();
    const intervalId = window.setInterval(updateStatus, 1000);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [serverTimeOffsetMs, forceUnavailable, calendar]);

  const isLive = status.state === "OPEN";
  const isClosed = status.state === "CLOSED";

  const borderTone = isLive
    ? "border-ui-green/25 bg-ui-green/10"
    : isClosed
      ? "border-ui-red/25 bg-ui-red/10"
      : "border-ui-amber/25 bg-ui-amber/10";

  const badgeTone = isLive
    ? "border-ui-green/25 bg-ui-green/15 text-ui-green"
    : isClosed
      ? "border-ui-red/25 bg-ui-red/15 text-ui-red"
      : "border-ui-amber/25 bg-ui-amber/15 text-ui-amber";

  if (variant === "compact") {
    return (
      <div
        role="status"
        aria-live="polite"
        data-testid="market-status-compact"
        className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[11px] font-semibold tracking-wide ${badgeTone} ${className}`}
      >
        <span className="relative flex h-2 w-2 items-center justify-center" aria-hidden="true">
          {isLive && (
            <span className="market-live-ring absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
          )}
          <span
            className={`relative inline-flex h-2 w-2 rounded-full ${
              isLive
                ? "bg-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.85)]"
                : isClosed
                  ? "bg-rose-500"
                  : "bg-amber-400"
            }`}
          />
        </span>
        <span>{isLive ? "NSE SESSION OPEN" : status.label}</span>
      </div>
    );
  }

  return (
    <div
      data-testid="market-status-card"
      className={`flex flex-col justify-between rounded-xl border px-4 py-3 shadow-inner backdrop-blur-md transition-colors ${borderTone} ${className}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-ui-muted">
          Scheduled NSE Equity Session
        </span>
        <span className="rounded border border-ui-line bg-ui-inset px-1.5 py-0.5 font-mono text-[10px] font-medium text-ui-muted">
          {status.scheduleSummary}
        </span>
      </div>

      <div className="mt-1.5 flex items-center gap-2.5">
        <span className="relative flex h-3 w-3 shrink-0 items-center justify-center" aria-hidden="true">
          {isLive && (
            <span className="market-live-ring absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
          )}
          <span
            data-testid="market-status-dot"
            className={`relative inline-flex h-2.5 w-2.5 rounded-full ${
              isLive
                ? "bg-emerald-400 shadow-[0_0_10px_rgba(16,185,129,0.9)]"
                : isClosed
                  ? "bg-rose-500 shadow-[0_0_6px_rgba(244,63,94,0.45)]"
                  : "bg-amber-400"
            }`}
          />
        </span>

        <span
          role="status"
          aria-live="polite"
          data-testid="market-status-label"
          className={`font-mono text-base font-bold tracking-wider sm:text-lg ${
            isLive
              ? "text-ui-green"
              : isClosed
                ? "text-ui-red"
                : "text-ui-amber"
          }`}
        >
          {isLive ? "NSE SESSION OPEN" : status.label}
        </span>

        {isLive && (
          <span
            aria-hidden="true"
            className="ml-auto inline-flex items-end gap-0.5 rounded border border-ui-green/25 bg-ui-green/10 px-2 py-1"
          >
            <span className="live-eq-bar h-2 w-0.5 bg-emerald-400" />
            <span className="live-eq-bar h-3 w-0.5 bg-emerald-300 [animation-delay:180ms]" />
            <span className="live-eq-bar h-1.5 w-0.5 bg-emerald-400 [animation-delay:340ms]" />
            <span className="live-eq-bar h-2.5 w-0.5 bg-emerald-300 [animation-delay:120ms]" />
          </span>
        )}
      </div>

      <div aria-live="off" className="mt-1 flex flex-col gap-0.5 text-[11px] text-ui-muted tabular-nums">
        {showCountdown && status.countdown ? (
          <span data-testid="market-status-countdown" className="font-mono font-medium text-ui-ink">
            {status.countdown.summaryText}
          </span>
        ) : (
          <span data-testid="market-status-reason" className="text-ui-muted">
            {status.reason}
          </span>
        )}
        {status.holidayName && (
          <span className="text-[10px] text-ui-amber">
            Holiday: {status.holidayName}
          </span>
        )}
      </div>
    </div>
  );
}

export default memo(IndianMarketStatusBadge);
