"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/components/auth/AuthProvider";

type Warning = { id: string; message: string; sent_at: string };
type WarningPage = { warnings: Warning[]; next_before: string | null };

const api = (process.env.NEXT_PUBLIC_API_BASE_URL ||
  (process.env.NODE_ENV === "production" ? "https://allsafe-ai-api.onrender.com" : "http://localhost:8000")).trim().replace(/\/+$/, "");
const ist = new Intl.DateTimeFormat("en-IN", {
  dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata",
});

function WarningEntry({ warning }: { warning: Warning }) {
  return (
    <div className="min-w-0">
      <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-amber-100">{warning.message}</p>
      <time dateTime={warning.sent_at} className="mt-1.5 block text-xs text-amber-200/75">
        {ist.format(new Date(warning.sent_at))} IST
      </time>
    </div>
  );
}

function WarningList({ token, refreshProfile }: { token: string; refreshProfile: () => Promise<void> }) {
  const [page, setPage] = useState<WarningPage | null>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [error, setError] = useState(false);
  const lifecycle = useRef<AbortController | null>(null);

  const fetchPage = useCallback(async (signal: AbortSignal, before?: string): Promise<WarningPage | null> => {
    const suffix = before ? `?before=${encodeURIComponent(before)}` : "";
    const response = await fetch(`${api}/api/v1/auth/warnings${suffix}`, {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
      cache: "no-store",
      credentials: "omit",
      signal: AbortSignal.any([signal, AbortSignal.timeout(20000)]),
    });
    if (response.status === 401 || response.status === 403) {
      if (!signal.aborted) {
        setPage(null);
        void refreshProfile().catch(() => {});
      }
      return null;
    }
    if (!response.ok) throw new Error("Could not load account warnings.");
    const result = await response.json() as WarningPage;
    if (!Array.isArray(result.warnings)) throw new Error("Could not read account warnings.");
    return result;
  }, [refreshProfile, token]);

  useEffect(() => {
    const controller = new AbortController();
    lifecycle.current = controller;
    let reading = false;
    async function refresh() {
      if (document.hidden || controller.signal.aborted || reading) return;
      reading = true;
      try {
        const result = await fetchPage(controller.signal);
        if (result && !controller.signal.aborted) {
          setPage((current) => current && current.warnings[0]?.id === result.warnings[0]?.id ? current : result);
        }
      } catch {
        // A temporary connection failure will retry at the next refresh.
      } finally {
        reading = false;
      }
    }
    void refresh();
    const timer = window.setInterval(refresh, 30000);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      controller.abort();
      lifecycle.current = null;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [fetchPage]);

  async function loadEarlier() {
    const before = page?.next_before;
    const signal = lifecycle.current?.signal;
    if (!before || !signal || loadingOlder) return;
    setLoadingOlder(true);
    setError(false);
    try {
      const earlier = await fetchPage(signal, before);
      if (earlier && !signal.aborted) {
        setPage((current) => current?.next_before === before
          ? { warnings: [...current.warnings, ...earlier.warnings], next_before: earlier.next_before }
          : current);
      }
    } catch {
      if (!signal.aborted) setError(true);
    } finally {
      if (!signal.aborted || lifecycle.current) setLoadingOlder(false);
    }
  }

  const [latest, ...earlier] = page?.warnings ?? [];
  if (!latest) return null;
  return (
    <section aria-label="Account warnings" className="my-4 rounded-xl border border-amber-400/25 bg-amber-950/40 p-4 sm:p-5">
      <h2 className="mb-2 text-sm font-semibold text-amber-100">Account warning from your administrator</h2>
      <div aria-live="polite"><WarningEntry warning={latest} /></div>
      {earlier.length > 0 && (
        <details className="mt-4 border-t border-amber-400/20 pt-3">
          <summary className="cursor-pointer text-sm font-medium text-amber-200">Earlier warnings</summary>
          <div className="mt-3 grid gap-4">
            {earlier.map((warning) => <WarningEntry key={warning.id} warning={warning} />)}
            {page?.next_before && (
              <button type="button" disabled={loadingOlder} onClick={() => void loadEarlier()} className="w-fit rounded-lg border border-amber-400/25 px-3 py-2 text-xs text-amber-200 hover:bg-amber-400/10 disabled:opacity-60">
                {loadingOlder ? "Loading…" : "Load earlier warnings"}
              </button>
            )}
            {error && <p role="alert" className="text-sm text-rose-200">Could not load earlier warnings. Try again.</p>}
          </div>
        </details>
      )}
    </section>
  );
}

export default function CustomerWarnings() {
  const { session, profile, refreshProfile } = useAuth();
  if (!session || profile?.role !== "user" || profile.status !== "active") return null;
  return <WarningList key={profile.id} token={session.access_token} refreshProfile={refreshProfile} />;
}
