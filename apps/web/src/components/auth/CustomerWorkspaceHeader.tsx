import Link from "next/link";
import BrandLink from "@/components/BrandLink";

export default function CustomerWorkspaceHeader({
  email,
  isAdmin,
  active = "dashboard",
  onSignOut,
}: {
  email: string;
  isAdmin: boolean;
  active?: "dashboard" | "account";
  onSignOut: () => void;
}) {
  return (
    <header className="as-topbar">
      <div className="as-container as-topbar-inner">
        <BrandLink />
        <nav aria-label="Account navigation" className="as-nav-group as-customer-nav">
          <Link href="/terminal" aria-current={active === "dashboard" ? "page" : undefined} className="as-nav-link">Dashboard</Link>
          <Link href="/account" aria-current={active === "account" ? "page" : undefined} className="as-nav-link">Account</Link>
          {isAdmin && <Link href="/admin" className="as-nav-link">Admin portal</Link>}
        </nav>
        <div className="flex min-w-0 items-center gap-3">
          <span className="hidden max-w-48 truncate text-xs text-slate-400 lg:block">{email}</span>
          <button type="button" className="as-button as-button--quiet" onClick={onSignOut}>Sign out</button>
        </div>
      </div>
    </header>
  );
}
