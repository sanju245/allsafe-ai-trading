"use client";

import { useEffect, useState } from "react";
import type { MarketCalendar } from "@/lib/indianMarketStatus";

type ApiHealth = {
  status: "checking" | "online" | "unavailable";
  marketCalendar?: MarketCalendar;
  serverTimeOffsetMs: number;
};

export function useApiHealth() {
  const [health, setHealth] = useState<ApiHealth>({ status: "checking", serverTimeOffsetMs: 0 });

  useEffect(() => {
    const controller = new AbortController();
    async function check() {
      try {
        const startedAt = Date.now();
        const response = await fetch("/api/health", {
          cache: "no-store", signal: AbortSignal.any([controller.signal, AbortSignal.timeout(5000)]),
        });
        if (!response.ok) throw new Error(`Health check failed (${response.status})`);
        const data: { timeUtc: string; marketCalendar?: MarketCalendar } = await response.json();
        const serverTime = Date.parse(data.timeUtc);
        if (!controller.signal.aborted) setHealth({
          status: "online",
          marketCalendar: data.marketCalendar,
          serverTimeOffsetMs: Number.isFinite(serverTime) ? serverTime - (startedAt + Date.now()) / 2 : 0,
        });
      } catch {
        if (!controller.signal.aborted) setHealth({ status: "unavailable", serverTimeOffsetMs: 0 });
      }
    }
    void check();
    return () => controller.abort();
  }, []);

  return health;
}
