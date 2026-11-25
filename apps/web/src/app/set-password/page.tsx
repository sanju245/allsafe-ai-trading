"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ||
  (process.env.NODE_ENV === "production" ? "https://allsafe-ai-api.onrender.com" : "http://localhost:8000")).replace(/\/+$/, "");
type SetupProof = { token_hash: string; type: "invite" | "recovery" } | { access_token: string };

export default function SetPasswordPage() {
  const [proof, setProof] = useState<SetupProof | null>(null);
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const token = fragment.get("access_token");
    const hash = fragment.get("token_hash");
    const type = fragment.get("type");
    const failure = fragment.get("error_description");
    window.history.replaceState(null, "", window.location.pathname);
    const timer = window.setTimeout(() => {
      if (hash && (type === "invite" || type === "recovery")) setProof({ token_hash: hash, type });
      else if (token) setProof({ access_token: token });
      else setError(failure || "This setup link is missing or expired. Contact the administrator for a new link.");
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!proof) return;
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
      const response = await fetch(`${API_BASE_URL}/api/v1/auth/password/setup`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ ...proof, password }),
        cache: "no-store",
        credentials: "omit",
        signal: AbortSignal.timeout(60000),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(typeof body?.detail === "string" ? body.detail : "Could not set the password. Request a new setup link.");
      }
      setProof(null);
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
            Your password is ready. <Link href="/login" className="font-semibold text-emerald-300 underline">Sign in</Link> from any network.
          </div>
        ) : proof ? (
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
        {!done && <Link href="/forgot-password" className="mt-5 inline-block text-sm text-emerald-300 underline">Request a new password link</Link>}
      </section>
    </main>
  );
}
