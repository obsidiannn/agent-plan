'use client'
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react"
import { useRouter } from "next/navigation"

/** 登录用户信息(与后端 JWT 载荷一致) */
export interface SessionUser {
    userId: string
    username: string
    nickname?: string | null
    roles: string[]
    perms: string[]
}

interface AuthContextValue {
    user: SessionUser | null
    loading: boolean
    /** 是否拥有某个权限码, 如 page:/strategy/sword */
    has: (code: string) => boolean
    refresh: () => Promise<void>
    logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue>({
    user: null,
    loading: true,
    has: () => false,
    refresh: async () => { },
    logout: async () => { },
})

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
    const [user, setUser] = useState<SessionUser | null>(null)
    const [loading, setLoading] = useState(true)
    const router = useRouter()

    const refresh = useCallback(async () => {
        try {
            const res = await fetch('/api/auth/me')
            const resp = await res.json()
            setUser(resp?.data ?? null)
        } catch {
            setUser(null)
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        refresh()
    }, [refresh])

    const has = useCallback((code: string) => {
        if (!user) {
            return false
        }
        return user.perms.includes('*') || user.perms.includes(code)
    }, [user])

    const logout = useCallback(async () => {
        await fetch('/api/auth/logout', { method: 'POST' })
        setUser(null)
        router.push('/login')
    }, [router])

    const value = useMemo(() => ({ user, loading, has, refresh, logout }), [user, loading, has, refresh, logout])

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
