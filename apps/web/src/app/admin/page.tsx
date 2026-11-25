import BrandLink from "@/components/BrandLink";
import AdminUsersPanel from "@/components/admin/AdminUsersPanel";

export const metadata = {
  title: "Admin · AllSafe AI Trading",
};

export default function AdminPage() {
  return (
    <AdminUsersPanel brand={<BrandLink />} />
  );
}
