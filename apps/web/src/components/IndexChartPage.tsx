"use client";

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { useAuth } from "@/components/auth/AuthProvider";

type MarketSymbol = "NIFTY50" | "BANKNIFTY";
type Candle = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  is_forming: boolean;
  is_incomplete?: boolean;
  timeframe?: string;
};
type Decision = {
  decision: "BUY" | "SELL" | "WAIT" | "DATA_UNAVAILABLE";
  is_current_signal: boolean;
  candle_timestamp: string | null;
  reason: string;
  ut_bot_signal: string | null;
  ema_bullish: boolean | null;
  rsi_bullish: boolean | null;
  macd_bullish: boolean | null;
  supertrend_bullish: boolean | null;
  confirmed_candle_count: number;
};
type CandleResponse = {
  candles: Candle[];
  feed_state: string;
  is_stale: boolean;
  message: string;
  timeframe: string;
  indicator_decision: Decision;
  indicator_history: SignalPoint[];
};
type SignalPoint = { timestamp: string; decision: Decision["decision"] };
type QuoteResponse = {
  available: boolean;
  feed_state: string;
  is_stale: boolean;
  quote: { ltp: number; timestamp: string } | null;
};
type FormingResponse = { available: boolean; forming_candle: Candle | null };
type Provider = "groww" | "upstox";
const chartControlClass = "min-h-9 rounded border border-white/10 px-2 text-xs text-slate-300 transition hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400";

function subscribeToMarketProvider(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener("allsafe-market-provider-change", onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener("allsafe-market-provider-change", onChange);
  };
}

function getMarketProviderSnapshot(): Provider {
  const stored = window.localStorage.getItem("allsafe-market-provider");
  return stored === "upstox" ? "upstox" : "groww";
}

function setMarketProvider(provider: Provider) {
  window.localStorage.setItem("allsafe-market-provider", provider);
  window.dispatchEvent(new Event("allsafe-market-provider-change"));
}

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  (process.env.NODE_ENV === "production"
    ? "https://allsafe-ai-api.onrender.com"
    : "http://localhost:8000")
).trim().replace(/\/+$/, "");

const labels: Record<MarketSymbol, string> = {
  NIFTY50: "NIFTY 50",
  BANKNIFTY: "BANK NIFTY",
};

const emptyDecision: Decision = {
  decision: "DATA_UNAVAILABLE",
  is_current_signal: false,
  candle_timestamp: null,
  reason: "Waiting for the first confirmed candle.",
  ut_bot_signal: null,
  ema_bullish: null,
  rsi_bullish: null,
  macd_bullish: null,
  supertrend_bullish: null,
  confirmed_candle_count: 0,
};

class MarketAccessError extends Error {}

async function getJson<T>(path: string, token: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
    credentials: "omit",
    signal: AbortSignal.any([signal, AbortSignal.timeout(12000)]),
  });
  if (response.status === 401 || response.status === 403) {
    throw new MarketAccessError("Your account access changed. Sign in again.");
  }
  if (!response.ok) throw new Error(`Market data request failed (HTTP ${response.status}).`);
  return response.json() as Promise<T>;
}

function price(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

function timeLabel(value: string): string {
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Kolkata",
  }).format(new Date(value));
}

function voteLabel(value: boolean | null): string {
  return value == null ? "No reading" : value ? "Bullish" : "Bearish";
}

function voteStyle(value: boolean | null): string {
  return value == null ? "text-slate-500" : value ? "text-emerald-300" : "text-rose-300";
}

function CandlestickPanel({
  candles,
  visibleCount,
  offset,
  decision,
  signalHistory,
  onZoomIn,
  onZoomOut,
  onOlder,
  onNewer,
  onLatest,
}: {
  candles: Candle[];
  visibleCount: number;
  offset: number;
  decision: Decision;
  signalHistory: SignalPoint[];
  onZoomIn: () => void;
  onZoomOut: () => void;
  onOlder: () => void;
  onNewer: () => void;
  onLatest: () => void;
}) {
  const width = 1200;
  const height = 560;
  const left = 24;
  const right = 92;
  const top = 32;
  const bottom = 54;
  const plotHeight = height - top - bottom;
  const end = Math.max(0, candles.length - offset);
  const start = Math.max(0, end - visibleCount);
  const visible = candles.slice(start, end);
  const decisionByTimestamp = new Map(signalHistory.map((point) => [point.timestamp, point.decision]));
  const minimum = visible.length ? Math.min(...visible.map((candle) => candle.low)) : 0;
  const maximum = visible.length ? Math.max(...visible.map((candle) => candle.high)) : 1;
  const range = Math.max(maximum - minimum, Math.abs(maximum) * 0.0001, 1);
  const y = (value: number) => top + ((maximum - value) / range) * plotHeight;
  const plotWidth = width - left - right;
  const slot = visible.length ? plotWidth / visible.length : plotWidth;
  const visibleSignals = visible.flatMap((candle, index) => {
    const eventDecision = decisionByTimestamp.get(candle.timestamp);
    const latestMatches = decision.candle_timestamp === candle.timestamp;
    const signal = eventDecision === "BUY" || eventDecision === "SELL"
      ? eventDecision
      : latestMatches && (decision.decision === "BUY" || decision.decision === "SELL")
        ? decision.decision
        : null;
    return signal ? [{ candle, index, signal }] : [];
  });

  return (
    <section className="overflow-hidden rounded-xl border border-white/10 bg-[#0b1118]" aria-label="15-minute candlestick chart">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="rounded bg-emerald-400/10 px-2 py-1 text-xs font-semibold text-emerald-300">15m</span>
          <span className="text-xs text-slate-400">NSE session · IST</span>
          <span className="hidden text-xs text-slate-600 sm:inline">{candles.length} candles loaded</span>
        </div>
        <div className="flex flex-wrap items-center gap-2" aria-label="Chart controls">
          <button onClick={onOlder} disabled={start === 0} className={chartControlClass}>← Older</button>
          <button onClick={onNewer} disabled={offset === 0} className={chartControlClass}>Newer →</button>
          <button onClick={onLatest} className={chartControlClass}>Latest</button>
          <span className="mx-1 hidden h-5 border-l border-white/10 sm:inline" />
          <button onClick={onZoomOut} aria-label="Zoom out" className={chartControlClass}>−</button>
          <span className="min-w-12 text-center text-xs tabular-nums text-slate-400">{visibleCount} bars</span>
          <button onClick={onZoomIn} aria-label="Zoom in" className={chartControlClass}>+</button>
        </div>
      </div>
      {visible.length === 0 ? (
        <div className="flex h-[62vh] min-h-80 items-center justify-center px-5 text-center text-sm text-slate-400">
          No validated 15-minute candles are available yet. Check the provider and live-feed status.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <svg
            className="block h-[62vh] min-h-80 w-full min-w-[760px]"
            viewBox={`0 0 ${width} ${height}`}
            role="img"
            aria-label={`15-minute candlestick chart with ${visible.length} bars`}
            preserveAspectRatio="none"
          >
            {[0, 0.25, 0.5, 0.75, 1].map((fraction) => {
              const gridY = top + fraction * plotHeight;
              const value = maximum - fraction * range;
              return (
                <g key={fraction}>
                  <line x1={left} x2={width - right} y1={gridY} y2={gridY} stroke="#233142" strokeDasharray="3 6" />
                  <text x={width - right + 12} y={gridY + 4} fill="#94a3b8" fontSize="12">{price(value)}</text>
                </g>
              );
            })}
            {visible.map((candle, index) => {
              const x = left + index * slot + slot / 2;
              const bullish = candle.close >= candle.open;
              const color = bullish ? "#34d399" : "#fb7185";
              const bodyTop = Math.min(y(candle.open), y(candle.close));
              const bodyHeight = Math.max(Math.abs(y(candle.open) - y(candle.close)), 2);
              const bodyWidth = Math.max(Math.min(slot * 0.62, 18), 2);
              const dateIndex = index === 0 || index === visible.length - 1 || index % Math.max(1, Math.floor(visible.length / 6)) === 0;
              return (
                <g key={candle.timestamp} opacity={candle.is_forming ? 0.6 : 1}>
                  <line x1={x} x2={x} y1={y(candle.high)} y2={y(candle.low)} stroke={color} strokeWidth="1.5" />
                  <rect x={x - bodyWidth / 2} y={bodyTop} width={bodyWidth} height={bodyHeight}
                    fill={bullish ? color : "#0b1118"} stroke={color} strokeWidth="1.5" rx="1" />
                  {dateIndex && <text x={x} y={height - 16} textAnchor="middle" fill="#94a3b8" fontSize="11">{timeLabel(candle.timestamp)}</text>}
                </g>
              );
            })}
            {visibleSignals.map(({ candle, index, signal }) => {
              const x = left + index * slot + slot / 2;
              const markerY = Math.max(top + 7, y(candle.high) - 26);
              const current = decision.candle_timestamp === candle.timestamp;
              const markerWidth = current ? 54 : 22;
              const label = current ? signal : signal === "BUY" ? "B" : "S";
              return (
                <g key={`signal-${candle.timestamp}`} aria-label={`${signal} signal on ${timeLabel(candle.timestamp)}`}>
                  <title>{`${signal} signal · ${timeLabel(candle.timestamp)} IST`}</title>
                  <rect x={x - markerWidth / 2} y={markerY} width={markerWidth} height="22" rx="11"
                    fill={signal === "BUY" ? "#064e3b" : "#881337"}
                    stroke={signal === "BUY" ? "#34d399" : "#fb7185"} />
                  <text x={x} y={markerY + 15} textAnchor="middle" fill="white" fontSize="11" fontWeight="700">{label}</text>
                </g>
              );
            })}
            {visible.some((candle) => candle.is_forming) && (
              <text x={left + 6} y={top + 16} fill="#fbbf24" fontSize="11">Dashed opacity marks the forming candle</text>
            )}
          </svg>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-white/10 px-4 py-3 text-xs text-slate-400">
        <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-emerald-400" />Bullish candle</span>
        <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-rose-400" />Bearish candle</span>
        {decision.candle_timestamp && <span>Signal evaluated on {timeLabel(decision.candle_timestamp)} IST</span>}
      </div>
    </section>
  );
}

export default function IndexChartPage({ symbol }: { symbol: string }) {
  const normalizedSymbol = symbol.toUpperCase() as MarketSymbol;
  const validSymbol = normalizedSymbol === "NIFTY50" || normalizedSymbol === "BANKNIFTY";
  const instrumentName = validSymbol ? labels[normalizedSymbol] : "Index";
  const { session, signOut } = useAuth();
  const token = session?.access_token;
  const provider = useSyncExternalStore(subscribeToMarketProvider, getMarketProviderSnapshot, () => "groww");
  const [candles, setCandles] = useState<Candle[]>([]);
  const [signalHistory, setSignalHistory] = useState<SignalPoint[]>([]);
  const [decision, setDecision] = useState<Decision>(emptyDecision);
  const [quote, setQuote] = useState<QuoteResponse["quote"]>(null);
  const [feedState, setFeedState] = useState("checking");
  const [feedMessage, setFeedMessage] = useState("Connecting to the market-data service.");
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [visibleCount, setVisibleCount] = useState(80);
  const [offset, setOffset] = useState(0);
  const activeRefresh = useRef<AbortSignal | null>(null);

  const refresh = useCallback(async (signal: AbortSignal) => {
    if (!token || !validSymbol || signal.aborted || (activeRefresh.current && !activeRefresh.current.aborted)) return;
    activeRefresh.current = signal;
    const query = `?symbol=${normalizedSymbol}&provider=${provider}`;
    try {
      const [candleData, quoteData, formingData] = await Promise.all([
        getJson<CandleResponse>(`/api/v1/live/candles${query}&timeframe=15m&limit=500&include_indicator_history=true`, token, signal),
        getJson<QuoteResponse>(`/api/v1/live/quote${query}`, token, signal),
        getJson<FormingResponse>(`/api/v1/live/forming-candle${query}`, token, signal),
      ]);
      if (signal.aborted) return;
      const series = [...candleData.candles];
      const quoteCurrent = quoteData.available && quoteData.feed_state === "live" && !quoteData.is_stale;
      if (quoteCurrent && formingData.available && formingData.forming_candle) {
        series.push(formingData.forming_candle);
      }
      const unique = Array.from(new Map(series.filter((candle) => candle.timeframe == null || candle.timeframe === "15m")
        .map((candle) => [candle.timestamp, candle])).values())
        .sort((left, right) => left.timestamp.localeCompare(right.timestamp));
      setCandles(unique);
      setDecision(candleData.indicator_decision);
      setSignalHistory(candleData.indicator_history ?? []);
      setQuote(quoteData.quote);
      setFeedState(quoteData.feed_state || candleData.feed_state);
      setFeedMessage(candleData.message);
      setCheckedAt(new Date());
      setError(null);
      setLoading(false);
    } catch (reason) {
      if (signal.aborted) return;
      if (reason instanceof MarketAccessError) {
        await signOut();
        return;
      }
      setError(reason instanceof Error ? reason.message : "Could not load the 15-minute chart.");
      setFeedState("unavailable");
      setLoading(false);
    } finally {
      if (activeRefresh.current === signal) activeRefresh.current = null;
    }
  }, [normalizedSymbol, provider, signOut, token, validSymbol]);

  useEffect(() => {
    if (!token || !validSymbol) return;
    const controller = new AbortController();
    const initialRequest = window.setTimeout(() => void refresh(controller.signal), 0);
    const timer = window.setInterval(() => void refresh(controller.signal), 15000);
    return () => {
      controller.abort();
      window.clearTimeout(initialRequest);
      window.clearInterval(timer);
    };
  }, [refresh, token, validSymbol]);

  const latestConfirmed = useMemo(
    () => [...candles].reverse().find((candle) => !candle.is_forming),
    [candles],
  );
  const decisionColor = decision.decision === "BUY"
    ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300"
    : decision.decision === "SELL"
      ? "border-rose-400/30 bg-rose-400/10 text-rose-300"
      : "border-white/10 bg-white/[0.03] text-slate-300";

  if (!validSymbol) {
    return (
      <main className="mx-auto flex min-h-dvh max-w-3xl flex-col justify-center px-6 py-12">
        <h1 className="text-2xl font-semibold">Chart not found</h1>
        <p className="mt-2 text-slate-400">Choose NIFTY 50 or BANK NIFTY from the dashboard.</p>
        <Link href="/terminal" className="mt-5 text-emerald-300 underline">Return to dashboard</Link>
      </main>
    );
  }

  return (
    <main className="min-h-dvh bg-slate-950 px-3 py-4 text-slate-100 sm:px-6 sm:py-6">
      <div className="mx-auto max-w-[1600px] space-y-4">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
          <div>
            <Link href="/terminal" className="text-xs text-emerald-300 hover:text-emerald-200">← Market dashboard</Link>
            <h1 className="mt-2 text-2xl font-bold tracking-tight sm:text-3xl">{instrumentName}</h1>
            <p className="mt-1 text-sm text-slate-400">15-minute price chart · Rule-based indicator analysis</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <label htmlFor="chart-provider" className="text-sm text-slate-400">Market data</label>
            <select id="chart-provider" value={provider} onChange={(event) => {
              const next = event.target.value as Provider;
              setMarketProvider(next);
              setLoading(true);
            }} className="min-h-10 rounded-md border border-white/15 bg-slate-900 px-3 text-sm text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400">
              <option value="groww">Groww</option>
              <option value="upstox">Upstox</option>
            </select>
            <span className="rounded-full border border-white/10 px-3 py-2 text-xs capitalize text-slate-300">Feed: {feedState.replaceAll("_", " ")}</span>
          </div>
        </header>

        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Market summary">
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <p className="text-xs uppercase tracking-wide text-slate-500">Last price</p>
            <p className="mt-2 text-2xl font-semibold tabular-nums">{price(quote?.ltp ?? latestConfirmed?.close)}</p>
            <p className="mt-1 text-xs text-slate-500">{quote?.timestamp ? `${timeLabel(quote.timestamp)} IST` : "No recent quote"}</p>
          </div>
          <div className={`rounded-xl border p-4 ${decisionColor}`}>
            <p className="text-xs uppercase tracking-wide opacity-70">Signal</p>
            <p className="mt-2 text-2xl font-bold">{decision.decision}</p>
            <p className="mt-1 text-xs opacity-80">{decision.is_current_signal ? "Current confirmed signal" : "Based on confirmed candle data"}</p>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <p className="text-xs uppercase tracking-wide text-slate-500">Confirmed bars</p>
            <p className="mt-2 text-2xl font-semibold tabular-nums">{decision.confirmed_candle_count}</p>
            <p className="mt-1 text-xs text-slate-500">15-minute candles for indicator analysis</p>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <p className="text-xs uppercase tracking-wide text-slate-500">Updated</p>
            <p className="mt-2 text-lg font-semibold">{checkedAt ? checkedAt.toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" }) : "Connecting…"}</p>
            <p className="mt-1 text-xs text-slate-500">Refreshes every 15 seconds · IST</p>
          </div>
        </section>

        {error && <div role="alert" className="rounded-lg border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-200">{error}</div>}
        {loading && <p role="status" className="text-sm text-slate-400">Loading the 15-minute chart…</p>}
        {!error && <p className="text-sm text-slate-400">{feedMessage}</p>}

        <CandlestickPanel
          candles={candles}
          visibleCount={visibleCount}
          offset={offset}
          decision={decision}
        signalHistory={signalHistory}
          onZoomIn={() => setVisibleCount((count) => Math.max(20, count - 20))}
          onZoomOut={() => setVisibleCount((count) => Math.min(300, count + 20))}
          onOlder={() => setOffset((value) => Math.min(Math.max(0, candles.length - visibleCount), value + visibleCount))}
          onNewer={() => setOffset((value) => Math.max(0, value - visibleCount))}
          onLatest={() => setOffset(0)}
        />

        <section className="rounded-xl border border-white/10 bg-white/[0.03] p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="font-semibold">Indicator readings</h2>
              <p className="mt-1 text-xs text-slate-500">Calculated from complete, confirmed 15-minute candles. Forming candles are excluded.</p>
            </div>
            <span className="text-xs text-slate-500">{decision.candle_timestamp ? `Evaluated ${timeLabel(decision.candle_timestamp)} IST` : "Waiting for confirmed data"}</span>
          </div>
          <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
            {[
              ["UT Bot", decision.ut_bot_signal ?? "No signal", decision.ut_bot_signal === "BUY" ? "text-emerald-300" : decision.ut_bot_signal === "SELL" ? "text-rose-300" : "text-slate-500"],
              ["EMA", voteLabel(decision.ema_bullish), voteStyle(decision.ema_bullish)],
              ["RSI", voteLabel(decision.rsi_bullish), voteStyle(decision.rsi_bullish)],
              ["MACD", voteLabel(decision.macd_bullish), voteStyle(decision.macd_bullish)],
              ["Supertrend", voteLabel(decision.supertrend_bullish), voteStyle(decision.supertrend_bullish)],
            ].map(([name, value, style]) => (
              <div key={name} className="rounded-lg border border-white/10 bg-slate-950/70 px-3 py-3">
                <p className="text-xs text-slate-500">{name}</p>
                <p className={`mt-1 text-sm font-medium ${style}`}>{value}</p>
              </div>
            ))}
          </div>
          <p className="mt-4 text-sm leading-relaxed text-slate-400">{decision.reason}</p>
        </section>

        <footer className="border-t border-white/10 pt-3 text-xs leading-relaxed text-slate-500">
          Educational market analysis only; not investment advice. Signals follow fixed rules, may be delayed or wrong, and do not place orders.
        </footer>
      </div>
    </main>
  );
}
