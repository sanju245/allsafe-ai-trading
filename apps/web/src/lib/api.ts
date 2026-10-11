// Server-side helper for talking to the FastAPI backend.
// Only import this from Server Components or route handlers: API_BASE_URL is
// intentionally not exposed to the browser.

export type HealthResult =
  | {
      ok: true;
      service: string;
      version: string;
      environment: string;
      timeUtc: string;
    }
  | { ok: false; reason: string };

export async function getApiHealth(): Promise<HealthResult> {
  const base = process.env.API_BASE_URL;
  if (!base) {
    return { ok: false, reason: "API_BASE_URL is not set" };
  }

  try {
    const res = await fetch(`${base}/health`, {
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
    };
  } catch {
    return { ok: false, reason: "API is not reachable" };
  }
}
