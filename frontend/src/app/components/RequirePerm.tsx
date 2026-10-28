'use client'
import { useAuth } from "@/app/providers/AuthProvider"

/**
 * 页面权限守卫: 前端兜底(服务端已由 proxy.ts 拦截)
 */
const RequirePerm = ({ code, children }: { code: string, children: React.ReactNode }) => {
    const { has, loading, user } = useAuth()

    if (loading) {
        return null
    }

    if (!user) {
        return <div className="min-h-screen flex items-center justify-center text-gray-500">未登录, 正在跳转登录页...</div>
    }

    if (!has(code)) {
        return (
            <div className="min-h-screen flex flex-col items-center justify-center gap-3 text-gray-500">
                <div className="text-2xl">403</div>
                <div>无权限访问该页面</div>
                <a href="/" className="text-blue-500 underline">返回首页</a>
            </div>
        )
    }

    return <>{children}</>
}

export default RequirePerm
