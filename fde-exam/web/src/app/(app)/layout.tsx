import { getPageUser } from "@/lib/page-auth";
import { AppNav } from "@/components/AppNav";

export const dynamic = "force-dynamic";

export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await getPageUser();
  return (
    <div className="app-shell">
      <AppNav user={user} />
      {children}
    </div>
  );
}
