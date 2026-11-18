"use client";

import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
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
type HistoryResponse = {
  timeframe: string;
  start_date: string;
  candles: Candle[];
  signals: SignalPoint[];
  message: string;
};
type Provider = "groww" | "upstox";
type ChartScope = {
  symbol: MarketSymbol;
  provider: Provider;
  token: string | undefined;
  historyDays: number | null;
};
type LiveSnapshot = {
  scope: ChartScope;
  candles: Candle[];
  decision: Decision;
  signalHistory: SignalPoint[];
  quote: QuoteResponse["quote"];
  feedState: string;
  message: string;
  checkedAt: Date;
};
type HistorySnapshot = {
  scope: ChartScope;
  data: HistoryResponse;
};
type ChartError = { scope: ChartScope; message: string };
const emptyCandles: Candle[] = [];
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
  try {
    return window.localStorage.getItem("allsafe-market-provider") === "upstox" ? "upstox" : "groww";
  } catch {
    return "groww";
  }
}

function setMarketProvider(provider: Provider) {
  const params = new URLSearchParams(window.location.search);
  params.set("provider", provider);
  if (provider !== "upstox") params.delete("days");
  window.history.replaceState(null, "", `?${params.toString()}${window.location.hash}`);
  try {
    window.localStorage.setItem("allsafe-market-provider", provider);
    window.dispatchEvent(new Event("allsafe-market-provider-change"));
  } catch {
    // The URL still preserves the selected provider when storage is unavailable.
  }
}

function selectedHistoryDays(days: string | null): number | null {
  if (days === null || !/^(?:[1-9]|[12][0-9]|30)$/.test(days)) return 7;
  return Number(days);
}

function mergeChartCandles(history: HistoryResponse | undefined, live: Candle[]): Candle[] {
  const candles = new Map<number, Candle>();
  for (const candle of history?.candles ?? []) {
    if (candle.timeframe === "15m") candles.set(Date.parse(candle.timestamp), { ...candle, is_forming: false });
  }
  const start = history ? Date.parse(`${history.start_date}T00:00:00+05:30`) : -Infinity;
  for (const candle of live) {
    const timestamp = Date.parse(candle.timestamp);
    if (candle.timeframe !== "15m" || timestamp < start) continue;
    if ((candle.is_incomplete || candle.is_forming) && candles.has(timestamp)) continue;
    candles.set(timestamp, candle);
  }
  return Array.from(candles.entries())
    .filter(([timestamp]) => Number.isFinite(timestamp))
    .sort(([left], [right]) => left - right)
    .map(([, candle]) => candle);
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
  const decisionByTimestamp = new Map(signalHistory.map((point) => [Date.parse(point.timestamp), point.decision]));
  const minimum = visible.length ? Math.min(...visible.map((candle) => candle.low)) : 0;
  const maximum = visible.length ? Math.max(...visible.map((candle) => candle.high)) : 1;
  const dataRange = Math.max(maximum - minimum, Math.abs(maximum) * 0.0001, 1);
  const chartMinimum = minimum - dataRange * 0.1;
  const chartMaximum = maximum + dataRange * 0.1;
  const range = chartMaximum - chartMinimum;
  const y = (value: number) => top + ((chartMaximum - value) / range) * plotHeight;
  const plotWidth = width - left - right;
  const slot = visible.length ? plotWidth / visible.length : plotWidth;
  const visibleSignals = visible.flatMap((candle, index) => {
    if (candle.is_forming || candle.is_incomplete) return [];
    const timestamp = Date.parse(candle.timestamp);
    const eventDecision = decisionByTimestamp.get(timestamp);
    const latestMatches = decision.candle_timestamp !== null && Date.parse(decision.candle_timestamp) === timestamp;
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
          <button onClick={onZoomOut} disabled={visibleCount >= 300} aria-label="Zoom out" className={chartControlClass}>−</button>
          <span className="min-w-12 text-center text-xs tabular-nums text-slate-400">{visibleCount} bars</span>
          <button onClick={onZoomIn} disabled={visibleCount <= 20} aria-label="Zoom in" className={chartControlClass}>+</button>
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
              const value = chartMaximum - fraction * range;
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
              const outline = candle.is_incomplete ? "3 3" : undefined;
              return (
                <g key={candle.timestamp} opacity={candle.is_forming ? 0.6 : 1}>
                  <line x1={x} x2={x} y1={y(candle.high)} y2={y(candle.low)} stroke={color} strokeWidth="1.5" strokeDasharray={outline} />
                  <rect x={x - bodyWidth / 2} y={bodyTop} width={bodyWidth} height={bodyHeight}
                    fill={bullish && !candle.is_incomplete ? color : "#0b1118"} stroke={color} strokeWidth="1.5" strokeDasharray={outline} rx="1" />
                  {dateIndex && <text x={x} y={height - 16} textAnchor="middle" fill="#94a3b8" fontSize="11">{timeLabel(candle.timestamp)}</text>}
                </g>
              );
            })}
            {visibleSignals.map(({ candle, index, signal }) => {
              const x = left + index * slot + slot / 2;
              const isBuy = signal === "BUY";
              const markerHeight = 20;
              const markerWidth = 40;
              const markerY = isBuy ? y(candle.low) + 8 : y(candle.high) - 30;
              const label = isBuy ? "Buy" : "Sell";
              const fill = isBuy ? "#22c55e" : "#ef4444";
              const pointerPath = isBuy
                ? `M ${x - 6} ${markerY} L ${x} ${markerY - 6} L ${x + 6} ${markerY} Z`
                : `M ${x - 6} ${markerY + markerHeight} L ${x} ${markerY + markerHeight + 6} L ${x + 6} ${markerY + markerHeight} Z`;
              return (
                <g key={`signal-${candle.timestamp}`} aria-label={`${label} signal on ${timeLabel(candle.timestamp)}`}>
                  <title>{`${label} signal · ${timeLabel(candle.timestamp)} IST`}</title>
                  <rect x={x - markerWidth / 2} y={markerY} width={markerWidth} height={markerHeight} rx="4"
                    fill={fill} />
                  <path d={pointerPath} fill={fill} />
                  <text x={x} y={markerY + 14} textAnchor="middle" fill="white" fontSize="11" fontWeight="700">{label}</text>
                </g>
              );
            })}
            {visible.some((candle) => candle.is_forming) && (
              <text x={left + 6} y={top + 16} fill="#fbbf24" fontSize="11">Faded candle is still forming</text>
            )}
          </svg>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-white/10 px-4 py-3 text-xs text-slate-400">
        <span>{visibleSignals.length} confirmed BUY/SELL {visibleSignals.length === 1 ? "signal" : "signals"} in view</span>
        <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-emerald-400" />Bullish candle</span>
        <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-rose-400" />Bearish candle</span>
        {visible.some((candle) => candle.is_incomplete) && <span>Dashed outline means incomplete data</span>}
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
  const searchParams = useSearchParams();
  const requestedProvider = searchParams.get("provider");
  const storedProvider = useSyncExternalStore<Provider>(subscribeToMarketProvider, getMarketProviderSnapshot, () => "groww");
  const provider = requestedProvider === "groww" || requestedProvider === "upstox" ? requestedProvider : storedProvider;
  const historyDays = selectedHistoryDays(searchParams.get("days"));
  const scope = useMemo<ChartScope>(
    () => ({ symbol: normalizedSymbol, provider, token, historyDays }),
    [normalizedSymbol, provider, token, historyDays],
  );
  const [liveSnapshot, setLiveSnapshot] = useState<LiveSnapshot | null>(null);
  const [historySnapshot, setHistorySnapshot] = useState<HistorySnapshot | null>(null);
  const [liveFailure, setLiveFailure] = useState<ChartError | null>(null);
  const [historyFailure, setHistoryFailure] = useState<ChartError | null>(null);
  const [visibleCount, setVisibleCount] = useState(150);
  const [position, setPosition] = useState<{ scope: ChartScope; offset: number } | null>(null);

  useEffect(() => {
    const { token, symbol, provider, historyDays } = scope;
    if (!token || !validSymbol) return;
    const controller = new AbortController();
    const { signal } = controller;
    const query = `?symbol=${symbol}&provider=${provider}`;
    let refreshing = false;

    async function refresh(authToken: string) {
      if (refreshing || signal.aborted) return;
      refreshing = true;
      try {
        const [candleData, quoteData, formingData] = await Promise.all([
          getJson<CandleResponse>(`/api/v1/live/candles${query}&timeframe=15m&limit=500&include_indicator_history=true`, authToken, signal),
          getJson<QuoteResponse>(`/api/v1/live/quote${query}`, authToken, signal),
          getJson<FormingResponse>(`/api/v1/live/forming-candle${query}`, authToken, signal),
        ]);
        if (signal.aborted) return;
        if (candleData.timeframe !== "15m" || !Array.isArray(candleData.candles)) {
          throw new Error("The market-data service did not return 15-minute candles.");
        }
        const series = candleData.candles.filter((candle) => !candle.is_forming);
        const currentQuote = quoteData.available && quoteData.feed_state === "live" && !quoteData.is_stale;
        if (currentQuote && formingData.available && formingData.forming_candle) {
          series.push({ ...formingData.forming_candle, is_forming: true });
        }
        const currentSignal = candleData.indicator_decision.is_current_signal &&
          currentQuote && !candleData.is_stale && candleData.feed_state === "live";
        setLiveSnapshot({
          scope,
          candles: series,
          decision: { ...candleData.indicator_decision, is_current_signal: currentSignal },
          signalHistory: candleData.indicator_history ?? [],
          quote: quoteData.quote,
          feedState: quoteData.feed_state || candleData.feed_state,
          message: candleData.message,
          checkedAt: new Date(),
        });
        setLiveFailure(null);
      } catch (reason) {
        if (signal.aborted) return;
        setLiveSnapshot(null);
        if (reason instanceof MarketAccessError) {
          controller.abort();
          await signOut();
          return;
        }
        setLiveFailure({ scope, message: reason instanceof Error ? reason.message : "Could not load the 15-minute chart." });
      } finally {
        refreshing = false;
      }
    }

    async function loadHistory(authToken: string, days: number) {
      try {
        const data = await getJson<HistoryResponse>(
          `/api/v1/market-data/upstox/candles?symbol=${symbol}&days=${days}`,
          authToken,
          signal,
        );
        if (signal.aborted) return;
        if (data.timeframe !== "15m" || !Array.isArray(data.candles)) {
          throw new Error("Upstox did not return a readable 15-minute candle list.");
        }
        setHistorySnapshot({ scope, data });
        setHistoryFailure(null);
      } catch (reason) {
        if (signal.aborted) return;
        if (reason instanceof MarketAccessError) {
          controller.abort();
          await signOut();
          return;
        }
        setHistoryFailure({ scope, message: reason instanceof Error ? reason.message : "Could not load Upstox history." });
      }
    }

    void refresh(token);
    if (historyDays !== null) void loadHistory(token, historyDays);
    const timer = window.setInterval(() => void refresh(token), 15000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [scope, signOut, validSymbol]);

  const liveError = liveFailure?.scope === scope ? liveFailure.message : null;
  const historyError = historyFailure?.scope === scope ? historyFailure.message : null;
  const live = !liveError && liveSnapshot?.scope === scope ? liveSnapshot : null;
  const history = historySnapshot?.scope === scope ? historySnapshot.data : undefined;
  const liveCandles = live?.candles ?? emptyCandles;
  const candles = useMemo(() => mergeChartCandles(history, liveCandles), [history, liveCandles]);
  const chartSignals = useMemo(() => {
    const byTimestamp = new Map<number, SignalPoint>();
    for (const point of history?.signals ?? []) byTimestamp.set(Date.parse(point.timestamp), point);
    for (const point of live?.signalHistory ?? []) byTimestamp.set(Date.parse(point.timestamp), point);
    return Array.from(byTimestamp.values());
  }, [history, live]);
  const decision = live?.decision ?? emptyDecision;
  const quote = live?.quote ?? null;
  const feedState = liveError ? "unavailable" : live?.feedState ?? "checking";
  const checkedAt = live?.checkedAt ?? null;
  const loading = !liveError && !live;
  const loadingHistory = historyDays !== null && !history && !historyError;
  const latestConfirmed = candles.findLast((candle) => !candle.is_forming && !candle.is_incomplete);
  const maxOffset = Math.max(0, candles.length - visibleCount);
  const offset = position?.scope === scope ? Math.min(position.offset, maxOffset) : 0;
  const decisionColor = decision.decision === "BUY"
    ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300"
    : decision.decision === "SELL"
      ? "border-rose-400/30 bg-rose-400/10 text-rose-300"
      : "border-white/10 bg-white/[0.03] text-slate-300";
  const signalLabel = decision.is_current_signal
    ? "Current confirmed signal"
    : decision.decision === "DATA_UNAVAILABLE"
      ? "Signal unavailable"
      : decision.decision === "WAIT" ? "Based on confirmed candle data" : "Previous confirmed signal";

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
            <p className="mt-1 text-sm text-slate-400">15-minute price chart · Confirmed signal analysis</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <label htmlFor="chart-provider" className="text-sm text-slate-400">Market data</label>
            <select id="chart-provider" value={provider} onChange={(event) => {
              const next = event.target.value;
              if (next === "groww" || next === "upstox") setMarketProvider(next);
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
            <p className="mt-1 text-xs text-slate-500">{quote?.timestamp
              ? `${timeLabel(quote.timestamp)} IST`
              : latestConfirmed ? `Candle close · ${timeLabel(latestConfirmed.timestamp)} IST` : "No recent quote"}</p>
          </div>
          <div className={`rounded-xl border p-4 ${decisionColor}`}>
            <p className="text-xs uppercase tracking-wide opacity-70">Signal</p>
            <p className="mt-2 text-2xl font-bold">{decision.decision}</p>
            <p className="mt-1 text-xs opacity-80">{signalLabel}</p>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <p className="text-xs uppercase tracking-wide text-slate-500">Confirmed bars</p>
            <p className="mt-2 text-2xl font-semibold tabular-nums">{decision.confirmed_candle_count}</p>
            <p className="mt-1 text-xs text-slate-500">Closed 15-minute candles used for signal checks</p>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <p className="text-xs uppercase tracking-wide text-slate-500">Updated</p>
            <p className="mt-2 text-lg font-semibold">{checkedAt
              ? checkedAt.toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" })
              : liveError ? "Unavailable" : "Connecting…"}</p>
            <p className="mt-1 text-xs text-slate-500">Refreshes every 15 seconds · IST</p>
          </div>
        </section>

        {liveError && <div role="alert" className="rounded-lg border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-200">
          Live refresh failed. {liveError}
        </div>}
        {loading && <p role="status" className="text-sm text-slate-400">Loading 15-minute market data…</p>}
        {live?.message && <p className="text-sm text-slate-400">{live.message}</p>}
        {historyDays !== null && <p className="text-sm text-slate-400">
          Upstox history · {historyDays === 1 ? "Today" : `Last ${historyDays} days`}
          {history && ` · ${history.message}`}
        </p>}
        {loadingHistory && <p role="status" className="text-sm text-slate-400">Loading Upstox history…</p>}
        {historyError && <p role="alert" className="text-sm text-rose-300">Upstox history could not be loaded. {historyError}</p>}

        <CandlestickPanel
          candles={candles}
          visibleCount={visibleCount}
          offset={offset}
          decision={decision}
          signalHistory={chartSignals}
          onZoomIn={() => setVisibleCount((count) => Math.max(20, count - 20))}
          onZoomOut={() => setVisibleCount((count) => Math.min(300, count + 20))}
          onOlder={() => setPosition({ scope, offset: Math.min(maxOffset, offset + visibleCount) })}
          onNewer={() => setPosition({ scope, offset: Math.max(0, offset - visibleCount) })}
          onLatest={() => setPosition({ scope, offset: 0 })}
        />

        <section className="rounded-xl border border-white/10 bg-white/[0.03] p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="font-semibold">Signal confirmation checks</h2>
              <p className="mt-1 text-xs text-slate-500">Calculated from complete, confirmed 15-minute candles. Forming candles are excluded.</p>
            </div>
            <span className="text-xs text-slate-500">{decision.candle_timestamp ? `Evaluated ${timeLabel(decision.candle_timestamp)} IST` : "Waiting for confirmed data"}</span>
          </div>
          <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
            {[
              ["Primary trigger", decision.ut_bot_signal ?? "No signal", decision.ut_bot_signal === "BUY" ? "text-emerald-300" : decision.ut_bot_signal === "SELL" ? "text-rose-300" : "text-slate-500"],
              ["Trend check A", voteLabel(decision.ema_bullish), voteStyle(decision.ema_bullish)],
              ["Momentum check A", voteLabel(decision.rsi_bullish), voteStyle(decision.rsi_bullish)],
              ["Momentum check B", voteLabel(decision.macd_bullish), voteStyle(decision.macd_bullish)],
              ["Trend check B", voteLabel(decision.supertrend_bullish), voteStyle(decision.supertrend_bullish)],
            ].map(([name, value, style]) => (
              <div key={name} className="rounded-lg border border-white/10 bg-slate-950/70 px-3 py-3">
                <p className="text-xs text-slate-500">{name}</p>
                <p className={`mt-1 text-sm font-medium ${style}`}>{value}</p>
              </div>
            ))}
          </div>
          <p className="mt-4 text-sm leading-relaxed text-slate-400">
            {liveError ? "Signal checks are unavailable until the live data request succeeds." : decision.reason}
          </p>
        </section>

        <footer className="border-t border-white/10 pt-3 text-xs leading-relaxed text-slate-500">
          Educational market analysis only; not investment advice. Signals follow fixed rules, may be delayed or wrong, and do not place orders.
        </footer>
      </div>
    </main>
  );
}
