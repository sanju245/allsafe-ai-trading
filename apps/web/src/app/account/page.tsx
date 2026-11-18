"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "@/components/auth/AuthProvider";

export default function AccountPage() {
  const router = useRouter();
  const { session, profile, loading, signOut, changePassword } = useAuth();
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !session) router.replace("/login?next=%2Faccount");
  }, [loading, router, session]);

  async function submitPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    if (password.length < 8 || password.length > 128) {
      setError("Choose a password between 8 and 128 characters.");
      return;
    }
    if (password !== confirmation) {
      setError("The password entries do not match.");
      return;
    }
    try {
      await changePassword(password);
      setPassword("");
      setConfirmation("");
      setMessage("Password changed. You are still signed in.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not change the password.");
    }
  }

  async function leaveAccount() {
    await signOut();
    router.replace("/login");
  }

  if (loading || !session || !profile) {
    return (
      <main className="mx-auto flex min-h-screen max-w-3xl items-center px-4 py-10 sm:px-6">
        <div className="w-full rounded-2xl border border-white/10 bg-white/[0.025] p-6 text-sm text-slate-300">
          {loading ? "Checking your account…" : "Redirecting to sign in…"}
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center px-4 py-10 sm:px-6">
      <header className="mb-6 flex items-center justify-between gap-3">
        <Link href="/" className="text-sm font-semibold text-slate-200 hover:text-white">
          AllSafe <span className="text-emerald-400">AI Trading</span>
        </Link>
        <div className="flex flex-wrap items-center gap-4">
          {profile.role === "admin" && (
            <Link href="/admin" className="text-sm text-emerald-200 hover:text-white">
              Admin portal
            </Link>
          )}
          <Link href="/terminal" className="text-sm text-slate-400 hover:text-white">
            Live market terminal
          </Link>
        </div>
      </header>

      <section className="rounded-2xl border border-white/10 bg-white/[0.025] p-5 sm:p-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-widest text-emerald-400">Account</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">Your account</h1>
            <p className="mt-2 text-sm text-slate-300">Signed in as {profile.email}</p>
          </div>
          <button
            type="button"
            onClick={() => void leaveAccount()}
            disabled={loading}
            className="rounded-lg border border-white/15 px-3 py-2 text-sm text-slate-200 hover:bg-white/5 disabled:opacity-50"
          >
            Sign out
          </button>
        </div>

        <dl className="mt-6 grid gap-3 rounded-lg border border-white/10 bg-slate-950/50 p-4 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs text-slate-500">Account role</dt>
            <dd className="mt-1 capitalize text-slate-200">{profile.role}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Login status</dt>
            <dd className="mt-1 capitalize text-emerald-200">{profile.status}</dd>
          </div>
        </dl>

        {profile.status === "paused" ? (
          <div className="mt-6 rounded-lg border border-amber-400/30 bg-amber-400/10 p-4 text-sm text-amber-100">
            This login is paused. Contact the administrator to restore access.
          </div>
        ) : (
          <form onSubmit={submitPassword} className="mt-7 max-w-xl">
            <h2 className="text-lg font-semibold text-white">Change password</h2>
            <p className="mt-1 text-sm text-slate-400">Use between 8 and 128 characters and enter it twice.</p>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <label className="text-sm text-slate-300">
                New password
                <input
                  type="password"
                  autoComplete="new-password"
                  minLength={8}
                  maxLength={128}
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="mt-1 block w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2.5 text-sm text-white outline-none focus:border-emerald-400/60"
                />
              </label>
              <label className="text-sm text-slate-300">
                Confirm password
                <input
                  type="password"
                  autoComplete="new-password"
                  minLength={8}
                  maxLength={128}
                  required
                  value={confirmation}
                  onChange={(event) => setConfirmation(event.target.value)}
                  className="mt-1 block w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2.5 text-sm text-white outline-none focus:border-emerald-400/60"
                />
              </label>
            </div>
            <button
              type="submit"
              disabled={loading}
              className="mt-4 rounded-lg bg-emerald-400 px-4 py-2.5 text-sm font-semibold text-slate-950 hover:bg-emerald-300 disabled:cursor-wait disabled:opacity-60"
            >
              {loading ? "Updating password…" : "Change password"}
            </button>
          </form>
        )}

        {error && (
          <p role="alert" className="mt-4 rounded-lg border border-rose-400/30 bg-rose-400/10 p-3 text-sm text-rose-100">
            {error}
          </p>
        )}
        {message && (
          <p role="status" className="mt-4 rounded-lg border border-emerald-400/20 bg-emerald-400/5 p-3 text-sm text-emerald-100">
            {message}
          </p>
        )}
      </section>
    </main>
  );
}
