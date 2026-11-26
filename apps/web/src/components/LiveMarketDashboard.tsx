"use client";

import { memo, useEffect, useRef, useState, type RefObject } from "react";
import Link from "next/link";
import { useAuth } from "@/components/auth/AuthProvider";
import { currentSignal, epoch, formatPrice as formatIndexPrice, freshQuote, slotAt, type Decision, type QuoteSnapshot, type SeriesSnapshot, type Signal } from "@/lib/indexChart";
import CandleSignalLabels from "./CandleSignalLabels";

type MarketSymbol = "NIFTY50" | "BANKNIFTY";
type Provider = "groww" | "upstox";
type Candle = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  is_forming: boolean;
  source?: { kind?: string; name?: string } | null;
};
type CandleResponse = SeriesSnapshot & {
  candles: Candle[];
  message: string;
};
type QuoteResponse = QuoteSnapshot & { forming_candle?: Candle | null };
type OverviewResponse = {
  feed_state: string;
  connected: boolean;
  session_open: boolean;
  last_error: string | null;
  providers: ProviderOption[];
  quotes: Record<MarketSymbol, QuoteResponse>;
  checked_at: string;
};
type ProviderOption = {
  id: Provider;
  label: string;
  configured: boolean;
  feed_state: string;
};

type MarketSnapshot = {
  candles: Candle[];
  forming: Candle | null;
  signals: Signal[];
  decision?: Decision;
  quote: QuoteResponse["quote"];
  message?: string;
  loading: boolean;
  error?: string;
  current: boolean;
  isCurrentSignal: boolean;
  feedState: string;
};

const markets: { symbol: MarketSymbol; title: string }[] = [
  { symbol: "NIFTY50", title: "NIFTY 50" },
  { symbol: "BANKNIFTY", title: "BANK NIFTY" },
];

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  (process.env.NODE_ENV === "production"
    ? "https://allsafe-ai-api.onrender.com"
    : "http://localhost:8000")
)
  .trim()
  .replace(/\/+$/, "");

const emptyCandles: Candle[] = [];
const emptySignals: Signal[] = [];
const timeFormat = new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", timeStyle: "medium" });
const stampFormat = new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "short", timeStyle: "medium" });

function readProviderPreference(): Provider | null {
  try {
    const saved = window.localStorage.getItem("allsafe-market-provider");
    if (saved === "groww" || saved === "upstox") return saved;
  } catch {
    // The dashboard can still work without browser storage.
  }
  return null;
}

class MarketAccessError extends Error {}

async function getJson<T>(path: string, accessToken: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
    credentials: "omit",
    signal: AbortSignal.any([signal, AbortSignal.timeout(12000)]),
  });
  if (response.status === 401 || response.status === 403) {
    throw new MarketAccessError("Your account access has changed. Sign in again.");
  }
  if (!response.ok) throw new Error(`Market data request failed (HTTP ${response.status}).`);
  return response.json() as Promise<T>;
}

function formatPrice(value?: number) {
  return value === undefined ? "—" : formatIndexPrice(value);
}

const chartTime = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});

const CandlestickChart = memo(function CandlestickChart({ candles, forming, signals, label, width }: {
  candles: Candle[]; forming: Candle | null; signals: Signal[]; label: string; width: number;
}) {
  const height = 320;
  const inset = 28;

  if (candles.length === 0 && !forming) {
    return (
      <div className="flex h-64 items-center justify-center rounded-lg border border-dashed border-ui-line px-6 text-center text-sm text-ui-muted">
        No validated 15-minute candles are available. Check the feed status and account-service connection.
      </div>
    );
  }

  const plotRight = width - 83;
  const bars = Math.max(12, Math.min(60, Math.floor((plotRight - inset) / 10)));
  const replacesTail = forming && epoch(forming.timestamp) === epoch(candles.at(-1)?.timestamp ?? "");
  const visible = forming ? [...(replacesTail ? candles.slice(-bars, -1) : candles.slice(1 - bars)), forming] : candles.slice(-bars);
  const min = Math.min(...visible.map((candle) => candle.low));
  const max = Math.max(...visible.map((candle) => candle.high));
  const range = Math.max(max - min, Math.abs(max) * 0.0001, 1);
  const plotHeight = height - inset * 2 - 14;
  const slotWidth = (plotRight - inset) / visible.length;
  const slotX = (index: number) => inset + (index + 0.5) * slotWidth;
  const y = (price: number) => inset + ((max - price) / range) * plotHeight;
  const timeTicks = visible.length > 1
    ? [{ index: 0, x: inset, anchor: "start" }, { index: visible.length - 1, x: plotRight, anchor: "end" }] as const
    : [{ index: 0, x: inset, anchor: "start" }] as const;

  return (
    <div className="overflow-hidden rounded-lg border border-ui-line bg-[#102820]">
      <svg
        className="market-focused-svg block w-full"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${label} 15-minute candlestick chart`}
        preserveAspectRatio="none"
      >
        {[0, 0.5, 1].map((fraction) => {
          const gridY = inset + fraction * plotHeight;
          const value = max - fraction * range;
          return (
            <g key={fraction}>
              <line x1={inset} x2={plotRight} y1={gridY} y2={gridY} stroke="#37564a" strokeDasharray="3 5" />
              <text x={width - 12} y={gridY + 4} textAnchor="end" fill="#b9cdc4" fontSize="12">
                {formatPrice(value)}
              </text>
            </g>
          );
        })}
        {visible.map((candle, index) => {
          const x = slotX(index);
          const bullish = candle.close >= candle.open;
          const color = bullish ? "#34d399" : "#fb7185";
          const bodyTop = Math.min(y(candle.open), y(candle.close));
          const bodyHeight = Math.max(Math.abs(y(candle.open) - y(candle.close)), 1.5);
          const bodyWidth = Math.max(Math.min(slotWidth * 0.58, 12), 2);
          return (
            <g key={candle.timestamp} opacity={candle.is_forming ? 0.62 : 1}>
              <line x1={x} x2={x} y1={y(candle.high)} y2={y(candle.low)} stroke={color} strokeWidth="1.5" />
              <rect
                x={x - bodyWidth / 2}
                y={bodyTop}
                width={bodyWidth}
                height={bodyHeight}
                fill={bullish ? color : "#0b0f14"}
                stroke={color}
                strokeWidth="1.5"
                rx="1"
              />
            </g>
          );
        })}
        <CandleSignalLabels candles={visible} signals={signals} x={slotX} y={y} />
        {timeTicks.map(({ index, x, anchor }) => {
          const time = Date.parse(visible[index].timestamp);
          if (!Number.isFinite(time)) return null;
          return (
            <text key={index} x={x} y={height - 9} textAnchor={anchor} fill="#b9cdc4" fontSize="11">
              {chartTime.format(time)}
            </text>
          );
        })}
      </svg>
    </div>
  );
});

function readPrice(snapshot: MarketSnapshot) {
  return snapshot.quote?.ltp ?? snapshot.forming?.close ?? snapshot.candles.at(-1)?.close;
}

function priceLabel(snapshot: MarketSnapshot) {
  return readPrice(snapshot) === undefined ? "Price unavailable" : snapshot.current ? "Latest validated price" : "Last recorded price · not current";
}

function signalStyle(snapshot: MarketSnapshot) {
  if (!snapshot.isCurrentSignal) return "";
  return snapshot.decision?.decision === "BUY" ? "as-pill--green" : "as-pill--red";
}

function signalText(snapshot: MarketSnapshot) {
  const side = snapshot.decision?.decision;
  switch (side) {
    case "BUY":
      return "Buy";
    case "SELL":
      return "Sell";
    case "WAIT":
      return "Wait";
    case "DATA_UNAVAILABLE":
      return "Data unavailable";
    default:
      return snapshot.error ? "Signal unavailable" : "Signal pending";
  }
}

function FocusedMarketChart({
  chartHref,
  title,
  snapshot,
  plotRef,
  width,
}: {
  chartHref: string;
  title: string;
  snapshot: MarketSnapshot;
  plotRef: RefObject<HTMLDivElement | null>;
  width: number;
}) {
  const { forming } = snapshot;
  const price = readPrice(snapshot);
  const stateLabel = snapshot.feedState.replaceAll("_", " ");
  const decision = snapshot.decision;
  const signalLabel = snapshot.isCurrentSignal
    ? "Current confirmed signal"
    : decision?.decision === "BUY" || decision?.decision === "SELL"
      ? "Previous confirmed signal"
      : "Signal from confirmed candles";

  return (
    <section id="focused-market-chart" aria-labelledby="focused-market-title" className="as-panel market-focus">
      <header className="market-focus-header">
        <div>
          <p className="as-kicker">15-minute candles</p>
          <h2 id="focused-market-title" className="as-section-title mt-1">{title}</h2>
        </div>
        <Link href={chartHref} target="_blank" rel="noopener noreferrer" className="as-button as-button--primary">
          Open full chart <span aria-hidden="true">↗</span>
        </Link>
      </header>
      <div className="market-focus-grid">
        <div>
          <div ref={plotRef}>
            <CandlestickChart candles={snapshot.candles} forming={forming} signals={snapshot.signals} label={title} width={width} />
          </div>
          {forming && <p className="mt-2 text-xs text-ui-amber">The latest candle is still forming.</p>}
        </div>
        <aside className="market-focus-details" aria-label="Index price and signal">
          <span className="as-pill capitalize">Feed · {stateLabel || "checking"}</span>
          <div>
            <p className="text-xs font-medium text-ui-muted">{priceLabel(snapshot)}</p>
            <p className="market-focus-price tabular-nums">{formatPrice(price)}</p>
            {snapshot.quote?.timestamp && (
              <p className="mt-1 text-xs text-ui-muted">
                Recorded {stampFormat.format(new Date(snapshot.quote.timestamp))} IST
              </p>
            )}
          </div>
          <div className="market-focus-decision">
            <p className="text-xs font-medium text-ui-muted">{signalLabel}</p>
            <span className={`as-pill mt-2 ${signalStyle(snapshot)}`}>{signalText(snapshot)}</span>
            {decision && <p className="mt-2 text-xs leading-relaxed text-ui-muted">{decision.reason}</p>}
          </div>
          {snapshot.error && <p className="text-sm text-ui-red" role="alert">{snapshot.error}</p>}
          {snapshot.message && !snapshot.error && <p className="text-sm text-ui-muted">{snapshot.message}</p>}
          {snapshot.loading && <p className="text-xs text-ui-muted">Loading candle history…</p>}
          {!snapshot.loading && !snapshot.current && !snapshot.error && snapshot.candles.length > 0 && (
            <p className="text-xs text-ui-amber">Historical candles are shown. This feed is not current.</p>
          )}
        </aside>
      </div>
    </section>
  );
}

export default function LiveMarketDashboard() {
  const { session, signOut } = useAuth();
  const accessToken = session?.access_token;
  const [overview, setOverview] = useState<OverviewResponse>();
  const [overviewError, setOverviewError] = useState(false);
  const [preferredProvider, setPreferredProvider] = useState(readProviderPreference);
  const [automaticProvider, setAutomaticProvider] = useState<Provider>("groww");
  const selectedProvider = preferredProvider ?? automaticProvider;
  const [history, setHistory] = useState<Partial<Record<MarketSymbol, CandleResponse>>>({});
  const [historyErrors, setHistoryErrors] = useState<Partial<Record<MarketSymbol, string>>>({});
  const refreshController = useRef<AbortController | null>(null);

  const [focusedSymbol, setFocusedSymbol] = useState<MarketSymbol>("NIFTY50");
  const [plotWidth, setPlotWidth] = useState(720);
  const plotRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const plot = plotRef.current;
    if (!plot) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width > 0) setPlotWidth(Math.max(240, Math.round(entry.contentRect.width)));
    });
    observer.observe(plot);
    return () => observer.disconnect();
  }, []);

  const selectProvider = (provider: Provider) => {
    try {
      window.localStorage.setItem("allsafe-market-provider", provider);
    } catch {
      // Chart links preserve the selection independently of browser storage.
    }
    if (provider === selectedProvider) return;
    refreshController.current?.abort();
    setPreferredProvider(provider);
    setOverview(undefined);
    setOverviewError(false);
    setHistory({});
    setHistoryErrors({});
  };

  useEffect(() => {
    if (!accessToken) return;
    const token = accessToken;
    const controller = new AbortController();
    const { signal } = controller;
    refreshController.current = controller;
    const active = () => !signal.aborted && !document.hidden;
    let timer: ReturnType<typeof setTimeout>;
    let readingOverview = false;
    let readingHistory = false;
    let lastHistoryStart = 0;
    let lastHistorySlot: number | undefined;

    function accessChanged(error: unknown) {
      if (!(error instanceof MarketAccessError)) return false;
      controller.abort();
      void signOut();
      return true;
    }

    async function loadHistory(slot: number | undefined, sessionOpen: boolean) {
      const now = Date.now();
      const interval = sessionOpen ? 30000 : 60000;
      if (!active() || readingHistory || (slot === lastHistorySlot && now - lastHistoryStart < interval)) return;
      readingHistory = true;
      lastHistoryStart = now;
      lastHistorySlot = slot;
      try {
        await Promise.all(markets.map(async ({ symbol }) => {
          try {
            const data = await getJson<CandleResponse>(
              `/api/v1/live/candles?symbol=${symbol}&provider=${selectedProvider}&timeframe=15m&limit=60&history_days=7&include_indicator_history=true`,
              token, signal,
            );
            if (signal.aborted) return;
            setHistory((previous) => ({ ...previous, [symbol]: data }));
            setHistoryErrors((previous) => ({ ...previous, [symbol]: undefined }));
          } catch (error) {
            if (signal.aborted || accessChanged(error)) return;
            setHistoryErrors((previous) => ({
              ...previous,
              [symbol]: error instanceof Error ? error.message : "Could not load candle history.",
            }));
          }
        }));
      } finally {
        readingHistory = false;
      }
    }

    async function loadOverview() {
      if (!active() || readingOverview) return;
      readingOverview = true;
      let delay = 15000;
      try {
        const data = await getJson<OverviewResponse>(`/api/v1/live/overview?provider=${selectedProvider}`, token, signal);
        if (signal.aborted) return;
        const usable = (provider: ProviderOption) => provider.configured && ["live", "closed"].includes(provider.feed_state);
        const selected = data.providers.find((provider) => provider.id === selectedProvider);
        const alternative = data.providers.find((provider) => provider.id !== selectedProvider && usable(provider));
        if (!preferredProvider && (!selected || !usable(selected)) && alternative) {
          controller.abort();
          setOverview(undefined);
          setHistory({});
          setHistoryErrors({});
          setAutomaticProvider(alternative.id);
          return;
        }
        setOverview(data);
        setOverviewError(false);
        delay = data.session_open ? 15000 : 30000;
        void loadHistory(data.session_open ? slotAt(data.checked_at) : undefined, data.session_open);
      } catch (error) {
        if (signal.aborted || accessChanged(error)) return;
        setOverview(undefined);
        setOverviewError(true);
        setHistory({});
        setHistoryErrors({});
        lastHistoryStart = 0;
      } finally {
        readingOverview = false;
        if (active()) timer = setTimeout(loadOverview, delay);
      }
    }

    function refreshWhenVisible() {
      clearTimeout(timer);
      if (!active()) return;
      lastHistoryStart = 0;
      void loadOverview();
    }
    void loadOverview();
    document.addEventListener("visibilitychange", refreshWhenVisible);
    window.addEventListener("online", refreshWhenVisible);
    return () => {
      controller.abort();
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
      window.removeEventListener("online", refreshWhenVisible);
    };
  }, [accessToken, preferredProvider, selectedProvider, signOut]);

  const providerLabel = selectedProvider === "upstox" ? "Upstox" : "Groww";
  const providers = overview?.providers ?? [];
  const backendMessage = overviewError
    ? "The live-data service could not be reached. Retrying…"
    : !overview
      ? "Waiting for the live-data service."
      : !providers.find((provider) => provider.id === selectedProvider)?.configured
        ? `${providerLabel} is not configured for this platform yet. No live prices are being shown.`
        : overview.last_error
          ? `${providerLabel} reports: ${overview.last_error}`
          : !overview.session_open
            ? "NSE is currently closed. Available data is historical."
            : overview.connected && overview.feed_state === "live"
              ? `${providerLabel} is connected. Prices refresh automatically.`
              : `The live feed is ${overview.feed_state.replaceAll("_", " ")}. Displayed history is not current.`;

  function snapshotFor(symbol: MarketSymbol): MarketSnapshot {
    const series = overviewError ? undefined : history[symbol];
    const quote = overviewError ? undefined : overview?.quotes[symbol];
    const candles = series?.candles ?? emptyCandles;
    const latest = candles.at(-1);
    const current = freshQuote(quote);
    const forming = current && quote?.forming_candle && (!latest || epoch(quote.forming_candle.timestamp) >= epoch(latest.timestamp))
      ? quote.forming_candle : null;
    const error = overviewError ? undefined : historyErrors[symbol];
    return {
      candles, forming, current, error,
      signals: series?.indicator_history ?? emptySignals,
      decision: series?.indicator_decision,
      quote: quote?.quote ?? null,
      message: series?.message,
      loading: !overviewError && !series && !error,
      isCurrentSignal: !error && currentSignal(series, quote),
      feedState: overviewError ? "unavailable" : quote?.feed_state ?? series?.feed_state ?? "checking",
    };
  }

  return (
    <div className="space-y-4">
      <div className="as-panel market-feed-bar px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-3">
            <label htmlFor="market-data-provider" className="text-sm text-ui-muted">Market data</label>
            <select
              id="market-data-provider"
              value={selectedProvider}
              onChange={(event) => selectProvider(event.target.value as Provider)}
              className="as-field"
            >
              {(["groww", "upstox"] as const).map((id) => {
                const option = providers.find((item) => item.id === id);
                const state = option?.configured ? option.feed_state : "unavailable";
                const label = state === "closed" ? "market closed" : state === "failed" ? "unavailable" : state;
                return <option key={id} value={id}>{option?.label ?? (id === "groww" ? "Groww" : "Upstox")}{option && ` · ${label}`}</option>;
              })}
            </select>
            <p className="text-sm text-ui-muted">{backendMessage}</p>
          </div>
          <p className="text-xs text-ui-muted">
            {overview ? `Checked ${timeFormat.format(new Date(overview.checked_at))} IST` : overviewError ? "Retrying…" : "Connecting…"}
          </p>
        </div>
      </div>
      <div className="market-watchlist" aria-label="Index overview">
        {markets.map(({ symbol, title }) => {
          const snapshot = snapshotFor(symbol);
          const price = readPrice(snapshot);
          const selected = focusedSymbol === symbol;
          const previousSignal = (snapshot.decision?.decision === "BUY" || snapshot.decision?.decision === "SELL")
            && !snapshot.isCurrentSignal;
          return (
            <article key={symbol} className={`as-panel market-watch-tile${selected ? " market-watch-tile--selected" : ""}`}>
              <div className="min-w-0">
                <h2 className="font-semibold">
                  <Link href={`/chart/${symbol}?provider=${selectedProvider}`} target="_blank" rel="noopener noreferrer" className="as-link">
                    {title} <span aria-label="opens a new tab">↗</span>
                  </Link>
                </h2>
                <p className="market-watch-price tabular-nums">{formatPrice(price)}</p>
                <p className="text-xs text-ui-muted">{priceLabel(snapshot)}</p>
              </div>
              <div className="market-watch-actions">
                <span className={`as-pill ${signalStyle(snapshot)}`}>{previousSignal ? "Earlier " : ""}{signalText(snapshot)}</span>
                <button type="button" aria-pressed={selected} aria-controls="focused-market-chart"
                  aria-label={`Focus ${title} chart`} onClick={() => setFocusedSymbol(symbol)} className="as-button as-button--quiet">
                  {selected ? "In focus" : "Focus chart"}
                </button>
              </div>
            </article>
          );
        })}
      </div>
      <FocusedMarketChart
        chartHref={`/chart/${focusedSymbol}?provider=${selectedProvider}`}
        title={focusedSymbol === "NIFTY50" ? "NIFTY 50" : "BANK NIFTY"}
        snapshot={snapshotFor(focusedSymbol)}
        plotRef={plotRef}
        width={plotWidth}
      />
    </div>
  );
}
