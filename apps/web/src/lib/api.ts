// Server-side health check helper + re-exported browser-safe API client helpers.
// Server-only environment variables (process.env.API_BASE_URL) are read exclusively inside getApiHealth() on the server.

export {
  PUBLIC_API_BASE_URL,
  API_BASE_URL,
  AuthApiError,
  fetchApi,
  type FetchApiOptions,
} from "./clientApi";

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
  const base =
    process.env.API_BASE_URL ||
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    (process.env.NODE_ENV === "production"
      ? "https://allsafe-ai-api.onrender.com"
      : "");
  if (!base) {
    return { ok: false, reason: "API_BASE_URL is not set" };
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 3000);

  try {
    const res = await fetch(`${base.replace(/\/+$/, "")}/health`, {
      cache: "no-store",
      signal: controller.signal,
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
  } finally {
    clearTimeout(timeoutId);
  }
}
