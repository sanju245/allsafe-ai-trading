"use client";

import { useCallback, useEffect, useState } from "react";

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
};
type QuoteResponse = {
  available: boolean;
  quote: { ltp: number; timestamp: string } | null;
};
type FormingResponse = {
  available: boolean;
  forming_candle: Candle | null;
};
type InstrumentStatus = { feed_state: string };
type StatusResponse = {
  feed_state: string;
  streaming_enabled: boolean;
  connected: boolean;
  session_open: boolean;
  last_error: string | null;
  instruments: Record<string, InstrumentStatus>;
};
type MarketSnapshot = {
  candles: Candle[];
  quote: QuoteResponse["quote"];
  message: string;
  loading: boolean;
  error: string | null;
};

const markets: { symbol: MarketSymbol; title: string }[] = [
  { symbol: "NIFTY50", title: "NIFTY 50" },
  { symbol: "BANKNIFTY", title: "BANK NIFTY" },
];

const emptyMarket: MarketSnapshot = {
  candles: [],
  quote: null,
  message: "",
  loading: true,
  error: null,
};

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { cache: "no-store" });
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

function CandlestickChart({ candles, label }: { candles: Candle[]; label: string }) {
  const width = 720;
  const height = 260;
  const inset = 20;

  if (candles.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-lg border border-dashed border-white/10 px-6 text-center text-sm text-slate-400">
        No 5-minute candles are available yet. Live candles appear during NSE
        market hours once Groww sends an update.
      </div>
    );
  }

  const visible = candles.slice(-60);
  const min = Math.min(...visible.map((candle) => candle.low));
  const max = Math.max(...visible.map((candle) => candle.high));
  const range = Math.max(max - min, Math.abs(max) * 0.0001, 1);
  const plotHeight = height - inset * 2;
  const slotWidth = (width - inset * 2) / visible.length;
  const y = (price: number) => inset + ((max - price) / range) * plotHeight;

  return (
    <div className="overflow-hidden rounded-lg border border-white/10 bg-slate-950/60">
      <svg
        className="block h-64 w-full"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${label} 5-minute candlestick chart`}
        preserveAspectRatio="none"
      >
        {[0, 0.5, 1].map((fraction) => {
          const gridY = inset + fraction * plotHeight;
          const value = max - fraction * range;
          return (
            <g key={fraction}>
              <line x1={inset} x2={width - inset} y1={gridY} y2={gridY} stroke="#243142" strokeDasharray="3 5" />
              <text x={width - inset} y={gridY - 4} textAnchor="end" fill="#94a3b8" fontSize="10">
                {formatPrice(value)}
              </text>
            </g>
          );
        })}
        {visible.map((candle, index) => {
          const x = inset + index * slotWidth + slotWidth / 2;
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
      </svg>
    </div>
  );
}

function MarketCard({
  title,
  snapshot,
  feedState,
}: {
  title: string;
  snapshot: MarketSnapshot;
  feedState: string;
}) {
  const forming = snapshot.candles.find((candle) => candle.is_forming);
  const latestConfirmed = [...snapshot.candles].reverse().find((candle) => !candle.is_forming);
  const price = snapshot.quote?.ltp ?? forming?.close ?? latestConfirmed?.close;
  const stateLabel = feedState.replaceAll("_", " ");

  return (
    <section className="rounded-xl border border-white/10 bg-white/[0.03] p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{title}</h2>
          <p className="mt-1 text-xs capitalize text-slate-400">
            Feed: {stateLabel || "checking"}
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs uppercase tracking-wide text-slate-400">Latest price</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">{formatPrice(price)}</p>
          {snapshot.quote?.timestamp && (
            <p className="mt-1 text-xs text-slate-500">
              Updated {new Date(snapshot.quote.timestamp).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" })} IST
            </p>
          )}
        </div>
      </div>

      <div className="mt-5">
        <CandlestickChart candles={snapshot.candles} label={title} />
      </div>

      {snapshot.error && <p className="mt-3 text-sm text-rose-300">{snapshot.error}</p>}
      {snapshot.message && !snapshot.error && (
        <p className="mt-3 text-sm text-slate-400">{snapshot.message}</p>
      )}
      {snapshot.loading && <p className="mt-3 text-xs text-slate-500">Loading market data…</p>}
      {forming && <p className="mt-2 text-xs text-amber-300">The latest candle is still forming.</p>}
    </section>
  );
}

export default function LiveMarketDashboard() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [marketsState, setMarketsState] = useState<Record<MarketSymbol, MarketSnapshot>>({
    NIFTY50: emptyMarket,
    BANKNIFTY: emptyMarket,
  });
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);

  const refresh = useCallback(async () => {
    try {
      const latestStatus = await getJson<StatusResponse>("/api/live/status");
      setStatus(latestStatus);
    } catch {
      setStatus(null);
    }

    await Promise.all(markets.map(async ({ symbol }) => {
      const query = `?symbol=${symbol}`;
      try {
        const [candleResponse, quoteResponse, formingResponse] = await Promise.all([
          getJson<CandleResponse>(`/api/live/candles${query}`),
          getJson<QuoteResponse>(`/api/live/quote${query}`),
          getJson<FormingResponse>(`/api/live/forming-candle${query}`),
        ]);
        const candles = [...candleResponse.candles];
        if (formingResponse.forming_candle) {
          candles.push({ ...formingResponse.forming_candle, is_forming: true });
        }
        const uniqueCandles = Array.from(
          new Map(candles.map((candle) => [candle.timestamp, candle])).values(),
        ).sort((left, right) => left.timestamp.localeCompare(right.timestamp));
        setMarketsState((current) => ({
          ...current,
          [symbol]: {
            candles: uniqueCandles,
            quote: quoteResponse.quote,
            message: candleResponse.message,
            loading: false,
            error: null,
          },
        }));
      } catch (error) {
        setMarketsState((current) => ({
          ...current,
          [symbol]: {
            ...current[symbol],
            loading: false,
            error: error instanceof Error ? error.message : "Could not load market data.",
          },
        }));
      }
    }));
    setCheckedAt(new Date());
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 15000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const backendMessage = !status
    ? "Waiting for the live-data service."
    : status.last_error
      ? `Groww reports: ${status.last_error}`
      : !status.session_open
        ? "NSE is currently closed. Live updates resume during regular market hours."
        : status.connected
          ? "Groww is connected. Prices refresh automatically."
          : "Groww is not connected yet.";

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-slate-300">{backendMessage}</p>
          <p className="text-xs text-slate-500">
            {checkedAt ? `Checked ${checkedAt.toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" })} IST · refreshes every 15 seconds` : "Connecting…"}
          </p>
        </div>
      </div>
      <div className="grid gap-4">
        {markets.map(({ symbol, title }) => (
          <MarketCard
            key={symbol}
            title={title}
            snapshot={marketsState[symbol]}
            feedState={status?.instruments?.[symbol]?.feed_state ?? status?.feed_state ?? "checking"}
          />
        ))}
      </div>
      <p className="text-xs text-slate-500">
        Charts use Groww market data and show 5-minute candles. Educational analysis only;
        no orders are placed by this site.
      </p>
    </div>
  );
}
