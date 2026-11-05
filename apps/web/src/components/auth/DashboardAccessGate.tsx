"use client";

import { useEffect, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "./AuthProvider";

interface DashboardAccessGateProps {
  children: ReactNode;
  requireAdmin?: boolean;
}

function hasAdminAccess(role?: string, isSuperAdmin?: boolean): boolean {
  if (isSuperAdmin) return true;
  return role === "admin" || role === "operator" || role === "auditor";
}

export function DashboardAccessGate({
  children,
  requireAdmin = false,
}: DashboardAccessGateProps) {
  const { user, loading, signOut } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (loading) return;

    if (!user) {
      const loginRoute = requireAdmin ? "/admin/login" : "/login";
      const loginUrl = new URL(loginRoute, window.location.origin);
      loginUrl.searchParams.set("next", pathname);
      router.replace(loginUrl.pathname + loginUrl.search);
      return;
    }

    if (requireAdmin && !hasAdminAccess(user.role, user.is_super_admin)) {
      router.replace("/terminal");
    }
  }, [user, loading, requireAdmin, pathname, router]);

  if (loading) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="flex min-h-screen items-center justify-center bg-slate-950 px-4 text-slate-200"
      >
        <div className="flex items-center gap-3 rounded-xl border border-white/10 bg-slate-900/70 px-5 py-3.5 text-sm shadow-xl">
          <span className="h-2.5 w-2.5 animate-ping rounded-full bg-emerald-400" />
          <span>Verifying session &amp; security policy...</span>
        </div>
      </div>
    );
  }

  if (!user || (requireAdmin && !hasAdminAccess(user.role, user.is_super_admin))) {
    return null;
  }

  const isAdmin = hasAdminAccess(user.role, user.is_super_admin);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* Top Global Security & Navigation Strip */}
      <nav
        aria-label="Global platform navigation"
        className="border-b border-white/10 bg-slate-900/80 backdrop-blur-md"
      >
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-2.5 text-xs sm:px-6 lg:px-8">
          <div className="flex flex-wrap items-center gap-2 sm:gap-4">
            <Link
              href="/"
              className="rounded-lg px-2.5 py-1 font-medium text-slate-300 transition hover:bg-white/5 hover:text-white"
            >
              Landing Page
            </Link>
            <Link
              href="/terminal"
              className={`rounded-lg px-2.5 py-1 font-medium transition ${
                pathname === "/terminal"
                  ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                  : "text-slate-300 hover:bg-white/5 hover:text-white"
              }`}
            >
              Live Market Terminal
            </Link>
            {isAdmin && (
              <Link
                href="/admin"
                className={`rounded-lg px-2.5 py-1 font-medium transition ${
                  pathname?.startsWith("/admin")
                    ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                    : "text-slate-300 hover:bg-white/5 hover:text-white"
                }`}
              >
                Admin Control Center
              </Link>
            )}
            <Link
              href="/account"
              className={`rounded-lg px-2.5 py-1 font-medium transition ${
                pathname === "/account"
                  ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                  : "text-slate-300 hover:bg-white/5 hover:text-white"
              }`}
            >
              Account &amp; Security
            </Link>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <span className="hidden items-center gap-1.5 rounded-full border border-white/10 bg-slate-950/70 px-2.5 py-0.5 text-[11px] text-slate-300 sm:inline-flex">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              <span>{user.email}</span>
              <span className="rounded bg-emerald-500/20 px-1.5 py-0.2 text-[10px] font-semibold uppercase text-emerald-300">
                {user.is_super_admin ? "SUPER ADMIN" : user.role}
              </span>
            </span>
            <button
              type="button"
              onClick={() => void signOut()}
              className="rounded-lg border border-white/10 bg-white/5 px-2.5 py-1 text-xs font-medium text-slate-300 transition hover:bg-white/10 hover:text-white"
            >
              Sign Out
            </button>
          </div>
        </div>
      </nav>

      {children}
    </div>
  );
}

export default DashboardAccessGate;
