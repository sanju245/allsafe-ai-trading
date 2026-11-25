"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useAuth } from "@/components/auth/AuthProvider";

const SUPABASE_CONFIGURED = Boolean(
  process.env.NEXT_PUBLIC_SUPABASE_URL?.trim() &&
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim(),
);

export default function AdminLoginPage() {
  const router = useRouter();
  const { session, profile, loading, signIn } = useAuth();
  const handledSession = useRef<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (loading || !session || handledSession.current === session.access_token) return;
    handledSession.current = session.access_token;

    if (profile?.role === "admin" && profile.status === "active") {
      router.replace("/admin");
    }
  }, [loading, profile, router, session]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    try {
      await signIn(email, password);
      setPassword("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Sign-in failed. Try again.");
      setPassword("");
    }
  }

  const displayError = error ?? (session && profile?.role === "user"
    ? "This account does not have access to the admin portal. Your customer session is still active."
    : null);

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center px-4 py-10 sm:px-6">
      <header className="mb-6 flex items-center justify-between gap-3">
        <Link href="/" className="text-sm font-semibold text-slate-200 hover:text-white">
          AllSafe <span className="text-emerald-400">AI Trading</span>
        </Link>
        <Link href="/login" className="text-sm text-slate-400 hover:text-white">
          Customer sign in
        </Link>
      </header>

      <section className="rounded-2xl border border-white/10 bg-white/[0.025] p-5 sm:p-8">
        <p className="text-xs font-medium uppercase tracking-widest text-emerald-400">Administrator access</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">Admin sign in</h1>
        <p className="mt-2 text-sm leading-relaxed text-slate-300">
          Sign in with an active administrator account to manage customer access.
          Administrator access is available from any IP address.
        </p>

        {!SUPABASE_CONFIGURED ? (
          <div className="mt-5 rounded-lg border border-amber-400/30 bg-amber-400/10 p-4 text-sm text-amber-100">
            <p className="font-semibold">Administrator sign-in is temporarily unavailable.</p>
            <p className="mt-1 leading-relaxed">
              Contact the account owner to restore access.
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
                disabled={loading}
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="mt-1 block w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2.5 text-sm text-white outline-none focus:border-emerald-400/60"
              />
            </label>
            <label className="text-sm text-slate-300">
              Password
              <input
                type="password"
                autoComplete="current-password"
                required
                disabled={loading}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="mt-1 block w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2.5 text-sm text-white outline-none focus:border-emerald-400/60"
              />
            </label>
            <button
              type="submit"
              disabled={loading}
              className="rounded-lg bg-emerald-400 px-4 py-2.5 text-sm font-semibold text-slate-950 hover:bg-emerald-300 disabled:cursor-wait disabled:opacity-60"
            >
              {loading ? "Verifying account…" : "Sign in to admin portal"}
            </button>
          </form>
        )}

        <Link href="/forgot-password" className="mt-4 inline-flex text-sm text-emerald-300 underline">Forgot password?</Link>

        {loading && !session && (
          <p role="status" className="mt-4 text-sm text-slate-400">
            Checking administrator access… The account service can take up to a minute to wake up.
          </p>
        )}
        {displayError && (
          <p role="alert" className="mt-4 rounded-lg border border-rose-400/30 bg-rose-400/10 p-3 text-sm text-rose-100">
            {displayError}
          </p>
        )}
        {session && profile?.role === "user" && (
          <Link href="/account" className="mt-4 inline-flex text-sm font-medium text-emerald-200 hover:text-white">
            Return to your customer account
          </Link>
        )}
        <p className="mt-4 text-xs leading-relaxed text-slate-500">
          Only active administrator accounts can enter this portal. Contact the account owner if you need access.
        </p>
      </section>
    </main>
  );
}
