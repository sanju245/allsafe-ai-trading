"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/components/auth/AuthProvider";
import type { Signal } from "@/lib/indexChart";
import CandleSignalLabels from "./CandleSignalLabels";

type SymbolId = "NIFTY50" | "BANKNIFTY";
type Candle = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
};
type CandleReply = {
  provider: string;
  instrument: SymbolId;
  timeframe: "15m";
  start_date: string;
  end_date: string;
  retrieved_at: string;
  last_candle_at: string | null;
  candles: Candle[];
  signals?: Signal[];
  message: string;
};
type MarketSnapshot = {
  candles: Candle[];
  signals: Signal[];
  retrievedAt: string | null;
  lastCandleAt: string | null;
  startDate: string | null;
  endDate: string | null;
  loading: boolean;
  error: string | null;
};

const markets: { symbol: SymbolId; label: string }[] = [
  { symbol: "NIFTY50", label: "NIFTY 50" },
  { symbol: "BANKNIFTY", label: "BANK NIFTY" },
];
const ranges = [
  { days: 1, label: "Today" },
  { days: 7, label: "Last 7 days" },
  { days: 14, label: "Last 14 days" },
  { days: 30, label: "Last 30 days" },
];
const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL?.trim() ||
  (process.env.NODE_ENV === "development" ? "http://localhost:8000" : "https://allsafe-ai-api.onrender.com")
).replace(/\/+$/, "");

const emptySnapshot = (): MarketSnapshot => ({
  candles: [],
  signals: [],
  retrievedAt: null,
  lastCandleAt: null,
  startDate: null,
  endDate: null,
  loading: true,
  error: null,
});

function formatPrice(value: number): string {
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(value);
}

function formatIst(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Unavailable"
    : date.toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" });
}

function HistoryCandleChart({ candles, signals, label }: { candles: Candle[]; signals: Signal[]; label: string }) {
  if (candles.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-lg border border-dashed border-white/10 px-6 text-center text-sm text-slate-400">
        No completed 15-minute candles were returned for this date range.
      </div>
    );
  }

  const height = 300;
  const inset = 28;
  const width = Math.max(720, candles.length * 11 + inset * 2);
  const plotHeight = height - inset * 2 - 18;
  const slotWidth = (width - inset * 2) / candles.length;
  const slotX = (index: number) => inset + (index + 0.5) * slotWidth;
  const min = Math.min(...candles.map((candle) => candle.low));
  const max = Math.max(...candles.map((candle) => candle.high));
  const range = Math.max(max - min, Math.abs(max) * 0.0001, 1);
  const y = (price: number) => inset + ((max - price) / range) * plotHeight;
  const dayStarts = candles.flatMap((candle, index) => {
    const date = new Date(candle.timestamp).toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
    const previousDate = index > 0
      ? new Date(candles[index - 1].timestamp).toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" })
      : null;
    return date !== previousDate ? [{ index, date }] : [];
  });

  return (
    <div className="overflow-x-auto rounded-lg border border-white/10 bg-slate-950/60" tabIndex={0} aria-label={`${label} historical chart; scroll horizontally to older candles`}>
      <svg
        className="block h-72 max-w-none"
        style={{ width: `${width}px` }}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${label} Upstox 15-minute historical candlestick chart`}
        preserveAspectRatio="none"
      >
        {[0, 0.5, 1].map((fraction) => {
          const gridY = inset + fraction * plotHeight;
          const value = max - fraction * range;
          return (
            <g key={fraction}>
              <line x1={inset} x2={width - inset} y1={gridY} y2={gridY} stroke="#243142" strokeDasharray="3 5" />
              <text x={width - inset} y={gridY - 4} textAnchor="end" fill="#94a3b8" fontSize="10">{formatPrice(value)}</text>
            </g>
          );
        })}
        {candles.map((candle, index) => {
          const x = slotX(index);
          const bullish = candle.close >= candle.open;
          const color = bullish ? "#34d399" : "#fb7185";
          const bodyTop = Math.min(y(candle.open), y(candle.close));
          const bodyHeight = Math.max(Math.abs(y(candle.open) - y(candle.close)), 1.5);
          return (
            <g key={candle.timestamp}>
              <line x1={x} x2={x} y1={y(candle.high)} y2={y(candle.low)} stroke={color} strokeWidth="1.2" />
              <rect x={x - Math.max(1.5, slotWidth * 0.28)} y={bodyTop} width={Math.max(3, slotWidth * 0.56)} height={bodyHeight} rx="0.7" fill={color} />
            </g>
          );
        })}
        <CandleSignalLabels candles={candles} signals={signals} x={slotX} y={y} />
        {dayStarts.map(({ index, date }) => {
          const x = inset + index * slotWidth;
          const shortDate = new Date(`${date}T00:00:00+05:30`).toLocaleDateString("en-IN", {
            timeZone: "Asia/Kolkata",
            day: "2-digit",
            month: "short",
          });
          return <text key={date} x={x + 2} y={height - 3} fill="#94a3b8" fontSize="10">{shortDate}</text>;
        })}
      </svg>
    </div>
  );
}

function HistoryPanel({ accessToken }: { accessToken: string }) {
  const [days, setDays] = useState(7);
  const [refreshKey, setRefreshKey] = useState(0);
  const [marketsState, setMarketsState] = useState<Record<SymbolId, MarketSnapshot>>({
    NIFTY50: emptySnapshot(),
    BANKNIFTY: emptySnapshot(),
  });
  const { signOut } = useAuth();

  const refresh = useCallback(async (signal: AbortSignal) => {
    await Promise.all(markets.map(async ({ symbol }) => {
      try {
        const response = await fetch(
          `${API_BASE_URL}/api/v1/market-data/upstox/candles?symbol=${symbol}&days=${days}`,
          {
            headers: { Authorization: `Bearer ${accessToken}`, Accept: "application/json" },
            cache: "no-store",
            credentials: "omit",
            signal: AbortSignal.any([signal, AbortSignal.timeout(15000)]),
          },
        );
        if (signal.aborted) return;
        if (response.status === 401 || response.status === 403) {
          await signOut();
          return;
        }
        const body: unknown = await response.json().catch(() => null);
        if (!response.ok) {
          const detail = typeof body === "object" && body !== null && "detail" in body && typeof body.detail === "string"
            ? body.detail
            : `Upstox history request failed (HTTP ${response.status}).`;
          throw new Error(detail);
        }
        const result = body as CandleReply;
        if (!Array.isArray(result.candles)) throw new Error("Upstox returned an unreadable candle list.");
        if (signal.aborted) return;
        setMarketsState((current) => ({
          ...current,
          [symbol]: {
            candles: result.candles,
            signals: result.signals ?? [],
            retrievedAt: result.retrieved_at,
            lastCandleAt: result.last_candle_at,
            startDate: result.start_date,
            endDate: result.end_date,
            loading: false,
            error: null,
          },
        }));
      } catch (cause) {
        if (signal.aborted) return;
        setMarketsState((current) => ({
          ...current,
          [symbol]: {
            ...current[symbol],
            loading: false,
            error: cause instanceof Error ? cause.message : "Could not load Upstox historical candles.",
          },
        }));
      }
    }));
  }, [accessToken, days, signOut]);

  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    return () => controller.abort();
  }, [refresh, refreshKey]);

  function chooseDays(nextDays: number) {
    setDays(nextDays);
    setMarketsState((current) => ({
      NIFTY50: { ...current.NIFTY50, loading: true, error: null },
      BANKNIFTY: { ...current.BANKNIFTY, loading: true, error: null },
    }));
  }

  return (
    <section aria-labelledby="upstox-history-title" className="as-panel p-4 sm:p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="as-kicker">Upstox history</p>
          <h2 id="upstox-history-title" className="as-section-title mt-1">15-minute candle charts</h2>
          <p className="mt-2 max-w-2xl text-sm text-slate-400">Review completed candles from earlier sessions. Scroll the chart horizontally to see older dates.</p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-xs font-medium text-slate-400">
            Date range
            <select
              value={days}
              onChange={(event) => chooseDays(Number(event.target.value))}
              className="as-field mt-1"
            >
              {ranges.map((range) => <option key={range.days} value={range.days}>{range.label}</option>)}
            </select>
          </label>
          <button
            type="button"
            onClick={() => {
              setMarketsState((current) => ({
                NIFTY50: { ...current.NIFTY50, loading: true, error: null },
                BANKNIFTY: { ...current.BANKNIFTY, loading: true, error: null },
              }));
              setRefreshKey((value) => value + 1);
            }}
            disabled={marketsState.NIFTY50.loading || marketsState.BANKNIFTY.loading}
            className="as-button as-button--quiet"
          >
            Refresh candles
          </button>
        </div>
      </div>

      <p className="mt-3 text-xs text-slate-500">Historical data only; it is not a live quote or trading instruction. Upstox index volume is omitted.</p>

      <div className="mt-6 grid gap-6">
        {markets.map(({ symbol, label }) => {
          const snapshot = marketsState[symbol];
          return (
            <article key={symbol} aria-labelledby={`upstox-${symbol}-title`} className="as-inset min-w-0 p-3 sm:p-4">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h3 id={`upstox-${symbol}-title`} className="font-semibold text-white">
                  <Link href={`/chart/${symbol}?provider=upstox&days=${days}`} target="_blank" rel="noopener noreferrer" className="rounded underline-offset-4 hover:text-emerald-300 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400">
                    {label}<span className="ml-2 text-xs text-emerald-300" aria-label="opens chart in a new tab">↗</span>
                  </Link>
                </h3>
                {snapshot.retrievedAt && (
                  <div className="text-xs text-slate-500">
                    <p>Loaded {formatIst(snapshot.retrievedAt)} IST</p>
                    <p>Latest returned candle: {snapshot.lastCandleAt ? `${formatIst(snapshot.lastCandleAt)} IST` : "Unavailable"}</p>
                  </div>
                )}
              </div>
              {snapshot.error && <p role="alert" className="mb-3 rounded-lg border border-rose-400/30 bg-rose-400/10 p-3 text-sm text-rose-100">{snapshot.error}</p>}
              {snapshot.loading && snapshot.candles.length === 0 ? (
                <div className="flex h-64 items-center justify-center rounded-lg border border-dashed border-white/10 text-sm text-slate-400">Loading Upstox candles…</div>
              ) : (
                <HistoryCandleChart candles={snapshot.candles} signals={snapshot.signals} label={label} />
              )}
              <p className="mt-2 text-xs text-slate-500">
                {snapshot.startDate && snapshot.endDate
                  ? `${snapshot.startDate} to ${snapshot.endDate} · ${snapshot.candles.length} candles · 15-minute interval`
                  : "Choose a date range to load historical candles."}
              </p>
            </article>
          );
        })}
      </div>
    </section>
  );
}

export default function Upstox15mHistory() {
  const { session, profile } = useAuth();
  if (!session?.access_token || profile?.status !== "active") return null;
  return <HistoryPanel key={session.access_token} accessToken={session.access_token} />;
}
