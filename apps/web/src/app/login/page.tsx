"use client";

import { Suspense, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth, type AppUser } from "@/components/auth/AuthProvider";
import { API_BASE_URL, fetchApi } from "@/lib/api";

interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  csrf_token: string;
  user: AppUser;
}

function LoginFormContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedNext = searchParams.get("next");
  const { signIn } = useAuth();

  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [showMfaField, setShowMfaField] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);

    try {
      const trimmedId = identifier.trim();
      const response = await fetchApi<AuthResponse>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: trimmedId,
          username: trimmedId,
          password,
          totp_code: totpCode.trim() || undefined,
        }),
      });

      signIn(response.access_token, response.user, response.csrf_token);
      const isAdmin =
        response.user.is_super_admin ||
        response.user.role === "admin" ||
        response.user.role === "operator" ||
        response.user.role === "auditor";
      const targetPath = requestedNext || (isAdmin ? "/admin" : "/terminal");
      router.replace(targetPath);
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Sign in failed. Verify API configuration and credentials.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="w-full max-w-md space-y-6 rounded-2xl border border-white/10 bg-slate-900/60 p-6 shadow-2xl backdrop-blur-xl sm:p-8">
      <div className="space-y-2 text-center">
        <div className="mx-auto inline-flex h-11 w-11 items-center justify-center rounded-xl border border-emerald-500/30 bg-emerald-500/10 text-base font-bold text-emerald-400">
          AS
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-white">
          AllSafe <span className="text-emerald-400">AI Trading</span>
        </h1>
        <p className="text-sm text-slate-400">
          Sign in with your administrator username or registered email address
        </p>
      </div>

      <div className="flex items-center justify-between rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-3.5 py-2.5 text-[11px] text-emerald-200">
        <span>Global IP Access Enabled</span>
        <span className="font-mono text-emerald-300">PBKDF2-SHA256 &middot; TLS</span>
      </div>

      {!API_BASE_URL && (
        <div
          role="alert"
          className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-3.5 text-xs text-amber-200"
        >
          Warning: NEXT_PUBLIC_API_BASE_URL is not set. Defaulting to configured API endpoint.
        </div>
      )}

      {error && (
        <div
          role="alert"
          className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3.5 text-xs font-medium text-rose-200"
        >
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-1.5">
          <label className="block text-xs font-medium text-slate-300" htmlFor="identifier">
            Email address or Admin Username
          </label>
          <input
            id="identifier"
            type="text"
            autoComplete="username"
            required
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
            placeholder="superadmin or admin@allsafe.ai"
            className="w-full rounded-lg border border-white/10 bg-slate-950 px-3.5 py-2.5 text-sm text-white placeholder-slate-500 focus:border-emerald-400 focus:outline-none"
          />
        </div>

        <div className="space-y-1.5">
          <label className="block text-xs font-medium text-slate-300" htmlFor="password">
            Password
          </label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••••••"
            className="w-full rounded-lg border border-white/10 bg-slate-950 px-3.5 py-2.5 text-sm text-white placeholder-slate-500 focus:border-emerald-400 focus:outline-none"
          />
        </div>

        <div>
          <button
            type="button"
            onClick={() => setShowMfaField((prev) => !prev)}
            className="text-xs font-medium text-slate-400 underline-offset-2 hover:text-emerald-300 hover:underline"
          >
            {showMfaField ? "Hide 2FA authenticator code" : "Have a 2FA / TOTP code?"}
          </button>

          {showMfaField && (
            <div className="mt-2 space-y-1">
              <label className="block text-xs font-medium text-slate-300" htmlFor="totp-code">
                Two-Factor Authenticator Code (Optional)
              </label>
              <input
                id="totp-code"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={8}
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value)}
                placeholder="6-digit code"
                className="w-full rounded-lg border border-white/10 bg-slate-950 px-3.5 py-2 text-sm font-mono text-white placeholder-slate-500 focus:border-emerald-400 focus:outline-none"
              />
            </div>
          )}
        </div>

        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full rounded-xl bg-emerald-500 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isSubmitting ? "Verifying credentials..." : "Sign In Securely"}
        </button>
      </form>

      <div className="flex items-center justify-between border-t border-white/10 pt-4 text-xs text-slate-400">
        <Link href="/" className="font-medium text-emerald-300 hover:underline">
          &larr; Back to Landing Page
        </Link>
        <span className="font-mono text-[11px] text-slate-500">Read-Only Terminal</span>
      </div>

      <p className="text-center text-[11px] leading-relaxed text-slate-500">
        Strictly read-only market analysis terminal. Brute-force protection and session audit logging are active across all networks.
      </p>
    </div>
  );
}

export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 p-4 text-slate-100">
      <Suspense
        fallback={
          <div className="rounded-xl border border-white/10 bg-slate-900/60 px-6 py-4 text-sm text-slate-300">
            Loading sign-in portal...
          </div>
        }
      >
        <LoginFormContent />
      </Suspense>
    </main>
  );
}
