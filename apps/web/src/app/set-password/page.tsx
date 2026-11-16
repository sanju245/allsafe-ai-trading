"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

const SUPABASE_URL = (process.env.NEXT_PUBLIC_SUPABASE_URL ?? "").trim().replace(/\/+$/, "");
const SUPABASE_ANON_KEY = (process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "").trim();

export default function SetPasswordPage() {
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const token = fragment.get("access_token");
    const failure = fragment.get("error_description");
    window.history.replaceState(null, "", window.location.pathname);
    const timer = window.setTimeout(() => {
      if (token) setAccessToken(token);
      else setError(failure || "This setup link is missing or expired. Contact the administrator for a new link.");
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!accessToken) return;
    if (password !== confirmPassword) {
      setError("The passwords do not match.");
      return;
    }
    if (password.length < 8) {
      setError("Use at least 8 characters.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (!SUPABASE_URL || !SUPABASE_ANON_KEY) throw new Error("Account setup is not configured yet.");
      const response = await fetch(`${SUPABASE_URL}/auth/v1/user`, {
        method: "PUT",
        headers: {
          apikey: SUPABASE_ANON_KEY,
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({ password }),
        cache: "no-store",
        credentials: "omit",
      });
      if (!response.ok) throw new Error("Could not set the password. The link may have expired; contact the administrator for a new one.");
      setAccessToken(null);
      setPassword("");
      setConfirmPassword("");
      setDone(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not set the password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center px-4 py-10">
      <Link href="/" className="mb-6 text-sm font-semibold text-slate-200 hover:text-white">AllSafe <span className="text-emerald-400">AI Trading</span></Link>
      <section className="rounded-2xl border border-white/10 bg-white/[0.025] p-6 sm:p-8">
        <p className="text-xs font-semibold uppercase tracking-widest text-emerald-300">Account setup</p>
        <h1 className="mt-2 text-3xl font-semibold text-white">Set your password</h1>
        {done ? (
          <div role="status" className="mt-5 text-sm leading-6 text-slate-300">
            Your password is ready. <Link href="/login" className="font-semibold text-emerald-300 underline">Sign in</Link> from your approved public IP address.
          </div>
        ) : accessToken ? (
          <form onSubmit={submit} className="mt-5 grid gap-4">
            <label className="text-sm text-slate-300">New password
              <input type="password" autoComplete="new-password" minLength={8} maxLength={128} required value={password} onChange={(event) => setPassword(event.target.value)} className="mt-1 block w-full rounded-lg border border-white/15 bg-slate-950 px-3 py-2.5 text-white outline-none focus:border-emerald-400" />
            </label>
            <label className="text-sm text-slate-300">Confirm password
              <input type="password" autoComplete="new-password" minLength={8} maxLength={128} required value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} className="mt-1 block w-full rounded-lg border border-white/15 bg-slate-950 px-3 py-2.5 text-white outline-none focus:border-emerald-400" />
            </label>
            {error && <p role="alert" className="text-sm text-rose-200">{error}</p>}
            <button type="submit" disabled={busy} className="rounded-lg bg-emerald-400 px-4 py-2.5 text-sm font-semibold text-slate-950 hover:bg-emerald-300 disabled:opacity-50">{busy ? "Saving…" : "Set password"}</button>
          </form>
        ) : (
          <p role="alert" className="mt-5 text-sm leading-6 text-rose-200">{error || "Checking your setup link…"}</p>
        )}
      </section>
    </main>
  );
}
