import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { ApiError } from '../api/client'
import { adminLogin, adminLogout, adminSession, type AdminSession } from './api'

type Status = 'checking' | 'anonymous' | 'authenticated'

interface AdminAuthValue {
  status: Status
  session: AdminSession | null
  error: string | null
  login: (login: string, password: string, mfa: string) => Promise<void>
  logout: () => Promise<void>
}

const AdminAuthContext = createContext<AdminAuthValue | null>(null)

export function AdminAuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>('checking')
  const [session, setSession] = useState<AdminSession | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    void adminSession()
      .then((sess) => {
        if (cancelled) return
        setSession(sess)
        setStatus('authenticated')
      })
      .catch(() => {
        if (cancelled) return
        setSession(null)
        setStatus('anonymous')
      })
    return () => {
      cancelled = true
    }
  }, [])

  const value = useMemo<AdminAuthValue>(
    () => ({
      status,
      session,
      error,
      login: async (loginName, password, mfa) => {
        setError(null)
        try {
          const sess = await adminLogin(loginName, password, mfa)
          setSession(sess)
          setStatus('authenticated')
        } catch (err: unknown) {
          setStatus('anonymous')
          setSession(null)
          setError(err instanceof ApiError ? err.message : '登录失败')
          throw err
        }
      },
      logout: async () => {
        await adminLogout().catch(() => undefined)
        setSession(null)
        setStatus('anonymous')
      },
    }),
    [status, session, error],
  )

  return <AdminAuthContext.Provider value={value}>{children}</AdminAuthContext.Provider>
}

export function useAdminAuth(): AdminAuthValue {
  const ctx = useContext(AdminAuthContext)
  if (!ctx) {
    throw new Error('useAdminAuth 必须在 AdminAuthProvider 内使用')
  }
  return ctx
}
