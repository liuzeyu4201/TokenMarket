/**
 * Sole owner of browser session-summary state for TokenMarket.
 *
 * - Four states: checking | authenticated | anonymous | unavailable
 * - CSRF is held in React memory only (never localStorage/sessionStorage).
 * - Never reads document.cookie for the session token.
 * - Cross-tab BroadcastChannel carries event names only (no tokens/PII).
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import {
  PhoneAuthClientError,
  bootstrapSession,
  logoutSession,
} from '../api/v1/phoneAuth'
import type { AuthStatus, SessionData, SessionSummary } from '../types/auth'
import { toSessionSummary } from '../types/auth'
import { clearChallenge } from './challengeState'

/** Safe cross-tab event names only — never payloads with tokens/PII. */
export type AuthBroadcastEvent = 'login' | 'logout' | 'session-invalidated'

export const AUTH_BROADCAST_CHANNEL = 'tokenmarket-auth'

export interface AuthContextValue {
  status: AuthStatus
  session: SessionSummary | null
  /** Memory-only CSRF; do not render or persist. */
  getCsrfToken: () => string | null
  /** Apply create-session success — sets authenticated + broadcasts login. */
  establishSession: (data: SessionData) => void
  /** Clear summary + CSRF (logout / unauthenticated). */
  clearSession: () => void
  /** Revalidate cookie session with the server. */
  revalidate: () => Promise<void>
  /** Logout with CSRF; idempotent when already anonymous. */
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

function isUnavailableError(err: unknown): boolean {
  if (!(err instanceof PhoneAuthClientError)) {
    return true
  }
  return (
    err.code === 'SERVICE_UNAVAILABLE' ||
    err.code === 'DELIVERY_UNAVAILABLE' ||
    err.code === 'INTERNAL_ERROR' ||
    err.status === 503 ||
    err.status === 0
  )
}

function isUnauthenticatedError(err: unknown): boolean {
  return (
    err instanceof PhoneAuthClientError &&
    (err.code === 'UNAUTHENTICATED' || err.action === 'clear_session')
  )
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('checking')
  const [session, setSession] = useState<SessionSummary | null>(null)
  /** CSRF never leaves this ref into storage or serializable state for persistence. */
  const csrfRef = useRef<string | null>(null)
  const revalidateInFlight = useRef<Promise<void> | null>(null)
  const broadcastRef = useRef<BroadcastChannel | null>(null)
  /** Track whether we have ever been authenticated in this tab (for fail-soft). */
  const hadSessionRef = useRef(false)

  const getCsrfToken = useCallback(() => csrfRef.current, [])

  const postBroadcast = useCallback((event: AuthBroadcastEvent) => {
    try {
      broadcastRef.current?.postMessage(event)
    } catch {
      // BroadcastChannel may throw if closed; focus revalidation covers this.
    }
  }, [])

  const establishSession = useCallback(
    (data: SessionData) => {
      // Terminal login success: drop challenge metadata from sessionStorage.
      clearChallenge()
      csrfRef.current = data.csrf_token
      hadSessionRef.current = true
      setSession(toSessionSummary(data))
      setStatus('authenticated')
      postBroadcast('login')
    },
    [postBroadcast],
  )

  const clearSession = useCallback(() => {
    clearChallenge()
    csrfRef.current = null
    hadSessionRef.current = false
    setSession(null)
    setStatus('anonymous')
  }, [])

  const revalidate = useCallback(async () => {
    if (revalidateInFlight.current) {
      return revalidateInFlight.current
    }
    const run = (async () => {
      try {
        const data = await bootstrapSession()
        csrfRef.current = data.csrf_token
        hadSessionRef.current = true
        setSession(toSessionSummary(data))
        setStatus('authenticated')
      } catch (err) {
        if (isUnauthenticatedError(err)) {
          clearChallenge()
          csrfRef.current = null
          hadSessionRef.current = false
          setSession(null)
          setStatus('anonymous')
          return
        }
        if (isUnavailableError(err)) {
          // Network / dependency failure must not look like logout.
          if (hadSessionRef.current && csrfRef.current) {
            setStatus('authenticated')
          } else {
            setStatus('unavailable')
          }
          return
        }
        if (hadSessionRef.current && csrfRef.current) {
          setStatus('authenticated')
        } else {
          setStatus('unavailable')
        }
      } finally {
        revalidateInFlight.current = null
      }
    })()
    revalidateInFlight.current = run
    return run
  }, [])

  const logout = useCallback(async () => {
    // If CSRF is missing but a cookie may exist, bootstrap first.
    if (!csrfRef.current) {
      try {
        const data = await bootstrapSession()
        csrfRef.current = data.csrf_token
        hadSessionRef.current = true
        setSession(toSessionSummary(data))
        setStatus('authenticated')
      } catch (err) {
        if (isUnauthenticatedError(err)) {
          clearChallenge()
          csrfRef.current = null
          hadSessionRef.current = false
          setSession(null)
          setStatus('anonymous')
          postBroadcast('logout')
          return
        }
        if (isUnavailableError(err)) {
          setStatus('unavailable')
          return
        }
      }
    }

    try {
      await logoutSession(csrfRef.current)
      clearChallenge()
      csrfRef.current = null
      hadSessionRef.current = false
      setSession(null)
      setStatus('anonymous')
      postBroadcast('logout')
    } catch (err) {
      if (isUnauthenticatedError(err)) {
        clearChallenge()
        csrfRef.current = null
        hadSessionRef.current = false
        setSession(null)
        setStatus('anonymous')
        postBroadcast('session-invalidated')
        return
      }
      if (err instanceof PhoneAuthClientError && err.code === 'CSRF_INVALID') {
        await revalidate()
        return
      }
      if (isUnavailableError(err)) {
        setStatus('unavailable')
        return
      }
      clearChallenge()
      csrfRef.current = null
      hadSessionRef.current = false
      setSession(null)
      setStatus('anonymous')
      postBroadcast('logout')
    }
  }, [postBroadcast, revalidate])

  // Initial bootstrap + focus revalidation + BroadcastChannel.
  useEffect(() => {
    let cancelled = false
    void (async () => {
      if (cancelled) return
      await revalidate()
    })()

    const onFocus = () => {
      void revalidate()
    }
    window.addEventListener('focus', onFocus)

    let channel: BroadcastChannel | null = null
    if (typeof BroadcastChannel !== 'undefined') {
      try {
        channel = new BroadcastChannel(AUTH_BROADCAST_CHANNEL)
        broadcastRef.current = channel
        channel.onmessage = (ev: MessageEvent) => {
          const name = ev.data
          if (name === 'login' || name === 'logout' || name === 'session-invalidated') {
            void revalidate()
          }
        }
      } catch {
        channel = null
      }
    }

    return () => {
      cancelled = true
      window.removeEventListener('focus', onFocus)
      if (channel) {
        channel.close()
      }
      broadcastRef.current = null
    }
  }, [revalidate])

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      session,
      getCsrfToken,
      establishSession,
      clearSession,
      revalidate,
      logout,
    }),
    [status, session, getCsrfToken, establishSession, clearSession, revalidate, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return ctx
}

export default AuthProvider
