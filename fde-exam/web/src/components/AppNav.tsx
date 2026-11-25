import Link from "next/link";
import type { SessionUser } from "@/lib/auth";
import { NavLinks } from "@/components/NavLinks";
import { LogoutButton } from "@/components/LogoutButton";

export function AppNav({ user }: { user: SessionUser }) {
  const initial = (user.nickname || user.username).slice(0, 1).toUpperCase();
  return (
    <header className="topbar">
      <div className="topbar-inner">
        <Link href="/" className="brand">
          <span className="brand-mark">FDE</span>
          <span>FDE 模拟考试</span>
        </Link>
        <NavLinks isAdmin={user.role === "ADMIN"} />
        <div className="topbar-user">
          <span className="avatar">{initial}</span>
          <span className="user-name">{user.nickname || user.username}</span>
          <LogoutButton />
        </div>
      </div>
    </header>
  );
}
