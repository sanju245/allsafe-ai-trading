"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useAuth } from "@/components/auth/AuthProvider";
import { DashboardAccessGate } from "@/components/auth/DashboardAccessGate";
import { fetchApi } from "@/lib/api";

export default function AccountPage() {
  const { user, token, csrfToken, signOut } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [pwBusy, setPwBusy] = useState(false);
  const [pwError, setPwError] = useState<string | null>(null);
  const [pwSuccess, setPwSuccess] = useState<string | null>(null);

  const handlePasswordChange = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token) return;
    setPwError(null);
    setPwSuccess(null);

    if (newPassword !== confirmPassword) {
      setPwError("New password and confirmation do not match.");
      return;
    }

    setPwBusy(true);
    try {
      await fetchApi("/api/v1/auth/change-password", {
        method: "POST",
        token,
        csrfToken,
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPwSuccess("Password updated and re-hashed with PBKDF2-HMAC-SHA256.");
    } catch (err) {
      setPwError(err instanceof Error ? err.message : "Failed to change password.");
    } finally {
      setPwBusy(false);
    }
  };

  const isAdmin =
    user?.is_super_admin ||
    user?.role === "admin" ||
    user?.role === "operator" ||
    user?.role === "auditor";

  return (
    <DashboardAccessGate>
      <main className="mx-auto max-w-5xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 pb-6">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-emerald-400">
              Identity &amp; Access Profile
            </p>
            <h1 className="mt-1 text-2xl font-bold text-white sm:text-3xl">
              Account &amp; Security Settings
            </h1>
            <p className="mt-1 text-sm text-slate-400">
              Inspect your role permissions, global IP policy, and credential rotation controls
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2.5">
            {isAdmin && (
              <Link
                href="/admin"
                className="rounded-xl bg-emerald-500 px-4 py-2 text-xs font-semibold text-slate-950 transition hover:bg-emerald-400"
              >
                Open Admin Control Center
              </Link>
            )}
            <button
              type="button"
              onClick={() => void signOut()}
              className="rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-xs font-medium text-slate-200 transition hover:bg-white/10 hover:text-white"
            >
              Sign Out
            </button>
          </div>
        </header>

        <section className="grid gap-6 rounded-2xl border border-white/10 bg-slate-900/50 p-6 backdrop-blur-xl">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-lg font-semibold text-white">Verified Account Identity</h2>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-300">
              <span className="h-2 w-2 rounded-full bg-emerald-400" />
              {user?.is_super_admin ? "Permanent Super Admin" : `Role: ${user?.role}`}
            </span>
          </div>

          <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div className="rounded-xl border border-white/5 bg-slate-950/60 p-4">
              <dt className="text-xs font-medium text-slate-400">Account ID</dt>
              <dd className="mt-1 break-all font-mono text-xs font-semibold text-slate-200">
                {user?.id}
              </dd>
            </div>
            <div className="rounded-xl border border-white/5 bg-slate-950/60 p-4">
              <dt className="text-xs font-medium text-slate-400">Username</dt>
              <dd className="mt-1 font-mono text-sm font-semibold text-white">
                {user?.username || "—"}
              </dd>
            </div>
            <div className="rounded-xl border border-white/5 bg-slate-950/60 p-4">
              <dt className="text-xs font-medium text-slate-400">Email Address</dt>
              <dd className="mt-1 text-sm font-semibold text-white">{user?.email}</dd>
            </div>
            <div className="rounded-xl border border-white/5 bg-slate-950/60 p-4">
              <dt className="text-xs font-medium text-slate-400">Account Role</dt>
              <dd className="mt-1 text-sm font-semibold capitalize text-emerald-400">
                {user?.is_super_admin ? "Super Admin (admin)" : user?.role}
              </dd>
            </div>
            <div className="rounded-xl border border-white/5 bg-slate-950/60 p-4">
              <dt className="text-xs font-medium text-slate-400">Account Status</dt>
              <dd className="mt-1 text-sm font-semibold capitalize text-slate-200">
                {user?.status}
              </dd>
            </div>
            <div className="rounded-xl border border-white/5 bg-slate-950/60 p-4">
              <dt className="text-xs font-medium text-slate-400">IP Access Policy</dt>
              <dd className="mt-1 font-mono text-xs text-emerald-300">
                {!user?.allowed_ip || user?.allowed_ip === "*"
                  ? "Global Access (* — Any Legitimate IP)"
                  : user.allowed_ip}
              </dd>
            </div>
          </dl>
        </section>

        <section className="rounded-2xl border border-white/10 bg-slate-900/50 p-6 backdrop-blur-xl">
          <h2 className="text-lg font-semibold text-white">Rotate Account Password</h2>
          <p className="mt-1 text-xs text-slate-400">
            Passwords are never stored in plaintext. New passwords require at least 10 characters with uppercase, lowercase, digit, and special character.
          </p>

          {pwError && (
            <div
              role="alert"
              className="mt-4 rounded-xl border border-rose-500/30 bg-rose-500/10 p-3.5 text-xs text-rose-200"
            >
              {pwError}
            </div>
          )}

          {pwSuccess && (
            <div
              role="status"
              className="mt-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3.5 text-xs text-emerald-200"
            >
              {pwSuccess}
            </div>
          )}

          <form onSubmit={handlePasswordChange} className="mt-4 grid gap-4 sm:grid-cols-3">
            <label className="block text-xs font-medium text-slate-300">
              Current Password
              <input
                type="password"
                required
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white focus:border-emerald-400 focus:outline-none"
              />
            </label>
            <label className="block text-xs font-medium text-slate-300">
              New Password (min 10 chars)
              <input
                type="password"
                required
                minLength={10}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white focus:border-emerald-400 focus:outline-none"
              />
            </label>
            <label className="block text-xs font-medium text-slate-300">
              Confirm New Password
              <input
                type="password"
                required
                minLength={10}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white focus:border-emerald-400 focus:outline-none"
              />
            </label>
            <div className="sm:col-span-3">
              <button
                type="submit"
                disabled={pwBusy}
                className="rounded-xl bg-emerald-500 px-4 py-2.5 text-xs font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:opacity-50"
              >
                {pwBusy ? "Updating Password..." : "Update Password Hash"}
              </button>
            </div>
          </form>
        </section>
      </main>
    </DashboardAccessGate>
  );
}
