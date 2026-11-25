"use client";

import { useCallback, useEffect, useState } from "react";

const api = (process.env.NEXT_PUBLIC_API_BASE_URL ||
  (process.env.NODE_ENV === "production" ? "https://allsafe-ai-api.onrender.com" : "http://localhost:8000"))
  .trim().replace(/\/+$/, "");
const subscriptionUrl = `${api}/api/v1/telegram/subscription`;

type Status = { connected: boolean; available: boolean };

export default function TelegramAlerts({ token }: { token: string }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [link, setLink] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const request = useCallback((method: string, path = "", signal?: AbortSignal) => fetch(subscriptionUrl + path, {
    method, headers: { Authorization: `Bearer ${token}` }, cache: "no-store", credentials: "omit",
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(15000)]) : AbortSignal.timeout(15000),
  }), [token]);

  useEffect(() => {
    if (pending) return;
    const controller = new AbortController();
    let active = false;
    async function refresh() {
      if (active || controller.signal.aborted) return;
      active = true;
      try {
        const response = await request("GET", "", controller.signal);
        if (!response.ok) return;
        const status = await response.json() as Status;
        if (!controller.signal.aborted) {
          setStatus(status);
          if (status.connected) setLink(null);
        }
      } catch {
        // The focus handler gives customers another chance after a temporary failure.
      } finally {
        active = false;
      }
    }
    void refresh();
    window.addEventListener("focus", refresh);
    const poll = link ? window.setInterval(() => void refresh(), 5000) : undefined;
    return () => {
      controller.abort();
      window.removeEventListener("focus", refresh);
      window.clearInterval(poll);
    };
  }, [link, pending, request]);

  useEffect(() => {
    if (!link) return;
    const expire = window.setTimeout(() => setLink(null), 600000);
    return () => window.clearTimeout(expire);
  }, [link]);

  async function toggle() {
    setPending(true);
    setError(null);
    try {
      if (status?.connected) {
        const response = await request("DELETE");
        if (!response.ok) throw new Error();
        setLink(null);
        setStatus({ available: true, connected: false });
      } else {
        const response = await request("POST", "/link");
        if (!response.ok) throw new Error();
        const result = await response.json() as { url?: string };
        if (!result.url || !/^https:\/\/t\.me\/[A-Za-z0-9_]+\?start=[A-Za-z0-9_-]{43}$/.test(result.url)) {
          throw new Error();
        }
        setLink(result.url);
      }
    } catch {
      setError(status?.connected ? "Couldn’t turn off alerts. Try again." : "Couldn’t create a Telegram link. Try again.");
    } finally {
      setPending(false);
    }
  }

  if (!status?.available) return null;
  return (
    <section className="as-panel mt-6 p-5 sm:p-6" aria-labelledby="telegram-alerts-title">
      <h2 id="telegram-alerts-title" className="as-section-title">Telegram alerts</h2>
      <p className="mt-1 text-sm text-slate-300">Get a private message when a new signal is available on your AllSafe chart.</p>
      {status.connected && <p className="mt-2 text-sm text-emerald-200" role="status">Telegram is connected.</p>}
      {link && !status.connected ? (
        <div className="mt-3">
          <a className="as-button as-button--primary" href={link} target="_blank" rel="noreferrer">Open Telegram</a>
          <p className="mt-2 text-sm text-slate-400">Tap Start in Telegram to finish connecting. This link expires in 10 minutes.</p>
          <button className="as-button as-button--quiet mt-2" type="button" disabled={pending} onClick={() => void toggle()}>Get a new link</button>
        </div>
      ) : (
        <button className="as-button as-button--quiet mt-3" type="button" disabled={pending} onClick={() => void toggle()}>
          {status.connected ? "Turn off Telegram alerts" : "Connect Telegram"}
        </button>
      )}
      {error && <p className="mt-2 text-sm text-rose-200" role="alert">{error}</p>}
    </section>
  );
}
