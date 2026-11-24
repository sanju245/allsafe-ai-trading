"use client";

import { useEffect, useState } from "react";
import { epoch, slotAt, type QuoteSnapshot, type SeriesSnapshot } from "@/lib/indexChart";

const api = (process.env.NEXT_PUBLIC_API_BASE_URL ||
  (process.env.NODE_ENV === "production" ? "https://allsafe-ai-api.onrender.com" : "http://localhost:8000")
).trim().replace(/\/+$/, "");
class AccessChanged extends Error {}

async function read<T>(path: string, token: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(api + path, {
    headers: { Authorization: `Bearer ${token}` }, cache: "no-store", credentials: "omit",
    signal: AbortSignal.any([signal, AbortSignal.timeout(20000)]),
  });
  if (response.status === 401 || response.status === 403) throw new AccessChanged();
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json() as Promise<T>;
}

export function useIndexChart(symbol: string, provider: string, days: number, token: string, signOut: () => unknown) {
  const [series, setSeries] = useState<SeriesSnapshot>();
  const [tick, setTick] = useState<QuoteSnapshot>();
  const [seriesError, setSeriesError] = useState(false);
  const [quoteError, setQuoteError] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    const signal = controller.signal;
    const query = new URLSearchParams({ symbol, provider });
    let quoteTimer: ReturnType<typeof setTimeout>;
    let seriesTimer: ReturnType<typeof setTimeout>;
    let readingQuote = false;
    let readingSeries = false;
    let lastCheck = 0;
    let lastStamp = 0;
    let lastQuoteSlot = 0;
    let open = false;
    const active = () => !signal.aborted && !document.hidden;

    function denied(error: unknown) {
      if (!(error instanceof AccessChanged)) return false;
      controller.abort();
      void signOut();
      return true;
    }

    async function loadSeries() {
      if (readingSeries || !active()) return;
      clearTimeout(seriesTimer);
      readingSeries = true;
      lastCheck = Date.now();
      let delay = 30000;
      try {
        const result = await read<SeriesSnapshot>(`/api/v1/live/candles?${query}&timeframe=15m&limit=750&history_days=${days}&include_indicator_history=true`, token, signal);
        if (signal.aborted) return;
        lastStamp = result.indicator_decision.candle_timestamp ? epoch(result.indicator_decision.candle_timestamp) : 0;
        setSeries(result);
        setSeriesError(false);
        delay = result.feed_state === "closed" ? 60000 : 30000;
      } catch (error) {
        if (signal.aborted || denied(error)) return;
        setSeriesError(true);
        delay = 10000;
      } finally {
        readingSeries = false;
        if (active()) seriesTimer = setTimeout(loadSeries, delay);
      }
    }

    async function loadQuote() {
      if (readingQuote || !active()) return;
      clearTimeout(quoteTimer);
      readingQuote = true;
      let delay = 5000;
      try {
        const result = await read<QuoteSnapshot>(`/api/v1/live/quote?${query}&include_forming=true`, token, signal);
        if (signal.aborted) return;
        setTick(result);
        setQuoteError(false);
        open = result.feed_state === "live" && !result.is_stale;
        const slot = slotAt(result.checked_at);
        if (open && ((lastQuoteSlot && slot !== lastQuoteSlot) ||
            (lastStamp < slot - 900 && Date.now() - lastCheck >= 12000))) void loadSeries();
        lastQuoteSlot = slot;
        delay = open ? 2000 : result.feed_state === "closed" ? 30000 : 5000;
      } catch (error) {
        if (signal.aborted || denied(error)) return;
        setQuoteError(true);
      } finally {
        readingQuote = false;
        if (active()) quoteTimer = setTimeout(loadQuote, delay);
      }
    }

    function refresh() {
      clearTimeout(quoteTimer);
      clearTimeout(seriesTimer);
      if (active()) { void loadSeries(); void loadQuote(); }
    }
    refresh();
    document.addEventListener("visibilitychange", refresh);
    window.addEventListener("online", refresh);
    return () => {
      controller.abort();
      clearTimeout(quoteTimer);
      clearTimeout(seriesTimer);
      document.removeEventListener("visibilitychange", refresh);
      window.removeEventListener("online", refresh);
    };
  }, [symbol, provider, days, token, signOut]);

  return { series, tick, seriesError, quoteError };
}
