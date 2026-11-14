"use client";

import Link from "next/link";
import { useAuth } from "@/components/auth/AuthProvider";

export default function CustomerPortalNav() {
  const { user, signOut } = useAuth();

  return (
    <nav
      aria-label="Customer account navigation"
      className="flex flex-wrap items-center justify-end gap-2"
    >
      <p
        className="hidden max-w-48 truncate px-2 text-xs text-slate-400 sm:block"
        title={user?.email ?? undefined}
      >
        Signed in as <span className="font-medium text-slate-200">{user?.email ?? "Customer"}</span>
      </p>
      <Link
        href="/account"
        className="inline-flex min-h-10 items-center rounded-lg border border-white/10 bg-white/[0.03] px-3 text-xs font-medium text-slate-200 transition hover:border-emerald-500/30 hover:bg-white/[0.06] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
      >
        Account &amp; Security
      </Link>
      <button
        type="button"
        onClick={() => void signOut()}
        className="inline-flex min-h-10 items-center rounded-lg border border-white/10 bg-white/[0.03] px-3 text-xs font-medium text-slate-200 transition hover:border-rose-500/30 hover:bg-rose-500/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
      >
        Sign out
      </button>
    </nav>
  );
}
