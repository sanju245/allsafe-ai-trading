"use client";

import Link from "next/link";
import BrandLink from "@/components/BrandLink";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "@/components/auth/AuthProvider";
import { customerDestination } from "@/lib/customerNavigation";

const SUPABASE_CONFIGURED = Boolean(
  process.env.NEXT_PUBLIC_SUPABASE_URL?.trim() &&
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim(),
);

export default function LoginPage() {
  const router = useRouter();
  const { session, loading, signIn, pauseMessage } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && session) router.replace(customerDestination(window.location.search));
  }, [loading, router, session]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    try {
      await signIn(email, password);
      setPassword("");
      router.replace(customerDestination(window.location.search));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Sign-in failed. Try again.");
      setPassword("");
    }
  }

  return (
    <main className="as-page">
      <div className="as-auth">
        <header className="flex flex-wrap items-center justify-between gap-2">
          <BrandLink />
          <Link href="/" className="as-nav-link">Back to AllSafe home</Link>
        </header>

        <section className="as-panel as-auth-card">
          <p className="as-kicker">Customer access</p>
          <h1 className="mt-2">Sign in</h1>
          <p className="mt-2 text-sm leading-relaxed text-slate-300">
            Sign in with the email and password for your approved AllSafe account. You can sign in from any network.
          </p>

          {!SUPABASE_CONFIGURED ? (
            <div className="mt-5 rounded-lg border border-amber-400/30 bg-amber-400/10 p-4 text-sm text-amber-100">
              <p className="font-semibold">Sign-in is not configured yet.</p>
              <p className="mt-1 leading-relaxed">
                Account access is temporarily unavailable. Contact the administrator to finish setting up sign-in.
              </p>
            </div>
          ) : (
            <form onSubmit={submit} className="mt-5 grid gap-4">
              <label className="text-sm text-slate-300">
                Email
                <input
                  type="email"
                  autoComplete="username"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  className="as-field mt-1 w-full"
                />
              </label>
              <label className="text-sm text-slate-300">
                Password
                <input
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="as-field mt-1 w-full"
                />
              </label>
              <button
                type="submit"
                disabled={loading}
                className="as-button as-button--primary"
              >
                {loading ? "Verifying account…" : "Sign in"}
              </button>
            </form>
          )}

          <Link href="/forgot-password" className="mt-4 inline-flex text-sm text-emerald-300 underline">Forgot password?</Link>

          {loading && !session && (
            <p role="status" className="mt-4 text-sm text-slate-400">
              Checking your account. After inactivity, the account service may take about a minute to start. Keep this page open.
            </p>
          )}
          {(error || pauseMessage) && (
            <p role="alert" className="mt-4 whitespace-pre-wrap break-words rounded-lg border border-rose-400/30 bg-rose-400/10 p-3 text-sm text-rose-100">
              {error ?? pauseMessage}
            </p>
          )}
          <p className="mt-4 text-xs leading-relaxed text-slate-500">
            Need access? <Link href="/" className="text-emerald-300 underline">Request an account</Link> from the home page. Charts opened from the terminal use your active browser session.
          </p>
        </section>
      </div>
    </main>
  );
}
