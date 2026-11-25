"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useAuth } from "@/components/auth/AuthProvider";
import CustomerWarnings from "@/components/auth/CustomerWarnings";

export default function DashboardAccessGate({
  children,
  signInDestination = "/terminal",
}: {
  children: ReactNode;
  signInDestination?: string;
}) {
  const router = useRouter();
  const { session, profile, loading, signOut, pauseMessage } = useAuth();

  async function leaveProject() {
    await signOut();
    router.replace("/login");
  }

  if (loading) {
    return (
      <main className="mx-auto flex min-h-screen max-w-5xl items-center px-4 py-10 sm:px-6">
        <p className="rounded-xl border border-white/10 bg-white/[0.025] p-5 text-sm text-slate-300">
          Checking your account…
        </p>
      </main>
    );
  }

  if (!session || !profile) {
    return (
      <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center px-4 py-10 sm:px-6">
        <section className="rounded-2xl border border-white/10 bg-white/[0.025] p-6 sm:p-8">
          <p className="text-xs font-medium uppercase tracking-widest text-emerald-400">Customer access</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">{pauseMessage ? "Account paused" : "Sign in to use AllSafe"}</h1>
          {pauseMessage ? (
            <p role="alert" className="mt-3 max-w-xl whitespace-pre-wrap break-words text-sm leading-relaxed text-amber-100">{pauseMessage}</p>
          ) : (
            <p className="mt-3 max-w-xl text-sm leading-relaxed text-slate-300">
              Your administrator creates your account. Sign in with your email and password from any network.
            </p>
          )}
          <Link href={`/login?${new URLSearchParams({ next: signInDestination })}`} className="mt-5 inline-flex rounded-lg bg-emerald-400 px-4 py-2.5 text-sm font-semibold text-slate-950 hover:bg-emerald-300">
            Go to sign in
          </Link>
        </section>
      </main>
    );
  }

  return (
    <>
      <nav aria-label="Account navigation" className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 pt-4 sm:px-6">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Link href="/terminal" className="rounded-lg px-3 py-2 text-slate-200 hover:bg-white/5">Dashboard</Link>
          <Link href="/account" className="rounded-lg px-3 py-2 text-slate-300 hover:bg-white/5">Account</Link>
          {profile.role === "admin" && (
            <Link href="/admin" className="rounded-lg px-3 py-2 text-emerald-200 hover:bg-emerald-400/10">Admin</Link>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span className="max-w-56 truncate text-xs text-slate-500">{profile.email}</span>
          <button type="button" onClick={() => void leaveProject()} className="rounded-lg border border-white/15 px-3 py-2 text-xs font-medium text-slate-300 hover:bg-white/5">
            Sign out
          </button>
        </div>
      </nav>
      <div className="mx-auto max-w-5xl px-4 sm:px-6"><CustomerWarnings /></div>
      {children}
    </>
  );
}
