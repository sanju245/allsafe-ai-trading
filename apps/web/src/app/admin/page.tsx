import Link from "next/link";
import BrandLink from "@/components/BrandLink";
import AdminUsersPanel from "@/components/admin/AdminUsersPanel";

export const metadata = {
  title: "Admin · AllSafe AI Trading",
};

export default function AdminPage() {
  return (
    <div className="as-page">
      <header className="as-topbar">
        <div className="as-container as-topbar-inner">
          <BrandLink />
          <div className="as-nav-group">
            <span className="as-pill as-pill--green">Admin portal</span>
            <Link href="/terminal" className="as-nav-link">Market dashboard</Link>
          </div>
        </div>
      </header>
      <main className="as-container">
        <AdminUsersPanel />
      </main>
    </div>
  );
}
