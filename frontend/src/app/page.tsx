'use client'
import Link from "next/link";
import { useAuth } from "./providers/AuthProvider";

/** 菜单项与对应的页面权限码 */
const MENUS = [
  { href: "/window/chat", label: "快照", perm: "page:/window/chat" },
];

export default function Home() {
  const { user, has, loading, logout } = useAuth()

  if (loading) {
    return null
  }

  return (
    <div className=" min-h-screen items-center justify-center dark:bg-black" style={{
      display: 'flex', alignItems: 'center', flexDirection: 'column',
      padding: 20,
    }} >
      <div className="w-full flex justify-end items-center gap-3 p-4 text-sm text-gray-500"
        style={{
          margin: 18,

        }}
      >
        <span>user: {user?.nickname || user?.username}</span>
        <button onClick={logout} className="text-blue-500 underline">退出</button>
      </div>
      <div className="flex flex-1 flex-col items-center justify-center gap-2">
        {MENUS.filter(m => has(m.perm)).map(m => (
          <Link key={m.href} href={m.href} style={{ color: 'purple', fontSize: 17 }}>{m.label}</Link>
        ))}
      </div>
    </div>
  );
}
