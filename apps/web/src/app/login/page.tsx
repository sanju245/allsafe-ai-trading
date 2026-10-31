"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "@/components/auth/AuthProvider";

const SUPABASE_CONFIGURED = Boolean(
  process.env.NEXT_PUBLIC_SUPABASE_URL?.trim() &&
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim(),
);
const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  (process.env.NODE_ENV === "production"
    ? "https://allsafe-ai-api.onrender.com"
    : "http://localhost:8000")
)
  .trim()
  .replace(/\/+$/, "");

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export default function LoginPage() {
  const router = useRouter();
  const { session, loading, signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [clientIp, setClientIp] = useState<string | null>(null);
  const [ipLoading, setIpLoading] = useState(true);
  const [ipUnavailable, setIpUnavailable] = useState(false);

  useEffect(() => {
    if (!loading && session) router.replace("/account");
  }, [loading, router, session]);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 8000);

    fetch(`${API_BASE_URL}/api/v1/auth/client-ip`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
      credentials: "omit",
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error("IP lookup failed");
        const body: unknown = await response.json();
        if (!isRecord(body)) throw new Error("Unexpected IP response");
        const ip = [body.client_ip, body.ip, body.address].find(
          (value): value is string => typeof value === "string" && value.trim().length > 0,
        );
        if (!ip) throw new Error("IP missing from response");
        if (active) setClientIp(ip);
      })
      .catch(() => {
        if (active) setIpUnavailable(true);
      })
      .finally(() => {
        if (active) setIpLoading(false);
      });

    return () => {
      active = false;
      window.clearTimeout(timer);
      controller.abort();
    };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    try {
      await signIn(email, password);
      setPassword("");
      router.replace("/account");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Sign-in failed. Try again.");
      setPassword("");
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center px-4 py-10 sm:px-6">
      <header className="mb-6 flex items-center justify-between gap-3">
        <Link href="/" className="text-sm font-semibold text-slate-200 hover:text-white">
          AllSafe <span className="text-emerald-400">AI Trading</span>
        </Link>
        <Link href="/" className="text-sm text-slate-400 hover:text-white">
          Back to dashboard
        </Link>
      </header>

      <section className="rounded-2xl border border-white/10 bg-white/[0.025] p-5 sm:p-8">
        <p className="text-xs font-medium uppercase tracking-widest text-emerald-400">Customer access</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">Sign in</h1>
        <p className="mt-2 text-sm leading-relaxed text-slate-300">
          Sign in with the account created for you by the administrator. Public account creation is disabled.
        </p>

        <div className="mt-5 rounded-lg border border-white/10 bg-slate-950/50 p-4 text-sm">
          <p className="font-medium text-slate-200">Current IP for account setup</p>
          {ipLoading ? (
            <p className="mt-1 text-slate-400">Checking the account service…</p>
          ) : clientIp ? (
            <p className="mt-1 break-all font-mono text-emerald-200">{clientIp}</p>
          ) : (
            <p className="mt-1 text-amber-200">
              {ipUnavailable ? "Current IP is unavailable. Check the account service connection." : "Current IP is unavailable."}
            </p>
          )}
          <p className="mt-2 text-xs leading-relaxed text-slate-500">
            The administrator can use this address when restricting a customer login to one public IP.
          </p>
        </div>

        {!SUPABASE_CONFIGURED ? (
          <div className="mt-5 rounded-lg border border-amber-400/30 bg-amber-400/10 p-4 text-sm text-amber-100">
            <p className="font-semibold">Sign-in is not configured yet.</p>
            <p className="mt-1 leading-relaxed">
              The administrator must set <code>NEXT_PUBLIC_SUPABASE_URL</code> and{" "}
              <code>NEXT_PUBLIC_SUPABASE_ANON_KEY</code> in the web app environment, then redeploy the site.
              Do not put a Supabase service-role key in the web app.
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
                className="mt-1 block w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2.5 text-sm text-white outline-none focus:border-emerald-400/60"
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
                className="mt-1 block w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2.5 text-sm text-white outline-none focus:border-emerald-400/60"
              />
            </label>
            <button
              type="submit"
              disabled={loading}
              className="rounded-lg bg-emerald-400 px-4 py-2.5 text-sm font-semibold text-slate-950 hover:bg-emerald-300 disabled:cursor-wait disabled:opacity-60"
            >
              {loading ? "Verifying account…" : "Sign in"}
            </button>
          </form>
        )}

        {error && (
          <p role="alert" className="mt-4 rounded-lg border border-rose-400/30 bg-rose-400/10 p-3 text-sm text-rose-100">
            {error}
          </p>
        )}
        <p className="mt-4 text-xs leading-relaxed text-slate-500">
          Need access? Contact your administrator. Sign-in tokens stay in memory and are cleared when you sign out or reload.
        </p>
      </section>
    </main>
  );
}
