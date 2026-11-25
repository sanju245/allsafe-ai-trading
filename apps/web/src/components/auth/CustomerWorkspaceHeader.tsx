import Link from "next/link";
import { usePathname } from "next/navigation";
import BrandLink from "@/components/BrandLink";
import WorkspaceIcon from "@/components/WorkspaceIcon";

export default function CustomerWorkspaceHeader({
  email,
  isAdmin,
  onSignOut,
}: {
  email: string;
  isAdmin: boolean;
  onSignOut: () => void;
}) {
  const pathname = usePathname();
  return (
    <aside className="workspace-rail">
      <BrandLink />
      <nav aria-label="Account navigation" className="workspace-rail-nav">
        <p className="workspace-rail-label">Market workspace</p>
        <Link href="/terminal" aria-current={pathname === "/terminal" ? "page" : undefined} className="workspace-item"><WorkspaceIcon name="dashboard" /> Dashboard</Link>
        <Link href="/chart/NIFTY50" aria-current={pathname === "/chart/NIFTY50" ? "page" : undefined} className="workspace-item"><WorkspaceIcon name="chart" /> NIFTY 50 chart</Link>
        <Link href="/chart/BANKNIFTY" aria-current={pathname === "/chart/BANKNIFTY" ? "page" : undefined} className="workspace-item"><WorkspaceIcon name="chart" /> BANK NIFTY chart</Link>
        <Link href="/account" aria-current={pathname === "/account" ? "page" : undefined} className="workspace-item"><WorkspaceIcon name="account" /> Account</Link>
        {isAdmin && <Link href="/admin" className="workspace-item"><WorkspaceIcon name="shield" /> Admin portal</Link>}
      </nav>
      <div className="workspace-rail-foot">
        <span className="workspace-rail-email" title={email}>{email}</span>
        <button type="button" className="as-button workspace-signout" onClick={onSignOut}>Sign out</button>
      </div>
    </aside>
  );
}
