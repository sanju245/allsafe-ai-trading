import Link from "next/link";
import AdminUsersPanel from "@/components/admin/AdminUsersPanel";

export const metadata = {
  title: "Admin · AllSafe AI Trading",
};

export default function AdminPage() {
  return (
    <main className="mx-auto min-h-screen max-w-6xl px-4 py-6 sm:px-6 lg:px-8">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
        <Link href="/" className="text-lg font-semibold tracking-tight text-white hover:text-emerald-300">
          AllSafe <span className="text-emerald-400">AI Trading</span>
        </Link>
        <span className="rounded-full border border-emerald-400/20 bg-emerald-400/5 px-3 py-1 text-xs font-medium text-emerald-200">
          Admin portal
        </span>
      </header>
      <AdminUsersPanel />
    </main>
  );
}
