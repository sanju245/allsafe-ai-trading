"use client";

import Link from "next/link";
import BrandLink from "@/components/BrandLink";
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
    <main className="as-page"><div className="as-auth">
      <BrandLink />
      <section className="as-panel as-auth-card">
        <p className="as-kicker">Account setup</p>
        <h1 className="mt-2">Set your password</h1>
        {done ? (
          <div role="status" className="mt-5 text-sm leading-6 text-ui-muted">
            Your password is ready. <Link href="/login" className="font-semibold text-ui-green underline">Sign in</Link> from any network.
          </div>
        ) : proof ? (
          <form onSubmit={submit} className="mt-5 grid gap-4">
            <label className="text-sm text-ui-muted">New password
              <input type="password" autoComplete="new-password" minLength={8} maxLength={128} required value={password} onChange={(event) => setPassword(event.target.value)} className="as-field mt-1 w-full" />
            </label>
            <label className="text-sm text-ui-muted">Confirm password
              <input type="password" autoComplete="new-password" minLength={8} maxLength={128} required value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} className="as-field mt-1 w-full" />
            </label>
            {error && <p role="alert" className="text-sm text-ui-red">{error}</p>}
            <button type="submit" disabled={busy} className="as-button as-button--primary">{busy ? "Saving…" : "Set password"}</button>
          </form>
        ) : (
          <p role="alert" className="mt-5 text-sm leading-6 text-ui-red">{error || "Checking your setup link…"}</p>
        )}
        {!done && <Link href="/forgot-password" className="mt-5 inline-block text-sm text-ui-green underline">Request a new password link</Link>}
      </section>
    </div></main>
  );
}
