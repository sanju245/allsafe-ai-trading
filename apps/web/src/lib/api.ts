// Server-side helper for talking to the FastAPI backend.
// Only import this from Server Components or route handlers: API_BASE_URL is
// intentionally not exposed to the browser.
import type { MarketCalendar } from "./indianMarketStatus";

export type HealthResult =
  | {
      ok: true;
      service: string;
      version: string;
      environment: string;
      timeUtc: string;
      marketCalendar?: MarketCalendar;
    }
  | { ok: false; reason: string };

function parseMarketCalendar(value: unknown): MarketCalendar | undefined {
  if (!value || typeof value !== "object") return;
  const { holidays, verifiedYears } = value as Record<string, unknown>;
  if (!holidays || typeof holidays !== "object" || Array.isArray(holidays) ||
      !Array.isArray(verifiedYears) || !verifiedYears.every(year => Number.isInteger(year)) ||
      !Object.entries(holidays).every(([day, name]) => /^\d{4}-\d{2}-\d{2}$/.test(day) && typeof name === "string")) return;
  return { holidays: holidays as MarketCalendar["holidays"], verifiedYears };
}

export async function getApiHealth(): Promise<HealthResult> {
  const base = process.env.API_BASE_URL;
  if (!base) {
    return { ok: false, reason: "API_BASE_URL is not set" };
  }

  try {
    const res = await fetch(`${base}/health?calendar=1`, {
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    if (!res.ok) {
      return { ok: false, reason: `API responded with HTTP ${res.status}` };
    }

    const data: unknown = await res.json();
    if (
      typeof data !== "object" ||
      data === null ||
      (data as Record<string, unknown>).status !== "ok"
    ) {
      return { ok: false, reason: "Unexpected response from API" };
    }

    const d = data as Record<string, unknown>;
    return {
      ok: true,
      service: String(d.service ?? "unknown"),
      version: String(d.version ?? "unknown"),
      environment: String(d.environment ?? "unknown"),
      timeUtc: String(d.time_utc ?? ""),
      marketCalendar: parseMarketCalendar(d.market_calendar),
    };
  } catch {
    return { ok: false, reason: "API is not reachable" };
  }
}
