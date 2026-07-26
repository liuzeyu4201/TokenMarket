/**
 * Guard for authenticated routes: no protected content flash while checking.
 * Anonymous users are redirected to login with an in-app return path.
 */

import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from './AuthContext'

/** Only restore in-app relative paths; block open redirects. */
export function safeReturnPath(candidate: unknown, fallback = '/dashboard'): string {
  if (typeof candidate !== 'string' || candidate.length === 0) {
    return fallback
  }
  if (!candidate.startsWith('/') || candidate.startsWith('//')) {
    return fallback
  }
  if (candidate.includes('://') || candidate.includes('\\')) {
    return fallback
  }
  // Block auth pages as return targets to avoid loops.
  if (candidate === '/login' || candidate.startsWith('/login?')) {
    return fallback
  }
  return candidate
}

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const auth = useAuth()
  const location = useLocation()

  if (auth.status === 'checking') {
    return (
      <div className="card" aria-busy="true" data-testid="auth-checking">
        <p>正在确认登录状态…</p>
      </div>
    )
  }

  if (auth.status === 'unavailable') {
    return (
      <div className="card" role="alert" data-testid="auth-unavailable">
        <p>暂时无法确认登录状态，请稍后重试。</p>
        <button type="button" onClick={() => void auth.revalidate()}>
          重试
        </button>
      </div>
    )
  }

  if (auth.status !== 'authenticated' || !auth.session) {
    const from = `${location.pathname}${location.search}`
    return <Navigate to="/login" replace state={{ from: safeReturnPath(from, from) }} />
  }

  return <>{children}</>
}

export default ProtectedRoute
