import { getAdminPageUser } from "@/lib/page-auth";
import { AdminNav } from "@/components/AdminNav";

export const dynamic = "force-dynamic";

export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  await getAdminPageUser();
  return (
    <main className="page">
      <div className="admin-shell">
        <aside>
          <AdminNav />
        </aside>
        <div>{children}</div>
      </div>
    </main>
  );
}
