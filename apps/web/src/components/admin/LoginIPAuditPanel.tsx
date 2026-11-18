"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type LoginIPEvent = {
  user_id: string;
  email: string;
  client_ip: string;
  logged_at: string;
};

type MultipleIPDay = {
  user_id: string;
  email: string;
  login_date: string;
  login_count: number;
  distinct_ip_count: number;
  ip_addresses: string[];
};

type AuditReply = {
  events: LoginIPEvent[];
  multiple_ip_days: MultipleIPDay[];
  limit: number;
  offset: number;
};

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL?.trim() ||
  (process.env.NODE_ENV === "development"
    ? "http://localhost:8000"
    : "https://allsafe-ai-api.onrender.com")
).replace(/\/+$/, "");

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

async function readError(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
    }
  } catch { /* Use the status message below. */ }
  return `The sign-in audit service returned HTTP ${response.status}.`;
}

export default function LoginIPAuditPanel({ accessToken }: { accessToken: string }) {
  const [events, setEvents] = useState<LoginIPEvent[]>([]);
  const [multipleIPDays, setMultipleIPDays] = useState<MultipleIPDay[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const eventCount = useRef(0);

  const load = useCallback(async (reset = true) => {
    setLoading(true);
    setError(null);
    const offset = reset ? 0 : eventCount.current;
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/admin/login-ip-audit?limit=100&offset=${offset}`,
        {
          headers: { Authorization: `Bearer ${accessToken}`, Accept: "application/json" },
          cache: "no-store",
          credentials: "omit",
          signal: AbortSignal.timeout(20000),
        },
      );
      if (!response.ok) throw new Error(await readError(response));
      const reply = await response.json() as AuditReply;
      const received = Array.isArray(reply.events) ? reply.events : [];
      eventCount.current = offset + received.length;
      setEvents((current) => reset ? received : [...current, ...received]);
      setMultipleIPDays(Array.isArray(reply.multiple_ip_days) ? reply.multiple_ip_days : []);
      setHasMore(received.length === 100);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load customer sign-in history.");
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(true); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  return (
    <section aria-labelledby="login-ip-audit-title" className="mt-7 rounded-2xl border border-sky-400/15 bg-sky-400/[0.035] p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="login-ip-audit-title" className="text-lg font-semibold text-white">Customer sign-in IP history</h2>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-400">
            Successful customer sign-ins are recorded by the API. More than one IP on a UTC day is a review signal, not proof of account sharing; mobile networks and changing connections can cause it.
          </p>
        </div>
        <button type="button" onClick={() => void load(true)} disabled={loading} className="rounded-lg border border-white/15 px-3 py-2 text-xs text-slate-200 hover:bg-white/5 disabled:opacity-50">
          {loading && events.length === 0 ? "Loading…" : "Refresh history"}
        </button>
      </div>

      {error && <p role="alert" className="mt-4 rounded-lg border border-rose-400/25 bg-rose-400/10 p-3 text-sm text-rose-100">{error}</p>}

      {multipleIPDays.length > 0 && (
        <div className="mt-5 rounded-xl border border-amber-300/20 bg-amber-300/[0.06] p-4">
          <h3 className="font-medium text-amber-100">Days with sign-ins from multiple IP addresses</h3>
          <ul className="mt-3 grid gap-2 text-sm text-slate-200 sm:grid-cols-2">
            {multipleIPDays.slice(0, 30).map((day) => (
              <li key={`${day.user_id}-${day.login_date}`} className="rounded-lg border border-white/5 bg-slate-950/50 p-3">
                <p className="font-medium text-white">{day.email}</p>
                <p className="mt-1 text-xs text-slate-400">{day.login_date} UTC · {day.login_count} sign-ins · {day.distinct_ip_count} IPs</p>
                <p className="mt-1 break-all font-mono text-xs text-amber-100">{day.ip_addresses.join(", ")}</p>
              </li>
            ))}
          </ul>
          {multipleIPDays.length > 30 && <p className="mt-3 text-xs text-slate-500">Showing the latest 30 flagged days.</p>}
        </div>
      )}

      <div className="mt-5 overflow-x-auto rounded-xl border border-white/10">
        <table className="w-full min-w-[620px] text-left text-sm">
          <thead className="bg-white/5 text-xs uppercase tracking-wide text-slate-400">
            <tr><th scope="col" className="px-4 py-3">Customer</th><th scope="col" className="px-4 py-3">IP address</th><th scope="col" className="px-4 py-3">Signed in</th></tr>
          </thead>
          <tbody>
            {events.map((event, index) => (
              <tr key={`${event.user_id}-${event.logged_at}-${index}`} className="border-t border-white/5 text-slate-200">
                <td className="px-4 py-3">{event.email}</td>
                <td className="px-4 py-3 font-mono">{event.client_ip}</td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-400">{formatDate(event.logged_at)}</td>
              </tr>
            ))}
            {!loading && !error && events.length === 0 && (
              <tr><td colSpan={3} className="px-4 py-8 text-center text-sm text-slate-500">No customer sign-ins have been recorded yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      {hasMore && (
        <button type="button" onClick={() => void load(false)} disabled={loading} className="mt-4 rounded-lg border border-white/15 px-4 py-2 text-xs text-slate-200 hover:bg-white/5 disabled:opacity-50">
          {loading ? "Loading…" : "Load older sign-ins"}
        </button>
      )}
    </section>
  );
}
