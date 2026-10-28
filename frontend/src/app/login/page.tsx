'use client'
import { useCallback, useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/app/providers/AuthProvider"

const LoginPage = () => {
    const router = useRouter()
    const { refresh } = useAuth()
    const [username, setUsername] = useState('')
    const [password, setPassword] = useState('')
    const [redirect, setRedirect] = useState('/')
    const [error, setError] = useState('')
    const [loading, setLoading] = useState(false)

    useEffect(() => {
        const params = new URLSearchParams(window.location.search)
        setRedirect(params.get('redirect') || '/')
    }, [])

    const onSubmit = useCallback(async (e: React.FormEvent) => {
        e.preventDefault()
        if (loading) {
            return
        }
        setError('')
        setLoading(true)
        try {
            const res = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
            })
            const resp = await res.json().catch(() => ({}))
            if (!res.ok) {
                setError(resp?.message ?? '登录失败')
                return
            }
            // 更新 AuthProvider 中的登录态, 否则跳转后首页菜单仍为空
            await refresh()
            router.push(redirect)
            router.refresh()
        } catch {
            setError('网络异常, 请稍后重试')
        } finally {
            setLoading(false)
        }
    }, [username, password, redirect, loading, router, refresh])

    return (
        <div className="min-h-screen flex items-center justify-center dark:bg-black">
            <form onSubmit={onSubmit}
                className="flex flex-col gap-4 w-80 p-8 border border-gray-200 rounded-lg dark:border-gray-700">
                <div className="text-xl text-center">Agent Plan</div>
                <input
                    style={{
                        border: '0.5px solid gray',
                        padding: 3
                    }}
                    className="border border-gray-300 rounded px-3 py-2 dark:bg-transparent dark:border-gray-600"
                    placeholder="用户名"
                    value={username}
                    autoFocus
                    onChange={(e) => setUsername(e.target.value)}
                />
                <input
                    style={{
                        border: '0.5px solid gray',
                        padding: 3
                    }}
                    className="border border-gray-300 rounded px-3 py-2 dark:bg-transparent dark:border-gray-600"
                    placeholder="密码"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                />
                {error && <div className="text-red-500 text-sm">{error}</div>}
                <button
                    type="submit"
                    disabled={loading}
                    className="bg-blue-500 text-white rounded py-2 disabled:opacity-50"
                >
                    {loading ? '登录中...' : '登录'}
                </button>
            </form>
        </div>
    );
}

export default LoginPage
