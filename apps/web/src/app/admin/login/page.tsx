"use client";

import { Suspense, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth, type AppUser } from "@/components/auth/AuthProvider";
import { API_BASE_URL, fetchApi } from "@/lib/clientApi";

interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  csrf_token: string;
  user: AppUser;
}

function isAuthorizedAdminRole(user: AppUser): boolean {
  if (user.is_super_admin) return true;
  return user.role === "admin" || user.role === "operator" || user.role === "auditor";
}

function AdminLoginFormContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedNext = searchParams.get("next");
  const { signIn } = useAuth();

  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);

    try {
      const trimmedId = identifier.trim();
      const response = await fetchApi<AuthResponse>("/api/v1/auth/admin/login", {
        method: "POST",
        body: JSON.stringify({
          email: trimmedId,
          username: trimmedId,
          password,
          totp_code: totpCode.trim() || undefined,
          portal: "admin",
        }),
      });

      if (!isAuthorizedAdminRole(response.user)) {
        setError(
          "Customer accounts cannot sign in to the Admin Portal. Please use the Customer Sign-In Portal (/login).",
        );
        return;
      }

      signIn(response.access_token, response.user, response.csrf_token);
      const targetPath =
        requestedNext && requestedNext.startsWith("/admin") ? requestedNext : "/admin";
      router.replace(targetPath);
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Administrator sign-in failed. Verify credentials and MFA code.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="w-full max-w-md space-y-6 rounded-2xl border border-emerald-500/30 bg-slate-900/75 p-6 shadow-2xl backdrop-blur-xl sm:p-8">
      <div className="space-y-2 text-center">
        <div className="mx-auto inline-flex h-11 w-11 items-center justify-center rounded-xl border border-emerald-500/40 bg-emerald-500/15 font-mono text-base font-bold text-emerald-300">
          AS
        </div>
        <div className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wider text-emerald-300">
          Admin Control Center Portal
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-white">
          Administrator <span className="text-emerald-400">Sign In</span>
        </h1>
        <p className="text-xs text-slate-400 sm:text-sm">
          Dedicated administrative portal with global IP-independent access and server-side RBAC enforcement
        </p>
      </div>

      <div className="flex items-center justify-between rounded-xl border border-emerald-500/25 bg-emerald-500/10 px-3.5 py-2.5 text-[11px] text-emerald-200">
        <span>Admin Global IP Access (*)</span>
        <span className="font-mono text-emerald-300">PBKDF2 &middot; TOTP MFA &middot; RBAC</span>
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
          <label className="block text-xs font-medium text-slate-300" htmlFor="admin-identifier">
            Administrator Username or Email
          </label>
          <input
            id="admin-identifier"
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
          <label className="block text-xs font-medium text-slate-300" htmlFor="admin-password">
            Administrator Password
          </label>
          <input
            id="admin-password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••••••"
            className="w-full rounded-lg border border-white/10 bg-slate-950 px-3.5 py-2.5 text-sm text-white placeholder-slate-500 focus:border-emerald-400 focus:outline-none"
          />
        </div>

        <div className="space-y-1.5">
          <label className="block text-xs font-medium text-slate-300" htmlFor="admin-totp-code">
            Two-Factor Authenticator Code (TOTP / Optional if unconfigured)
          </label>
          <input
            id="admin-totp-code"
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={8}
            value={totpCode}
            onChange={(e) => setTotpCode(e.target.value)}
            placeholder="6-digit authenticator code"
            className="w-full rounded-lg border border-white/10 bg-slate-950 px-3.5 py-2 text-sm font-mono text-white placeholder-slate-500 focus:border-emerald-400 focus:outline-none"
          />
        </div>

        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full rounded-xl bg-emerald-500 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isSubmitting ? "Verifying Administrator..." : "Sign In to Admin Portal"}
        </button>
      </form>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-white/10 pt-4 text-xs text-slate-400">
        <Link href="/login" className="font-medium text-slate-300 hover:text-white hover:underline">
          Customer Portal Sign In &rarr;
        </Link>
        <Link href="/" className="font-medium text-emerald-300 hover:underline">
          &larr; Landing Page
        </Link>
      </div>
    </div>
  );
}

export default function AdminLoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 p-4 text-slate-100">
      <Suspense
        fallback={
          <div className="rounded-xl border border-white/10 bg-slate-900/60 px-6 py-4 text-sm text-slate-300">
            Loading Administrator Portal...
          </div>
        }
      >
        <AdminLoginFormContent />
      </Suspense>
    </main>
  );
}
