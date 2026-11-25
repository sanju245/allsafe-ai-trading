"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/components/auth/AuthProvider";
import type { Signal } from "@/lib/indexChart";
import CandleSignalLabels from "./CandleSignalLabels";

type MarketSymbol = "NIFTY50" | "BANKNIFTY";
type Candle = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  is_forming: boolean;
  source?: { kind?: string; name?: string } | null;
};
type CandleResponse = {
  candles: Candle[];
  feed_state: string;
  message: string;
  indicator_decision: IndicatorDecision;
  indicator_history?: Signal[];
};
type IndicatorDecision = {
  decision: "BUY" | "SELL" | "WAIT" | "DATA_UNAVAILABLE";
  is_current_signal: boolean;
  candle_timestamp: string | null;
  reason: string;
  ut_bot_signal: string | null;
  ema_bullish: boolean | null;
  rsi_bullish: boolean | null;
  macd_bullish: boolean | null;
  supertrend_bullish: boolean | null;
};
type QuoteResponse = {
  available: boolean;
  feed_state: string;
  is_stale: boolean;
  quote: { ltp: number; timestamp: string } | null;
};
type FormingResponse = {
  available: boolean;
  forming_candle: Candle | null;
};
type InstrumentStatus = { feed_state: string };
type StatusResponse = {
  feed_state: string;
  provider: string;
  streaming_enabled: boolean;
  connected: boolean;
  session_open: boolean;
  last_error: string | null;
  instruments: Record<string, InstrumentStatus>;
};
type ProviderOption = {
  id: "groww" | "upstox";
  label: string;
  configured: boolean;
  feed_state: string;
  connected: boolean;
  message: string;
};
type ProviderResponse = { providers: ProviderOption[] };
type MarketSnapshot = {
  candles: Candle[];
  signals: Signal[];
  decision: IndicatorDecision | null;
  quote: QuoteResponse["quote"];
  message: string;
  loading: boolean;
  error: string | null;
  current: boolean;
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

const emptyMarket: MarketSnapshot = {
  candles: [],
  signals: [],
  decision: null,
  quote: null,
  message: "",
  loading: true,
  error: null,
  current: false,
  feedState: "checking",
};

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

function formatPrice(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function CandlestickChart({ candles, signals, label }: { candles: Candle[]; signals: Signal[]; label: string }) {
  const width = 720;
  const height = 260;
  const inset = 20;

  if (candles.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-lg border border-dashed border-ui-line px-6 text-center text-sm text-ui-muted">
        No validated 15-minute candles are available. Check the feed status and account-service connection.
      </div>
    );
  }

  const visible = candles.slice(-60);
  const min = Math.min(...visible.map((candle) => candle.low));
  const max = Math.max(...visible.map((candle) => candle.high));
  const range = Math.max(max - min, Math.abs(max) * 0.0001, 1);
  const plotHeight = height - inset * 2;
  const plotRight = width - 92;
  const slotWidth = (plotRight - inset) / visible.length;
  const slotX = (index: number) => inset + (index + 0.5) * slotWidth;
  const y = (price: number) => inset + ((max - price) / range) * plotHeight;

  return (
    <div className="overflow-hidden rounded-lg border border-ui-line bg-[#102820]">
      <svg
        className="block h-64 w-full"
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
              <line x1={inset} x2={plotRight} y1={gridY} y2={gridY} stroke="#243142" strokeDasharray="3 5" />
              <text x={width - 12} y={gridY + 4} textAnchor="end" fill="#adbed2" fontSize="13">
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
      </svg>
    </div>
  );
}

function MarketCard({
  chartHref,
  title,
  snapshot,
  feedState,
}: {
  chartHref: string;
  title: string;
  snapshot: MarketSnapshot;
  feedState: string;
}) {
  const forming = snapshot.candles.find((candle) => candle.is_forming);
  const latestConfirmed = [...snapshot.candles].reverse().find((candle) => !candle.is_forming);
  const price = snapshot.quote?.ltp ?? forming?.close ?? latestConfirmed?.close;
  const stateLabel = (snapshot.error ? "unavailable" : snapshot.feedState || feedState).replaceAll("_", " ");
  const decision = snapshot.decision;
  const signalStyle = decision?.decision === "BUY"
    ? "as-pill--green"
    : decision?.decision === "SELL"
      ? "as-pill--red"
      : "";
  const signalLabel = snapshot.current && decision?.is_current_signal
    ? "Current confirmed signal"
    : decision?.decision === "BUY" || decision?.decision === "SELL"
      ? "Previous confirmed signal"
      : "Signal from confirmed candles";

  return (
    <section className="as-panel market-index-card p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="as-section-title">
            <Link href={chartHref} target="_blank" rel="noopener noreferrer" className="rounded underline-offset-4 hover:text-ui-green hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400">
              {title}<span className="ml-2 text-xs text-ui-green" aria-label="opens chart in a new tab">↗</span>
            </Link>
          </h2>
          <p className="as-pill mt-2 capitalize">
            Feed: {stateLabel || "checking"}
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs uppercase tracking-wide text-ui-muted">
            {snapshot.error ? "Price unavailable" : snapshot.current ? "Latest validated price" : "Last recorded price · not current"}
          </p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">{formatPrice(price)}</p>
          {snapshot.quote?.timestamp && (
            <p className="mt-1 text-xs text-ui-muted">
              Recorded {new Date(snapshot.quote.timestamp).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })} IST
            </p>
          )}
        </div>
      </div>

      <div className="mt-5">
        <CandlestickChart candles={snapshot.candles} signals={snapshot.signals} label={title} />
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`as-pill ${signalStyle}`}>
            {decision?.decision ?? "SIGNAL PENDING"}
          </span>
          <span className="text-xs text-ui-muted">
            {signalLabel}
          </span>
        </div>
        <Link
          href={chartHref}
          target="_blank"
          rel="noopener noreferrer"
          className="as-button as-button--quiet"
        >
          Open full chart <span aria-hidden="true" className="ml-2">↗</span>
        </Link>
      </div>
      {decision && <p className="mt-2 text-xs text-ui-muted">{decision.reason}</p>}

      {snapshot.error && <p className="mt-3 text-sm text-ui-red">{snapshot.error}</p>}
      {snapshot.message && !snapshot.error && (
        <p className="mt-3 text-sm text-ui-muted">{snapshot.message}</p>
      )}
      {snapshot.loading && <p className="mt-3 text-xs text-ui-muted">Loading market data…</p>}
      {!snapshot.loading && !snapshot.current && !snapshot.error && snapshot.candles.length > 0 && (
        <p className="mt-2 text-xs text-ui-amber">Historical candles are shown. This feed is not current.</p>
      )}
      {forming && <p className="mt-2 text-xs text-ui-amber">The latest candle is still forming.</p>}
    </section>
  );
}

export default function LiveMarketDashboard() {
  const { session, signOut } = useAuth();
  const accessToken = session?.access_token;
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [providers, setProviders] = useState<ProviderOption[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<"groww" | "upstox">("groww");
  const [marketsState, setMarketsState] = useState<Record<MarketSymbol, MarketSnapshot>>({
    NIFTY50: emptyMarket,
    BANKNIFTY: emptyMarket,
  });
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);
  const activeRefresh = useRef<AbortSignal | null>(null);
  const refreshController = useRef<AbortController | null>(null);
  const hasProviderPreference = useRef(false);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem("allsafe-market-provider");
      if (saved === "groww" || saved === "upstox") {
        hasProviderPreference.current = true;
        setSelectedProvider(saved);
      }
    } catch {
      // Customers can still select a provider when browser storage is unavailable.
    }
  }, []);

  const selectProvider = (provider: "groww" | "upstox") => {
    hasProviderPreference.current = true;
    if (provider === selectedProvider) return;
    refreshController.current?.abort();
    setSelectedProvider(provider);
    try {
      window.localStorage.setItem("allsafe-market-provider", provider);
    } catch {
      // Chart links preserve the selection independently of browser storage.
    }
    setStatus(null);
    setMarketsState({ NIFTY50: emptyMarket, BANKNIFTY: emptyMarket });
    setCheckedAt(null);
  };

  const refresh = useCallback(async (signal: AbortSignal) => {
    if (!accessToken || signal.aborted || (activeRefresh.current && !activeRefresh.current.aborted)) return;
    activeRefresh.current = signal;
    try {
      const [latestStatus, providerResponse] = await Promise.all([
        getJson<StatusResponse>(`/api/v1/live/status?provider=${selectedProvider}`, accessToken, signal),
        getJson<ProviderResponse>("/api/v1/live/providers", accessToken, signal),
      ]);
      if (!signal.aborted) {
        setProviders(providerResponse.providers);
        const usable = (p: ProviderOption) => p.configured && ["live", "closed"].includes(p.feed_state);
        const selected = providerResponse.providers.find(p => p.id === selectedProvider);
        const alternative = providerResponse.providers.find(p => p.id !== selectedProvider && usable(p));
        if (!hasProviderPreference.current && (!selected || !usable(selected)) && alternative) {
          setStatus(null);
          setMarketsState({ NIFTY50: emptyMarket, BANKNIFTY: emptyMarket });
          setCheckedAt(null);
          activeRefresh.current = null;
          setSelectedProvider(alternative.id);
          return;
        }
        setStatus(latestStatus);
      }
    } catch (error) {
      if (signal.aborted) return;
      setStatus(null);
      if (error instanceof MarketAccessError) {
        await signOut();
        activeRefresh.current = null;
        return;
      }
    }

    await Promise.all(markets.map(async ({ symbol }) => {
      const query = `?symbol=${symbol}&provider=${selectedProvider}`;
      try {
        const [candleResponse, quoteResponse, formingResponse] = await Promise.all([
          getJson<CandleResponse>(`/api/v1/live/candles${query}&timeframe=15m&limit=500&history_days=7&include_indicator_history=true`, accessToken, signal),
          getJson<QuoteResponse>(`/api/v1/live/quote${query}`, accessToken, signal),
          getJson<FormingResponse>(`/api/v1/live/forming-candle${query}`, accessToken, signal),
        ]);
        if (signal.aborted) return;
        const isCurrent = quoteResponse.available && quoteResponse.feed_state === "live" && !quoteResponse.is_stale;
        const candles = [...candleResponse.candles];
        if (isCurrent && formingResponse.available && formingResponse.forming_candle) {
          candles.push({ ...formingResponse.forming_candle, is_forming: true });
        }
        const uniqueCandles = Array.from(
          new Map(candles.map((candle) => [candle.timestamp, candle])).values(),
        ).sort((left, right) => left.timestamp.localeCompare(right.timestamp));
        setMarketsState((current) => ({
          ...current,
          [symbol]: {
            candles: uniqueCandles,
            signals: candleResponse.indicator_history ?? [],
            decision: candleResponse.indicator_decision,
            quote: quoteResponse.quote,
            message: candleResponse.message,
            loading: false,
            error: null,
            current: isCurrent,
            feedState: quoteResponse.feed_state || candleResponse.feed_state,
          },
        }));
      } catch (error) {
        if (signal.aborted) return;
        if (error instanceof MarketAccessError) {
          await signOut();
          return;
        }
        setMarketsState((current) => ({
          ...current,
          [symbol]: {
            ...current[symbol],
            candles: [],
            signals: [],
            decision: null,
            quote: null,
            message: "",
            current: false,
            feedState: "unavailable",
            loading: false,
            error: error instanceof Error ? error.message : "Could not load market data.",
          },
        }));
      }
    }));
    if (!signal.aborted) setCheckedAt(new Date());
    if (activeRefresh.current === signal) activeRefresh.current = null;
  }, [accessToken, selectedProvider, signOut]);

  useEffect(() => {
    if (!accessToken) return;
    const controller = new AbortController();
    refreshController.current = controller;
    void refresh(controller.signal);
    const timer = window.setInterval(() => void refresh(controller.signal), 15000);
    return () => {
      controller.abort();
      if (refreshController.current === controller) refreshController.current = null;
      window.clearInterval(timer);
    };
  }, [accessToken, refresh]);

  const backendMessage = !status
    ? "Waiting for the live-data service."
    : !providers.find((provider) => provider.id === selectedProvider)?.configured
      ? `${selectedProvider === "groww" ? "Groww" : "Upstox"} is not configured for this platform yet. No live prices are being shown.`
      : status.last_error
        ? `${selectedProvider === "groww" ? "Groww" : "Upstox"} reports: ${status.last_error}`
        : !status.session_open
          ? "NSE is currently closed. Available data is historical."
          : status.connected && status.feed_state === "live"
            ? `${selectedProvider === "groww" ? "Groww" : "Upstox"} is connected. Prices refresh automatically.`
            : `The live feed is ${status.feed_state.replaceAll("_", " ")}. Displayed history is not current.`;

  return (
    <div className="space-y-4">
      <div className="as-panel market-feed-bar px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-3">
            <label htmlFor="market-data-provider" className="text-sm text-ui-muted">Market data</label>
            <select
              id="market-data-provider"
              value={selectedProvider}
              onChange={(event) => selectProvider(event.target.value as "groww" | "upstox")}
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
            {checkedAt ? `Checked ${checkedAt.toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" })} IST · refreshes every 15 seconds` : "Connecting…"}
          </p>
        </div>
      </div>
      <div className="market-index-grid">
        {markets.map(({ symbol, title }) => (
          <MarketCard
            key={symbol}
            chartHref={`/chart/${symbol}?provider=${selectedProvider}`}
            title={title}
            snapshot={marketsState[symbol]}
            feedState={status?.instruments?.[symbol]?.feed_state ?? status?.feed_state ?? "checking"}
          />
        ))}
      </div>
    </div>
  );
}
