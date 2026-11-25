export type RawCandle = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  is_forming?: boolean;
  is_confirmed?: boolean;
  is_incomplete?: boolean;
};

export type Bar = { time: number; open: number; high: number; low: number; close: number };
export type Side = "BUY" | "SELL";
export type SignalLevels = { entry: number; stop_loss: number; target: number };
export type Signal = { timestamp: string; decision: Side | "WAIT" | "DATA_UNAVAILABLE"; levels?: SignalLevels | null };
export type ChartMark = { time: number; side: Side; price: number; levels?: SignalLevels };

const openingRangeLabels = {
  MISSING: "Opening candle missing",
  SET: "Range established",
  INSIDE: "Close inside range",
  ABOVE_HIGH: "Close above high",
  BELOW_LOW: "Close below low",
};
const trendPositionLabels = { [-1]: "Bearish", 0: "Neutral", 1: "Bullish" };

export type Decision = {
  decision: Signal["decision"];
  is_current_signal: boolean;
  candle_timestamp: string | null;
  reason: string;
  confirmed_candle_count: number;
  ut_bot_signal: string | null;
  opening_range_state?: keyof typeof openingRangeLabels | null;
  ut_bot_position?: keyof typeof trendPositionLabels | null;
  opening_range_high?: number | null;
  opening_range_low?: number | null;
  first_breakout?: { timestamp: string; side: Side; decision: Signal["decision"]; reason: string } | null;
  ema_bullish: boolean | null;
  rsi_bullish: boolean | null;
  macd_bullish: boolean | null;
  supertrend_bullish: boolean | null;
};
export type SeriesSnapshot = {
  candles: RawCandle[];
  heikin_ashi_previous_open_close?: [number, number] | null;
  indicator_history: Signal[];
  indicator_decision: Decision;
  history_warning?: string | null;
  feed_state: string;
  is_stale: boolean;
  checked_at: string;
};
export type QuoteSnapshot = {
  available: boolean;
  feed_state: string;
  is_stale: boolean;
  quote: { ltp: number; timestamp: string } | null;
  forming_candle?: RawCandle | null;
  checked_at: string;
};

const priceFormat = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const stampFormat = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
export const formatPrice = (price: number) => priceFormat.format(price);
export const formatStamp = (seconds: number) => stampFormat.format(seconds * 1000);
export const epoch = (stamp: string) => Math.floor(Date.parse(stamp) / 1000);
export const slotAt = (stamp: string) => Math.floor(epoch(stamp) / 900) * 900;

export function decisionChecks(decision?: Decision): [label: string, reading: string][] {
  const state = decision?.opening_range_state;
  const position = decision?.ut_bot_position;
  const direction = (bullish?: boolean | null) => {
    if (bullish === true) return "Bullish";
    if (bullish === false) return "Bearish";
    return bullish === null && decision?.decision !== "DATA_UNAVAILABLE" ? "Neutral" : "No reading";
  };
  return [
    ["09:15 IST opening range", state ? openingRangeLabels[state] : "No reading"],
    ["Trend position", position == null ? "No reading" : trendPositionLabels[position]],
    ["Trend check A", direction(decision?.ema_bullish)],
    ["Momentum check A", direction(decision?.rsi_bullish)],
    ["Momentum check B", direction(decision?.macd_bullish)],
    ["Trend check B", direction(decision?.supertrend_bullish)],
  ];
}

export function heikinAshiBar(c: RawCandle, previous?: Pick<Bar, "open" | "close">): Bar | null {
  const time = epoch(c.timestamp);
  if (![time, c.open, c.high, c.low, c.close].every(Number.isFinite) ||
      c.low <= 0 || c.low > Math.min(c.open, c.close) || c.high < Math.max(c.open, c.close)) return null;
  const close = (c.open + c.high + c.low + c.close) / 4;
  const open = previous ? (previous.open + previous.close) / 2 : (c.open + c.close) / 2;
  return { time, open, close, high: Math.max(c.high, open, close), low: Math.min(c.low, open, close) };
}

export function chartHistory(series?: SeriesSnapshot) {
  const bars: Bar[] = [];
  const byTime = new Map<number, Bar>();
  const marks: ChartMark[] = [];
  const seed = series?.heikin_ashi_previous_open_close;
  let previous = seed ? { open: seed[0], close: seed[1] } : undefined;
  // The API returns an ordered, de-duplicated window. A partial close never
  // becomes a confirmed chart candle or feeds the next averaged open.
  for (const c of series?.candles ?? []) {
    if (c.is_forming || c.is_confirmed === false || c.is_incomplete) continue;
    const bar = heikinAshiBar(c, previous);
    if (!bar || (bars.length && bar.time <= bars[bars.length - 1].time)) continue;
    bars.push(bar);
    byTime.set(bar.time, bar);
    previous = bar;
  }
  const marked = new Set<number>();
  for (const signal of series?.indicator_history ?? []) {
    const side = signal.decision;
    if (side !== "BUY" && side !== "SELL") continue;
    const time = epoch(signal.timestamp);
    const bar = byTime.get(time);
    if (!bar || marked.has(time)) continue;
    const mark: ChartMark = { time, side, price: side === "BUY" ? bar.low : bar.high };
    const levels = signal.levels;
    if (levels && [levels.entry, levels.stop_loss, levels.target].every(p => Number.isFinite(p) && p > 0) &&
        (side === "BUY" ? levels.stop_loss < levels.entry && levels.entry < levels.target :
          levels.target < levels.entry && levels.entry < levels.stop_loss)) {
      mark.levels = levels;
    }
    marks.push(mark);
    marked.add(time);
  }
  return { bars, marks };
}

export function freshQuote(tick?: QuoteSnapshot) {
  return !!tick?.available && !!tick.quote && tick.feed_state === "live" && !tick.is_stale;
}

export function formingBar(tick?: QuoteSnapshot, previous?: Bar) {
  const c = tick?.forming_candle;
  if (!tick || !freshQuote(tick) || !c?.is_forming || c.is_confirmed ||
      epoch(c.timestamp) !== slotAt(tick.checked_at) || (previous && epoch(c.timestamp) <= previous.time)) return null;
  // A feed that first connected mid-slot has no reliable open or extremes.
  if (c.is_incomplete) return null;
  return heikinAshiBar(c, previous);
}

export function currentSignal(series?: SeriesSnapshot, tick?: QuoteSnapshot) {
  const decision = series?.indicator_decision;
  return !!(tick && series && freshQuote(tick) && series.feed_state === "live" && !series.is_stale &&
    decision?.is_current_signal && decision.candle_timestamp &&
    (decision.decision === "BUY" || decision.decision === "SELL") &&
    epoch(decision.candle_timestamp) === slotAt(tick.checked_at) - 900);
}
