"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import BrandLink from "@/components/BrandLink";
import { useAuth } from "@/components/auth/AuthProvider";
import CustomerWarnings from "@/components/auth/CustomerWarnings";
import CustomerWorkspaceHeader from "@/components/auth/CustomerWorkspaceHeader";

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
      <main className="as-page">
        <div className="as-auth"><BrandLink />
        <p className="as-panel as-auth-card text-sm text-slate-300" role="status">
          Checking your account…
        </p>
        </div>
      </main>
    );
  }

  if (!session || !profile) {
    return (
      <main className="as-page"><div className="as-auth">
        <BrandLink />
        <section className="as-panel as-auth-card">
          <p className="as-kicker">Customer access</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">{pauseMessage ? "Account paused" : "Sign in to use AllSafe"}</h1>
          {pauseMessage ? (
            <p role="alert" className="mt-3 max-w-xl whitespace-pre-wrap break-words text-sm leading-relaxed text-amber-100">{pauseMessage}</p>
          ) : (
            <p className="mt-3 max-w-xl text-sm leading-relaxed text-slate-300">
              Sign in with the email and password for your approved AllSafe account.
            </p>
          )}
          <Link href={`/login?${new URLSearchParams({ next: signInDestination })}`} className="as-button as-button--primary mt-5">
            Go to sign in
          </Link>
        </section>
      </div></main>
    );
  }

  return (
    <>
      <CustomerWorkspaceHeader email={profile.email} isAdmin={profile.role === "admin"} onSignOut={() => void leaveProject()} />
      <div className="as-container"><CustomerWarnings /></div>
      {children}
    </>
  );
}
